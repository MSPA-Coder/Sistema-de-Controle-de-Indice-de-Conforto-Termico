"""
database.py
============
Persistência do histórico de leituras, configurações, zonas Modbus e
equipamentos no PostgreSQL.

Todas as operações passam por `_conexao()`, que garante commit/rollback e
fecha a conexão. O PostgreSQL gerencia concorrência e pooling.
Configuracoes persistidas sao sempre sanitizadas em leitura e escrita; valores
invalidos voltam ao padrao seguro da chave.
"""

from __future__ import annotations

import bisect
import datetime
import json

from app.termico import thermal_indices as ti

from .comum import coagir_booleano as coagir_booleano
from .comum import conexao as _conexao
from .configuracoes import obter_configuracoes

MODOS_OPERACAO = ("desligado", "manual", "automatico", "manutencao")
MODO_OPERACAO_PADRAO = "manual"


# ---------------------------------------------------------------------------
# Zonas Modbus: cadastro de zonas (grupos de sensores/ventiladores/
# nebulizadores conectados via Modbus) e seus equipamentos.
#
# NOTA DE DESIGN: diferente de `_sanitizar_configuracoes` (que sempre cai
# para um padrao seguro em caso de valor invalido), a validacao aqui
# REJEITA com erro claro em vez de adivinhar um substituto. Um endereco de
# registrador Modbus errado nao e um "valor de configuracao ligeiramente
# fora do ideal" -- e o endereco de um equipamento FISICO real; "corrigir"
# silenciosamente para um padrao arriscaria ler ou escrever no registrador
# ERRADO de um sensor/atuador de verdade. Cadastro de hardware deve falhar
# alto (400 na API) quando o que foi informado esta incorreto.
# ---------------------------------------------------------------------------


class ZonaInvalidaError(ValueError):
    """Erro de validacao ao criar/atualizar uma zona ou equipamento Modbus."""


class ZonaNaoEncontradaError(ZonaInvalidaError):
    """Subclasse especifica para "zona_id nao existe", usada por
    `criar_equipamento`. Existe para que a camada HTTP saiba
    devolver 404 (em vez de 400) SEM precisar refazer a consulta "a zona
    existe?" -- que ja foi respondida, atomicamente, dentro da mesma
    transacao que tentou a operacao (ver `criar_equipamento`)."""


def obter_controle_zona(zona_id: int) -> dict | None:
    """Devolve modo e permissao de acionamento persistidos para a zona."""
    with _conexao(escrita=False) as conn:
        zona = conn.execute("SELECT 1 FROM zonas WHERE id = ?", (zona_id,)).fetchone()
        if zona is None:
            return None
        linha = conn.execute(
            "SELECT modo, acionamento_habilitado, atualizado_em "
            "FROM controle_zonas WHERE zona_id = ?",
            (zona_id,),
        ).fetchone()
    if linha is None:
        return {
            "zona_id": zona_id,
            "modo": MODO_OPERACAO_PADRAO,
            "acionamento_habilitado": False,
            "atualizado_em": None,
        }
    return {
        "zona_id": zona_id,
        "modo": linha["modo"],
        "acionamento_habilitado": bool(linha["acionamento_habilitado"]),
        "atualizado_em": linha["atualizado_em"],
    }


def salvar_controle_zona(zona_id: int, dados: dict) -> dict:
    atual = obter_controle_zona(zona_id)
    if atual is None:
        raise ZonaNaoEncontradaError(f"Zona {zona_id} nao encontrada.")

    modo = dados.get("modo", atual["modo"])
    if modo not in MODOS_OPERACAO:
        raise ZonaInvalidaError(
            f"Modo operacional invalido: {modo!r} (esperado um de {MODOS_OPERACAO})."
        )

    acionamento = dados.get("acionamento_habilitado", atual["acionamento_habilitado"])
    if not isinstance(acionamento, bool):
        raise ZonaInvalidaError("acionamento_habilitado precisa ser booleano.")

    agora = datetime.datetime.now().replace(microsecond=0).isoformat(timespec="seconds")
    with _conexao() as conn:
        conn.execute(
            """
            INSERT INTO controle_zonas
                (zona_id, modo, acionamento_habilitado, atualizado_em)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(zona_id) DO UPDATE SET
                modo = excluded.modo,
                acionamento_habilitado = excluded.acionamento_habilitado,
                atualizado_em = excluded.atualizado_em
            """,
            (zona_id, modo, int(acionamento), agora),
        )
    return {
        "zona_id": zona_id,
        "modo": modo,
        "acionamento_habilitado": acionamento,
        "atualizado_em": agora,
    }


def _validar_inteiro(valor, nome_campo: str, minimo: int, maximo: int) -> int:
    try:
        numero = int(float(str(valor).replace(",", ".")))
    except (TypeError, ValueError) as err:
        raise ZonaInvalidaError(f"O campo '{nome_campo}' precisa ser um número inteiro.") from err
    if not (minimo <= numero <= maximo):
        raise ZonaInvalidaError(f"O campo '{nome_campo}' precisa estar entre {minimo} e {maximo}.")
    return numero


def _validar_numero(valor, nome_campo: str) -> float:
    try:
        return float(str(valor).replace(",", "."))
    except (TypeError, ValueError) as err:
        raise ZonaInvalidaError(f"O campo '{nome_campo}' precisa ser numérico.") from err


def _validar_zona(dados: dict) -> dict:
    nome = str(dados.get("nome", "")).strip()
    if not nome:
        raise ZonaInvalidaError("Informe um nome para a zona.")

    especie = dados.get("especie")
    if especie not in ti.ESPECIES_VALIDAS:
        raise ZonaInvalidaError(f"Espécie inválida: {especie!r}.")

    indice = dados.get("indice")
    if indice not in ti.INDICES_POR_ESPECIE.get(especie, ()):
        raise ZonaInvalidaError(
            f"Índice {indice!r} não está disponível para a espécie {especie!r}."
        )

    return {
        "nome": nome[:255],
        "especie": especie,
        "indice": indice,
        "ativa": coagir_booleano(dados.get("ativa", True), True),
        # Três ciclos é o padrão escolhido para equilibrar atraso transitório
        # e sinalização rápida. A política deliberadamente só admite 2 ou 3.
        "ciclos_expiracao_leitura": _validar_inteiro(
            dados.get("ciclos_expiracao_leitura", 3),
            "ciclos de expiração da leitura",
            2,
            3,
        ),
    }


def criar_zona(dados: dict) -> dict:
    validado = _validar_zona(dados)
    agora = datetime.datetime.now().replace(microsecond=0).isoformat(timespec="seconds")
    with _conexao() as conn:
        cursor = conn.execute(
            """INSERT INTO zonas
               (nome, especie, indice, ativa, ciclos_expiracao_leitura, criado_em)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                validado["nome"],
                validado["especie"],
                validado["indice"],
                int(validado["ativa"]),
                validado["ciclos_expiracao_leitura"],
                agora,
            ),
        )
        zona_id = cursor.lastrowid
        conn.execute(
            "INSERT INTO controle_zonas "
            "(zona_id, modo, acionamento_habilitado, atualizado_em) VALUES (?, ?, 0, ?)",
            (zona_id, MODO_OPERACAO_PADRAO, agora),
        )
    # Monta o retorno com os dados ja em maos, em vez de abrir uma segunda
    # conexao so para reler o que acabamos de gravar: uma zona recem-criada
    # nunca tem equipamentos (sao cadastrados depois, num POST separado).
    return {
        "id": zona_id,
        "nome": validado["nome"],
        "especie": validado["especie"],
        "indice": validado["indice"],
        "ativa": validado["ativa"],
        "ciclos_expiracao_leitura": validado["ciclos_expiracao_leitura"],
        "criado_em": agora,
        "equipamentos": [],
        "controle": {
            "modo": MODO_OPERACAO_PADRAO,
            "acionamento_habilitado": False,
            "atualizado_em": agora,
        },
    }


#: O que a listagem de zonas conta sobre um equipamento SEM contar a fiação.
#:
#: `host`, `porta`, `porta_serial`, `baud_rate`, `unidade_id`,
#: `tipo_registrador`, `endereco_registrador`, `tipo_dado` e `fator_escala`
#: ficam de fora: juntos, são o endereço do equipamento na rede industrial e o
#: bastante para falar com ele sem passar por esta aplicação. Quem precisa
#: deles é a aba Zonas, e a área `cadastro` existe para restringi-la.
#:
#: O que sobra é vocabulário de domínio: qual zona, que tipo de equipamento,
#: como se chama e o que mede.
COLUNAS_EQUIPAMENTO_SEM_FIACAO = ("id", "zona_id", "tipo", "nome", "campo_medido")


def listar_zonas(
    *, apenas_ativas: bool = False, com_fiacao: bool = False
) -> list[dict]:
    """Zonas com seus equipamentos e o estado do controle.

    ``com_fiacao`` decide se cada equipamento vem com o endereçamento Modbus.
    **O padrão é NÃO trazer**, e essa escolha é de segurança, não de
    desempenho: até 01/09/2026 esta função devolvia `SELECT *` para todo mundo,
    e a rota pública `GET /api/zonas` — liberada pela área `dashboard`, que os
    seis perfis têm — entregava a fiação completa a qualquer conta autenticada.
    A rota de UMA zona (`administracao.obter_zona`) exigia `cadastro` e
    devolvia os mesmos campos: estava fechada a porta e aberta a janela.

    Com o padrão fechado, um chamador novo que precise da fiação tem de pedir
    por nome — e quem esquecer recebe um `KeyError` visível, não um vazamento
    silencioso. Mesmo princípio do `_exigir_area`, que nega o endpoint não
    mapeado em vez de liberá-lo.

    Nenhum consumidor interno precisou mudar: o laço do coletor e o
    `ZonaService` leem a fiação por `obter_zona`, não por aqui.
    """
    # Interpolação deliberada: `filtro` é escolhido entre dois literais fixos
    # por um booleano do próprio código, nunca por entrada do usuário — não há
    # caminho de injeção. O mesmo vale para a lista de colunas abaixo, que é
    # uma constante do módulo.
    filtro = "WHERE ativa = 1" if apenas_ativas else ""
    colunas = "*" if com_fiacao else ", ".join(COLUNAS_EQUIPAMENTO_SEM_FIACAO)
    with _conexao(escrita=False) as conn:
        linhas_zonas = conn.execute(
            f"SELECT * FROM zonas {filtro} ORDER BY id"  # noqa: S608
        ).fetchall()
        # Uma unica consulta para os equipamentos de TODAS as zonas, em vez
        # de uma consulta por zona (N+1): antes, listar 20 zonas abria 21
        # conexoes/consultas; agora abre so 2, dentro da mesma conexao.
        linhas_equipamentos = conn.execute(
            f"SELECT {colunas} FROM equipamentos ORDER BY zona_id, tipo, id"  # noqa: S608
        ).fetchall()
        linhas_controle = conn.execute(
            "SELECT zona_id, modo, acionamento_habilitado, atualizado_em "
            "FROM controle_zonas ORDER BY zona_id"
        ).fetchall()

    equipamentos_por_zona: dict[int, list[dict]] = {}
    for linha in linhas_equipamentos:
        equipamentos_por_zona.setdefault(linha["zona_id"], []).append(dict(linha))

    zonas = [dict(linha) for linha in linhas_zonas]
    controle_por_zona = {linha["zona_id"]: linha for linha in linhas_controle}
    for zona in zonas:
        zona["ativa"] = bool(zona["ativa"])
        zona["equipamentos"] = equipamentos_por_zona.get(zona["id"], [])
        controle = controle_por_zona.get(zona["id"])
        zona["controle"] = {
            "modo": controle["modo"] if controle else MODO_OPERACAO_PADRAO,
            "acionamento_habilitado": bool(controle["acionamento_habilitado"])
            if controle
            else False,
            "atualizado_em": controle["atualizado_em"] if controle else None,
        }
    return zonas


def obter_zona(zona_id: int) -> dict | None:
    with _conexao(escrita=False) as conn:
        linha = conn.execute("SELECT * FROM zonas WHERE id = ?", (zona_id,)).fetchone()
        if not linha:
            return None
        equipamentos = conn.execute(
            "SELECT * FROM equipamentos WHERE zona_id = ? ORDER BY tipo, id", (zona_id,)
        ).fetchall()
        controle = conn.execute(
            "SELECT modo, acionamento_habilitado, atualizado_em "
            "FROM controle_zonas WHERE zona_id = ?",
            (zona_id,),
        ).fetchone()
    zona = dict(linha)
    zona["ativa"] = bool(zona["ativa"])
    zona["equipamentos"] = [dict(e) for e in equipamentos]
    zona["controle"] = {
        "modo": controle["modo"] if controle else MODO_OPERACAO_PADRAO,
        "acionamento_habilitado": bool(controle["acionamento_habilitado"]) if controle else False,
        "atualizado_em": controle["atualizado_em"] if controle else None,
    }
    return zona


def obter_estado_operacional_zonas() -> list[dict]:
    """Snapshot somente-leitura usado pelo Dashboard e pela aba Operacao."""
    zonas = listar_zonas()
    with _conexao(escrita=False) as conn:
        linhas = conn.execute("SELECT * FROM estado_equipamentos ORDER BY zona_id").fetchall()
    estados = {linha["zona_id"]: dict(linha) for linha in linhas}

    def _bool_opcional(valor):
        return None if valor is None else bool(valor)

    configuracoes = obter_configuracoes()
    intervalo = float(configuracoes.get("intervaloLeituraSegundos") or 1)
    agora = datetime.datetime.now()
    resultado = []
    for zona in zonas:
        ciclos_expiracao = int(zona.get("ciclos_expiracao_leitura") or 3)
        limite_atualidade = datetime.timedelta(seconds=max(10.0, intervalo * ciclos_expiracao))
        estado = estados.get(zona["id"], {})
        falhas = estado.get("falhas") or "[]"
        try:
            falhas = json.loads(falhas)
        except (TypeError, json.JSONDecodeError):
            falhas = []
        ultimo_ciclo_em = estado.get("ultimo_ciclo_em")
        idade_leitura_segundos = None
        leitura_atual = False
        if ultimo_ciclo_em:
            try:
                idade = agora - datetime.datetime.fromisoformat(ultimo_ciclo_em)
                idade_leitura_segundos = max(0, int(idade.total_seconds()))
                leitura_atual = idade <= limite_atualidade
            except (TypeError, ValueError):
                pass
        qualidade_original = estado.get("qualidade") or "sem_leitura"
        resultado.append(
            {
                "zona_id": zona["id"],
                "zona_nome": zona["nome"],
                "ativa": zona["ativa"],
                "modo": zona["controle"]["modo"],
                "acionamento_habilitado": zona["controle"]["acionamento_habilitado"],
                "desejado": {
                    "ventilador": _bool_opcional(estado.get("ventilador_desejado")),
                    "nebulizador": _bool_opcional(estado.get("nebulizador_desejado")),
                },
                "confirmado": {
                    "ventilador": _bool_opcional(estado.get("ventilador_confirmado")),
                    "nebulizador": _bool_opcional(estado.get("nebulizador_confirmado")),
                },
                "intensidade": estado.get("intensidade"),
                "qualidade": (
                    qualidade_original
                    if leitura_atual or ultimo_ciclo_em is None
                    else "desatualizada"
                ),
                "qualidade_original": qualidade_original,
                "leitura_atual": leitura_atual,
                "idade_leitura_segundos": idade_leitura_segundos,
                "limite_atualidade_segundos": int(limite_atualidade.total_seconds()),
                "ciclos_expiracao_leitura": ciclos_expiracao,
                "falhas": falhas,
                "ultimo_ciclo_em": ultimo_ciclo_em,
            }
        )
    return resultado


def atualizar_zona(zona_id: int, dados: dict) -> dict | None:
    """Valida os dados primeiro (falha antes de tocar no banco se estiverem
    invalidos) e so entao confere a existencia da zona e grava a mudanca
    dentro de UMA UNICA transacao. Fazer a checagem "a zona existe?" e a
    escrita em conexoes separadas (como nesta funcao antes) deixava uma
    brecha real: outra requisicao poderia excluir a zona bem entre as duas
    chamadas, e o UPDATE seguinte silenciosamente nao afetaria nada (ou, em
    tese, reviveria dados para um id que outra escrita concorrente acabou de
    reaproveitar). Com tudo em um so `with _conexao()`, a checagem e a
    mutacao sao atomicas: nenhuma outra escrita deste processo roda no meio
    do caminho."""
    validado = _validar_zona(dados)
    with _conexao() as conn:
        existe = conn.execute("SELECT 1 FROM zonas WHERE id = ?", (zona_id,)).fetchone()
        if existe is None:
            return None
        conn.execute(
            """UPDATE zonas SET nome = ?, especie = ?, indice = ?, ativa = ?,
               ciclos_expiracao_leitura = ? WHERE id = ?""",
            (
                validado["nome"],
                validado["especie"],
                validado["indice"],
                int(validado["ativa"]),
                validado["ciclos_expiracao_leitura"],
                zona_id,
            ),
        )
        zona_linha = conn.execute("SELECT * FROM zonas WHERE id = ?", (zona_id,)).fetchone()
        equipamentos = conn.execute(
            "SELECT * FROM equipamentos WHERE zona_id = ? ORDER BY tipo, id", (zona_id,)
        ).fetchall()
        controle = conn.execute(
            "SELECT modo, acionamento_habilitado, atualizado_em "
            "FROM controle_zonas WHERE zona_id = ?",
            (zona_id,),
        ).fetchone()
    zona = dict(zona_linha)
    zona["ativa"] = bool(zona["ativa"])
    zona["equipamentos"] = [dict(e) for e in equipamentos]
    zona["controle"] = {
        "modo": controle["modo"] if controle else MODO_OPERACAO_PADRAO,
        "acionamento_habilitado": bool(controle["acionamento_habilitado"]) if controle else False,
        "atualizado_em": controle["atualizado_em"] if controle else None,
    }
    return zona


def excluir_zona(zona_id: int) -> bool:
    """Remove a zona e (via ON DELETE CASCADE) seus equipamentos. O
    historico de leituras ja gravado permanece -- perder o registro
    historico so porque a zona foi reconfigurada/removida seria pior do
    que manter uma referencia a uma zona que não existe mais."""
    with _conexao() as conn:
        cursor = conn.execute("DELETE FROM zonas WHERE id = ?", (zona_id,))
    return int(cursor.rowcount) > 0


def obter_estatisticas_zonas() -> list[dict]:
    """Para cada zona cadastrada, resume todo o historico de leituras
    gravado com o indice ATUALMENTE configurado na zona (leituras de um
    indice anterior, se a zona ja foi reconfigurada, ficam de fora -- media,
    minimo e maximo de indices diferentes nao sao comparaveis entre si):

    - `percentuais`: fracao do tempo (%) que a zona passou em cada status
      (Conforto/Alerta/Perigo/Emergência), ou `None` se nao ha leituras.
    - `media`/`minimo`/`maximo`: estatisticas do valor do indice, ou `None`
      se nao ha leituras.

    Usado pela aba "Análises" do dashboard (2 relatorios por zona)."""
    with _conexao(escrita=False) as conn:
        zonas = conn.execute("SELECT id, nome, especie, indice FROM zonas ORDER BY id").fetchall()
        contagens = conn.execute(
            """
            SELECT zona_id, indice, status, COUNT(*) AS total
            FROM leituras
            WHERE zona_id IS NOT NULL
            GROUP BY zona_id, indice, status
            """
        ).fetchall()
        agregados = conn.execute(
            """
            SELECT zona_id, indice, AVG(valor) AS media, MIN(valor) AS minimo, MAX(valor) AS maximo
            FROM leituras
            WHERE zona_id IS NOT NULL
            GROUP BY zona_id, indice
            """
        ).fetchall()

    contagens_por_zona_indice: dict[tuple[int, str], dict[str, int]] = {}
    for linha in contagens:
        chave = (linha["zona_id"], linha["indice"])
        contagens_por_zona_indice.setdefault(chave, {})[linha["status"]] = linha["total"]

    agregados_por_zona_indice = {(linha["zona_id"], linha["indice"]): linha for linha in agregados}

    resultado = []
    for zona in zonas:
        chave = (zona["id"], zona["indice"])
        contagem_status = contagens_por_zona_indice.get(chave, {})
        total = sum(contagem_status.values())
        agregado = agregados_por_zona_indice.get(chave)

        percentuais = None
        if total:
            percentuais = {
                status: round((contagem_status.get(status, 0) / total) * 100, 1)
                for status in ti.STATUS_ORDEM
            }

        resultado.append(
            {
                "zona_id": zona["id"],
                "nome": zona["nome"],
                "especie": zona["especie"],
                "indice": zona["indice"],
                "total_leituras": total,
                "percentuais": percentuais,
                "media": round(agregado["media"], 2) if agregado else None,
                "minimo": round(agregado["minimo"], 2) if agregado else None,
                "maximo": round(agregado["maximo"], 2) if agregado else None,
            }
        )
    return resultado


# Quantidade maxima de leituras (mais recentes) lidas por zona para montar o
# "Painel executivo por zona" (ver `obter_painel_zonas`). Diferente de
# `obter_estatisticas_zonas` (que varre o historico inteiro para medias
# globais), este painel so precisa de uma janela recente para tendencias,
# leituras de hoje e o padrao de horario de pico dos ultimos dias -- limitar
# evita que uma instalacao com meses de historico faca uma varredura enorme
# a cada carregamento da aba Analises.
LIMITE_LEITURAS_PAINEL_EXECUTIVO = 5000

# Abaixo desta diferenca (em unidades do indice) entre o valor atual e o
# valor de referencia da janela, a tendencia e considerada "estavel" -- sem
# isso, qualquer ruido minimo de leitura apareceria como "subindo"/
# "descendo" a cada atualizacao.
EPSILON_TENDENCIA = 0.5


def obter_painel_zonas() -> list[dict]:
    """Para cada zona cadastrada, monta o resumo operacional usado pelo
    card "Painel executivo por zona" da aba Analises, a partir SOMENTE de
    dados persistidos (historico de leituras + cadastro de equipamentos +
    `estado_equipamentos`). Assim como `obter_estatisticas_zonas`,
    considera apenas leituras do indice ATUALMENTE configurado na zona.

    Inclui `equipamentos_ligados` (contagem ligada/total de ventiladores e
    nebulizadores, a partir de `estado_equipamentos`, atualizada a cada
    ciclo de calculo) e `recomendacao` (texto). Diferente de uma versao
    anterior deste painel, NADA aqui depende do estado em memoria de
    `ZonaService` -- o resultado e reproduzivel por qualquer processo que
    tenha acesso ao mesmo banco, incluindo um processo de "dashboard"
    somente-leitura que nunca fala Modbus (ver `zona_service.py` e
    `agents.md`)."""
    agora = datetime.datetime.now().replace(microsecond=0)
    inicio_dia = agora.replace(hour=0, minute=0, second=0)

    with _conexao(escrita=False) as conn:
        zonas = conn.execute("SELECT id, nome, especie, indice FROM zonas ORDER BY id").fetchall()
        linhas_sensores = conn.execute(
            "SELECT zona_id, nome, campo_medido FROM equipamentos "
            "WHERE tipo = 'sensor' ORDER BY zona_id, id"
        ).fetchall()
        linhas_atuadores = conn.execute(
            "SELECT zona_id, tipo, COUNT(*) AS total FROM equipamentos "
            "WHERE tipo IN ('ventilador', 'nebulizador') GROUP BY zona_id, tipo"
        ).fetchall()
        linhas_estado = conn.execute(
            "SELECT zona_id, ventilador_ligado, nebulizador_ligado, intensidade "
            "FROM estado_equipamentos"
        ).fetchall()
        leituras_por_zona: dict[int, list] = {}
        linhas_leituras = conn.execute(
            """
            SELECT
                z.id AS zona_id,
                recentes.valor,
                recentes.status,
                recentes.entradas,
                recentes.criado_em
            FROM zonas z
            CROSS JOIN LATERAL (
                SELECT l.id, l.valor, l.status, l.entradas, l.criado_em
                FROM leituras l
                WHERE l.zona_id = z.id AND l.indice = z.indice
                ORDER BY l.id DESC
                LIMIT ?
            ) recentes
            ORDER BY z.id, recentes.id
            """,
            (LIMITE_LEITURAS_PAINEL_EXECUTIVO,),
        ).fetchall()
        for linha in linhas_leituras:
            leituras_por_zona.setdefault(linha["zona_id"], []).append(linha)

    sensores_por_zona: dict[int, list] = {}
    for linha in linhas_sensores:
        sensores_por_zona.setdefault(linha["zona_id"], []).append(linha)

    totais_por_zona: dict[int, dict[str, int]] = {}
    for linha in linhas_atuadores:
        totais_por_zona.setdefault(linha["zona_id"], {"ventilador": 0, "nebulizador": 0})
        totais_por_zona[linha["zona_id"]][linha["tipo"]] = linha["total"]

    estado_por_zona: dict[int, object] = {linha["zona_id"]: linha for linha in linhas_estado}

    return [
        _resumir_painel_zona(
            zona,
            leituras_por_zona.get(zona["id"], []),
            sensores_por_zona.get(zona["id"], []),
            totais_por_zona.get(zona["id"], {"ventilador": 0, "nebulizador": 0}),
            estado_por_zona.get(zona["id"]),
            agora,
            inicio_dia,
        )
        for zona in zonas
    ]


def _resumir_painel_zona(
    zona,
    leituras: list,
    sensores: list,
    totais_equipamento: dict[str, int],
    estado_atuadores,
    agora: datetime.datetime,
    inicio_dia: datetime.datetime,
) -> dict:
    ventiladores_total = totais_equipamento.get("ventilador", 0)
    nebulizadores_total = totais_equipamento.get("nebulizador", 0)
    ventilador_ligado = bool(estado_atuadores["ventilador_ligado"]) if estado_atuadores else False
    nebulizador_ligado = bool(estado_atuadores["nebulizador_ligado"]) if estado_atuadores else False

    base = {
        "zona_id": zona["id"],
        "nome": zona["nome"],
        "especie": zona["especie"],
        "indice": zona["indice"],
        "equipamentos_ligados": {
            "ventiladores_ligados": ventiladores_total if ventilador_ligado else 0,
            "ventiladores_total": ventiladores_total,
            "nebulizadores_ligados": nebulizadores_total if nebulizador_ligado else 0,
            "nebulizadores_total": nebulizadores_total,
            "intensidade": estado_atuadores["intensidade"] if estado_atuadores else None,
        },
    }

    if not leituras:
        base.update(
            {
                "status_atual": None,
                "valor_atual": None,
                "ultima_leitura_em": None,
                "tendencias": {"15min": None, "30min": None, "60min": None},
                "percentual_conforto_24h": None,
                "tempo_continuo_status_minutos": None,
                "nivel_maximo_dia": None,
                "minutos_perigo_dia": 0.0,
                "minutos_emergencia_dia": 0.0,
                "pico_previsto": {"horario": None, "ja_ocorreu": False, "dias_amostrados": 0},
                # `None` (em vez de []) sinaliza "sem leitura para avaliar
                # disponibilidade" -- diferente de "todos os sensores
                # responderam" (lista vazia).
                "sensores_indisponiveis": None,
            }
        )
        base["recomendacao"] = _recomendacao_operacional(base)
        return base

    # As `leituras` chegam em ordem cronologica ascendente (ver
    # `obter_painel_zonas`). Cada `criado_em` era reconvertido de string
    # para `datetime` varias vezes abaixo (uma vez por janela de
    # tendencia, uma vez para o corte de 24h, uma vez para o corte de
    # hoje, etc.) -- para uma zona com o maximo de
    # `LIMITE_LEITURAS_PAINEL_EXECUTIVO` leituras, isso chegava a
    # reanalisar a mesma string de data mais de meia duzia de vezes.
    # Convertendo uma unica vez aqui e reaproveitando a lista (com busca
    # binaria via `bisect`, valida porque a lista ja esta ordenada), o
    # resultado e identico, so que em O(n) no lugar de O(n) repetido
    # varias vezes.
    datas = [datetime.datetime.fromisoformat(linha["criado_em"]) for linha in leituras]

    ultima = leituras[-1]
    ultima_dt = datas[-1]
    base["status_atual"] = ultima["status"]
    base["valor_atual"] = round(ultima["valor"], 2)
    base["ultima_leitura_em"] = ultima["criado_em"]

    def _indice_ate(alvo: datetime.datetime) -> int:
        """Indice do ultimo elemento de `datas` com data <= alvo, ou -1 se
        nenhum -- equivalente a percorrer `leituras` procurando o ultimo
        candidato que nao ultrapassa `alvo`, so que em O(log n)."""
        return bisect.bisect_right(datas, alvo) - 1

    def _valor_referencia(minutos: int) -> float | None:
        alvo = ultima_dt - datetime.timedelta(minutes=minutos)
        indice = _indice_ate(alvo)
        return leituras[indice]["valor"] if indice >= 0 else None

    def _tendencia(minutos: int) -> str | None:
        referencia = _valor_referencia(minutos)
        if referencia is None:
            return None
        diferenca = ultima["valor"] - referencia
        if diferenca > EPSILON_TENDENCIA:
            return "subindo"
        if diferenca < -EPSILON_TENDENCIA:
            return "descendo"
        return "estavel"

    base["tendencias"] = {
        "15min": _tendencia(15),
        "30min": _tendencia(30),
        "60min": _tendencia(60),
    }

    corte_24h = agora - datetime.timedelta(hours=24)
    inicio_24h = bisect.bisect_left(datas, corte_24h)
    leituras_24h = leituras[inicio_24h:]
    if leituras_24h:
        conforto = sum(1 for leitura in leituras_24h if leitura["status"] == "Conforto")
        base["percentual_conforto_24h"] = round(100 * conforto / len(leituras_24h), 1)
    else:
        base["percentual_conforto_24h"] = None

    # Tempo continuo no status atual: anda para tras a partir da leitura
    # mais recente enquanto o status nao muda, e usa o inicio dessa
    # sequencia como o momento em que o status atual "comecou".
    inicio_sequencia = ultima_dt
    for linha, dt in zip(reversed(leituras), reversed(datas), strict=False):
        if linha["status"] != ultima["status"]:
            break
        inicio_sequencia = dt
    base["tempo_continuo_status_minutos"] = round(
        (agora - inicio_sequencia).total_seconds() / 60, 1
    )

    inicio_hoje = bisect.bisect_left(datas, inicio_dia)
    leituras_hoje = leituras[inicio_hoje:]
    if leituras_hoje:
        base["nivel_maximo_dia"] = max(
            leituras_hoje,
            key=lambda leitura: ti.STATUS_PESO[
                ti.normalizar_chave_texto(leitura["status"]).lower()
            ],
        )["status"]
    else:
        base["nivel_maximo_dia"] = None

    # Minutos em Perigo/Emergencia hoje: integra o intervalo entre cada
    # leitura e a proxima (o status da leitura mais antiga do par "vale"
    # durante esse intervalo); o ultimo intervalo se estende ate agora,
    # para que o tempo no status atual continue contando em tempo real.
    datas_hoje = datas[inicio_hoje:]
    minutos_por_status = {"Perigo": 0.0, "Emergência": 0.0}
    for posicao, linha in enumerate(leituras_hoje):
        inicio_intervalo = datas_hoje[posicao]
        fim_intervalo = datas_hoje[posicao + 1] if posicao + 1 < len(leituras_hoje) else agora
        if linha["status"] in minutos_por_status:
            minutos_por_status[linha["status"]] += (
                fim_intervalo - inicio_intervalo
            ).total_seconds() / 60

    base["minutos_perigo_dia"] = round(minutos_por_status["Perigo"], 1)
    base["minutos_emergencia_dia"] = round(minutos_por_status["Emergência"], 1)

    # Horario previsto do pico: media do horario (hora:minuto) em que o
    # valor MAXIMO de cada dia ANTERIOR ocorreu. Precisa de pelo menos 2
    # dias anteriores com leitura para ser considerado uma estimativa
    # minimamente confiavel; hoje fica de fora do calculo (e o dia que
    # estamos tentando prever).
    picos_por_dia: dict[datetime.date, tuple[datetime.datetime, float]] = {}
    for linha, dt in zip(leituras, datas, strict=False):
        dia = dt.date()
        if dia == agora.date():
            continue
        atual = picos_por_dia.get(dia)
        if atual is None or linha["valor"] > atual[1]:
            picos_por_dia[dia] = (dt, linha["valor"])

    if len(picos_por_dia) >= 2:
        minutos_desde_meia_noite = [dt.hour * 60 + dt.minute for dt, _ in picos_por_dia.values()]
        media_minutos = round(sum(minutos_desde_meia_noite) / len(minutos_desde_meia_noite))
        minutos_agora = agora.hour * 60 + agora.minute
        base["pico_previsto"] = {
            "horario": f"{media_minutos // 60:02d}:{media_minutos % 60:02d}",
            "ja_ocorreu": minutos_agora > media_minutos,
            "dias_amostrados": len(picos_por_dia),
        }
    else:
        base["pico_previsto"] = {
            "horario": None,
            "ja_ocorreu": False,
            "dias_amostrados": len(picos_por_dia),
        }

    # Sensores indisponiveis: compara os sensores cadastrados na zona com
    # os campos que efetivamente apareceram na leitura mais recente. So
    # avalia campos relevantes para o indice atual (os exigidos pelo
    # indice, mais ur/tpo -- ou tbs/tbu/ur/tpo no caso do IGNU -- que sao
    # os "extras" que `zona_service._entradas_para_historico` tambem
    # grava quando disponiveis). Um sensor cadastrado para um campo fora
    # desse conjunto nao e avaliado aqui (nao ha como inferir sua
    # disponibilidade a partir do que fica persistido no historico).
    campos_relevantes = set(ti.CAMPOS_POR_INDICE[zona["indice"]])
    campos_relevantes |= {"tbs", "tbu", "ur", "tpo"} if zona["indice"] == "IGNU" else {"ur", "tpo"}
    entradas_ultima = json.loads(ultima["entradas"])
    base["sensores_indisponiveis"] = [
        sensor["nome"]
        for sensor in sensores
        if sensor["campo_medido"] in campos_relevantes
        and sensor["campo_medido"] not in entradas_ultima
    ]

    base["recomendacao"] = _recomendacao_operacional(base)
    return base


def _recomendacao_operacional(painel: dict) -> str:
    """Recomendacao textual combinando o status atual (mesma mensagem
    canonica de `thermal_indices.mensagem_do_status`, ja usada no resto da
    interface) com sinais adicionais do proprio painel -- tendencia
    recente e sensores indisponiveis -- quando eles mudam a leitura
    operacional da situacao. Vivia em `zona_service.py` (precisava do
    estado em memoria do ZonaService); movida para ca quando
    `equipamentos_ligados` passou a vir de `estado_equipamentos` -- agora
    o painel inteiro (estatisticas + recomendacao) e so leitura de banco."""
    status = painel.get("status_atual")
    if status is None:
        return "Ainda não há leitura registrada para esta zona."

    partes = [ti.mensagem_do_status(status)]

    tendencia_15min = painel.get("tendencias", {}).get("15min")
    if tendencia_15min == "subindo" and status in ("Perigo", "Emergência"):
        partes.append("O índice ainda está subindo nos últimos 15 minutos: reforce o resfriamento.")
    elif tendencia_15min == "subindo" and status == "Alerta":
        partes.append("Tendência de subida nos últimos 15 minutos; monitore de perto.")
    elif tendencia_15min == "descendo" and status in ("Perigo", "Emergência"):
        partes.append("O índice já vem caindo nos últimos 15 minutos.")

    sensores_indisponiveis = painel.get("sensores_indisponiveis") or []
    if sensores_indisponiveis:
        plural = "es" if len(sensores_indisponiveis) > 1 else ""
        partes.append(
            f"{len(sensores_indisponiveis)} sensor{plural} sem leitura recente -- "
            "confira a conexão Modbus antes de confiar no índice mostrado."
        )

    return " ".join(partes)


# Os agregados de usuários e configurações são reexportados por esta fachada para
# preservar os consumidores que continuam importando ``app.database``.
