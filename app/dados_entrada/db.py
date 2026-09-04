"""Persistência isolada para geração de dados de entrada no PostgreSQL.

A cópia para o histórico é explícita, transacional e idempotente.
"""

from __future__ import annotations

import datetime
import json
from contextlib import contextmanager
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.nucleo import db_backend

from .cidades import (
    CATEGORIAS_DENSIDADE,
    CIDADES_POR_ESPECIE,
    calcular_lotacao,
)

if TYPE_CHECKING:
    from collections.abc import Iterator


class ConfiguracaoDadosEntradaError(ValueError):
    """Configuracao de zona ou operacao de dados de entrada invalida."""


@contextmanager
def _conexao(*, escrita: bool = True) -> Iterator:
    """Conexao com commit/rollback automatico.

    Com `escrita=False`, a transacao sempre sofre rollback. Assim, uma funcao
    declarada como leitura nao persiste um INSERT introduzido por descuido.

    Descartar, e nao `SET TRANSACTION READ ONLY`, de proposito: a conexao vem
    de um pool do SQLAlchemy, e `SET default_transaction_read_only` ficaria
    grudado nela para o proximo tomador -- que pode ser um gravador legitimo.
    Falhar alto seria melhor se as duas coisas nao se contradissessem aqui.
    """
    conn = db_backend.abrir_conexao_postgres("dados_entrada")
    try:
        yield conn
        if escrita:
            conn.commit()
        else:
            conn.rollback()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@contextmanager
def sessao_geracao() -> Iterator[_SessaoGeracao]:
    """Reutiliza uma conexão PostgreSQL durante a geração em lotes."""
    conn = db_backend.abrir_conexao_postgres("dados_entrada")
    try:
        yield _SessaoGeracao(conn)
    finally:
        conn.close()


class _SessaoGeracao:
    """Insere cada lote em sua própria transação PostgreSQL."""

    __slots__ = ("_conn",)

    def __init__(self, conn) -> None:
        self._conn = conn

    def inserir_medicoes(self, medicoes: list[dict]) -> None:
        if not medicoes:
            return
        try:
            _inserir_medicoes_na_conexao(self._conn, medicoes)
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise


def iniciar_banco() -> None:
    """O schema ``dados_entrada`` é criado exclusivamente pelo Alembic."""


def _agora() -> str:
    return datetime.datetime.now().replace(microsecond=0).isoformat(timespec="seconds")


def sincronizar_zonas(zonas: list[dict]) -> list[dict]:
    """Cria os registros de configuracao que faltam e atualiza rotulos.

    Localizacao, efetivo e peso permanecem vazios/zero ate serem informados;
    nao ha valores zootecnicos inventados silenciosamente.
    """
    agora = _agora()
    with _conexao() as conn:
        for zona in zonas:
            conn.execute(
                """
                INSERT INTO configuracoes_zona
                    (zona_id, zona_nome, especie, atualizado_em)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(zona_id) DO UPDATE SET
                    zona_nome = excluded.zona_nome,
                    especie = excluded.especie
                """,
                (zona["id"], zona["nome"], zona["especie"], agora),
            )
        linhas = conn.execute("SELECT * FROM configuracoes_zona ORDER BY zona_id").fetchall()
    ids_atuais = {zona["id"] for zona in zonas}
    return [_config_publica(dict(linha)) for linha in linhas if linha["zona_id"] in ids_atuais]


# Espelha os DEFAULT do DDL de `configuracoes_zona`
# (`migrations/versions/20260803_0001_baseline.py`). Uma zona sem linha
# gravada e apresentada exatamente como a linha que o INSERT criaria -- e a
# unica forma de a leitura nao precisar gravar para responder.
_CONFIG_PADRAO: dict = {
    "cidade_codigo_ibge": None,
    "latitude": None,
    "longitude": None,
    "fuso_horario": "America/Sao_Paulo",
    "altitude_m": None,
    "area_util_m2": None,
    "densidade_categoria": "media",
    "densidade_animais_m2": None,
    "quantidade_animais": 0,
    "peso_medio_kg": None,
    "producao_leite_kg_dia": 0,
    "ordenhas_dia": 0,
    "atualizado_em": None,
}


def listar_configuracoes(zonas: list[dict]) -> list[dict]:
    """Le as configuracoes das zonas SEM gravar nada.

    Existe porque `GET /api/dados-entrada/configuracoes` chamava
    `sincronizar_zonas`, que faz INSERT/UPDATE. GET deve ser seguro por
    contrato: qualquer prefetch de navegador, robo ou sonda de monitoracao
    escrevia no banco so por passar ali. O efeito era idempotente, entao nao
    havia perda de dado -- era contrato quebrado, e vale arrumar antes que
    alguem construa em cima.

    A materializacao continua acontecendo, nos dois caminhos que ja gravam:
    salvar os parametros (`salvar_configuracoes_zonas`) e gerar dados
    (`gerador_dados`). Zona nunca configurada simplesmente nao tem linha --
    que e a mesma coisa que a linha em branco dizia.

    O rotulo (`zona_nome`, `especie`) vem sempre da zona VIVA, nao da copia
    denormalizada da tabela. Antes, renomear uma zona so aparecia aqui porque
    o proprio GET regravava; agora aparece porque a leitura sobrepoe. O
    resultado visivel e igual, sem a escrita.
    """
    with _conexao(escrita=False) as conn:
        linhas = conn.execute("SELECT * FROM configuracoes_zona ORDER BY zona_id").fetchall()
    gravadas = {linha["zona_id"]: dict(linha) for linha in linhas}

    configuracoes = []
    for zona in zonas:
        config = gravadas.get(zona["id"])
        if config is None:
            config = dict(_CONFIG_PADRAO)
            config["zona_id"] = zona["id"]
        config["zona_nome"] = zona["nome"]
        config["especie"] = zona["especie"]
        configuracoes.append(_config_publica(config))
    # Mesma ordem que `sincronizar_zonas` devolvia (a do SELECT), para a tela
    # nao trocar de ordem por causa desta mudanca.
    configuracoes.sort(key=lambda config: config["zona_id"])
    return configuracoes


def _config_publica(config: dict) -> dict:
    config["configurada"] = bool(
        config.get("cidade_codigo_ibge")
        and config.get("latitude") is not None
        and config.get("longitude") is not None
        and (config.get("area_util_m2") or 0) > 0
        and config.get("densidade_categoria")
        and (config.get("densidade_animais_m2") or 0) > 0
        and config.get("quantidade_animais", 0) > 0
        and (config.get("peso_medio_kg") or 0) > 0
    )
    return config


def _numero(dados: dict, chave: str, minimo: float, maximo: float) -> float:
    bruto = dados.get(chave)
    if bruto is None:
        raise ConfiguracaoDadosEntradaError(f"Informe um valor numÃ©rico para {chave}.")
    try:
        valor = float(bruto)
    except (TypeError, ValueError) as erro:
        raise ConfiguracaoDadosEntradaError(f"Informe um valor numérico para {chave}.") from erro
    if not minimo <= valor <= maximo:
        raise ConfiguracaoDadosEntradaError(f"{chave} deve estar entre {minimo:g} e {maximo:g}.")
    return valor


def validar_configuracao_zona(dados: dict, zona: dict) -> dict:
    cidade_codigo = str(dados.get("cidade_codigo_ibge", "")).strip()
    codigos_validos = {cidade["codigo_ibge"] for cidade in CIDADES_POR_ESPECIE[zona["especie"]]}
    if cidade_codigo not in codigos_validos:
        raise ConfiguracaoDadosEntradaError(
            f"Selecione uma das cidades de referência da zona '{zona['nome']}'."
        )
    latitude = _numero(dados, "latitude", -90, 90)
    longitude = _numero(dados, "longitude", -180, 180)
    altitude = _numero(dados, "altitude_m", -500, 9000)
    peso = _numero(dados, "peso_medio_kg", 0.01, 2_000)
    area_util = _numero(dados, "area_util_m2", 0.1, 10_000_000)
    categoria = str(dados.get("densidade_categoria", "")).strip()
    categorias_validas = {item["valor"] for item in CATEGORIAS_DENSIDADE}
    if categoria not in categorias_validas:
        raise ConfiguracaoDadosEntradaError(
            f"Selecione uma categoria de densidade para a zona '{zona['nome']}'."
        )
    lotacao = calcular_lotacao(zona["especie"], peso, area_util, categoria)
    quantidade = lotacao["quantidade_animais"]
    if quantidade < 1:
        raise ConfiguracaoDadosEntradaError(
            f"A área útil da zona '{zona['nome']}' é insuficiente para um animal "
            "com o peso e a densidade selecionados."
        )
    if quantidade > 1_000_000:
        raise ConfiguracaoDadosEntradaError(
            f"A lotação calculada da zona '{zona['nome']}' excede 1.000.000 de animais."
        )
    producao = _numero(dados, "producao_leite_kg_dia", 0, 150)
    ordenhas = int(_numero(dados, "ordenhas_dia", 0, 4))
    fuso = str(dados.get("fuso_horario", "")).strip()
    try:
        ZoneInfo(fuso)
    except (ZoneInfoNotFoundError, ValueError) as erro:
        raise ConfiguracaoDadosEntradaError(
            f"Fuso horário inválido: {fuso!r}. Use um nome IANA, como America/Sao_Paulo."
        ) from erro

    if zona["especie"] != "bovinos" and (producao > 0 or ordenhas > 0):
        raise ConfiguracaoDadosEntradaError(
            f"Produção de leite e ordenhas só se aplicam à zona bovina '{zona['nome']}'."
        )
    if zona["especie"] == "bovinos" and producao > 0 and ordenhas == 0:
        raise ConfiguracaoDadosEntradaError(
            f"Informe ao menos uma ordenha diária para a zona '{zona['nome']}'."
        )
    return {
        "zona_id": zona["id"],
        "zona_nome": zona["nome"],
        "especie": zona["especie"],
        "cidade_codigo_ibge": cidade_codigo,
        "latitude": latitude,
        "longitude": longitude,
        "fuso_horario": fuso,
        "altitude_m": altitude,
        "area_util_m2": area_util,
        "densidade_categoria": categoria,
        "densidade_animais_m2": lotacao["densidade_animais_m2"],
        "quantidade_animais": quantidade,
        "peso_medio_kg": peso,
        "producao_leite_kg_dia": producao,
        "ordenhas_dia": ordenhas,
    }


def salvar_configuracoes_zonas(dados: list[dict], zonas: list[dict]) -> list[dict]:
    if not isinstance(dados, list):
        raise ConfiguracaoDadosEntradaError("As configurações das zonas devem ser uma lista.")
    zonas_por_id = {zona["id"]: zona for zona in zonas}
    validadas = []
    for item in dados:
        zona_id_bruto = item.get("zona_id")
        if zona_id_bruto is None:
            raise ConfiguracaoDadosEntradaError("ID de zona invÃ¡lido.")
        try:
            zona_id = int(zona_id_bruto)
        except (TypeError, ValueError) as erro:
            raise ConfiguracaoDadosEntradaError("ID de zona inválido.") from erro
        zona = zonas_por_id.get(zona_id)
        if zona is None:
            raise ConfiguracaoDadosEntradaError(f"Zona {zona_id} não encontrada.")
        validadas.append(validar_configuracao_zona(item, zona))

    agora = _agora()
    with _conexao() as conn:
        for item in validadas:
            conn.execute(
                """
                INSERT INTO configuracoes_zona (
                    zona_id, zona_nome, especie, cidade_codigo_ibge, latitude, longitude,
                    fuso_horario, altitude_m, area_util_m2, densidade_categoria,
                    densidade_animais_m2, quantidade_animais,
                    peso_medio_kg, producao_leite_kg_dia, ordenhas_dia, atualizado_em
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(zona_id) DO UPDATE SET
                    zona_nome=excluded.zona_nome, especie=excluded.especie,
                    cidade_codigo_ibge=excluded.cidade_codigo_ibge,
                    latitude=excluded.latitude, longitude=excluded.longitude,
                    fuso_horario=excluded.fuso_horario, altitude_m=excluded.altitude_m,
                    area_util_m2=excluded.area_util_m2,
                    densidade_categoria=excluded.densidade_categoria,
                    densidade_animais_m2=excluded.densidade_animais_m2,
                    quantidade_animais=excluded.quantidade_animais,
                    peso_medio_kg=excluded.peso_medio_kg,
                    producao_leite_kg_dia=excluded.producao_leite_kg_dia,
                    ordenhas_dia=excluded.ordenhas_dia, atualizado_em=excluded.atualizado_em
                """,
                (
                    item["zona_id"],
                    item["zona_nome"],
                    item["especie"],
                    item["cidade_codigo_ibge"],
                    item["latitude"],
                    item["longitude"],
                    item["fuso_horario"],
                    item["altitude_m"],
                    item["area_util_m2"],
                    item["densidade_categoria"],
                    item["densidade_animais_m2"],
                    item["quantidade_animais"],
                    item["peso_medio_kg"],
                    item["producao_leite_kg_dia"],
                    item["ordenhas_dia"],
                    agora,
                ),
            )
    return sincronizar_zonas(zonas)


def criar_execucao(
    *,
    data_inicio: str,
    data_fim: str,
    dias: int,
    intervalo_minutos: int,
    semente: int,
    total_zonas: int,
    fonte_clima: str,
) -> int:
    with _conexao() as conn:
        cursor = conn.execute(
            """
            INSERT INTO execucoes (
                data_inicio, data_fim, dias, intervalo_minutos, semente,
                fonte_clima, total_zonas, status, criado_em
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'processando', ?)
            """,
            (
                data_inicio,
                data_fim,
                dias,
                intervalo_minutos,
                semente,
                fonte_clima,
                total_zonas,
                _agora(),
            ),
        )
        return int(cursor.lastrowid)


_COLUNAS_MEDICAO = (
    "execucao_id",
    "zona_id",
    "zona_nome",
    "especie",
    "indice",
    "timestamp_utc",
    "timestamp_local",
    "fuso_horario",
    "tbs_externa_c",
    "ur_externa_pct",
    "ponto_orvalho_c",
    "tbu_c",
    "velocidade_vento_ms",
    "precipitacao_mm",
    "pressao_hpa",
    "radiacao_w_m2",
    "nebulosidade_pct",
    "valor_indice",
    "status_termico",
    "area_util_m2",
    "densidade_categoria",
    "densidade_animais_m2",
    "quantidade_animais",
    "atividade_predominante",
    "alimentacao_kg",
    "consumo_agua_l",
    "animais_em_pe",
    "animais_deitados",
    "animais_em_ordenha",
    "calor_sensivel_animais_w",
    "calor_latente_animais_w",
    "vapor_agua_animais_kg_h",
    "origem_variaveis",
    "indicador_qualidade",
    "entradas_indice",
    "simulation_seed",
)


def _serializar_json_coluna(valor):
    """Serializa um valor de coluna JSON, a menos que ja seja uma string.

    `entradas_indice` varia a cada medicao e chega como dict. Ja
    `origem_variaveis` e identico para toda a execucao (ver
    `gerador_dados._metadados_origem_json`) e chega ja serializado como
    string, para nao repetir `json.dumps` no mesmo conteudo constante em
    cada uma das linhas.
    """
    return valor if isinstance(valor, str) else json.dumps(valor, ensure_ascii=False)


def _inserir_medicoes_na_conexao(conn, medicoes: list[dict]) -> None:
    if not medicoes:
        return
    placeholders = ",".join("?" for _ in _COLUNAS_MEDICAO)
    conn.executemany(
        f"INSERT INTO medicoes ({','.join(_COLUNAS_MEDICAO)}) VALUES ({placeholders})",
        [
            tuple(
                _serializar_json_coluna(item[coluna])
                if coluna in ("origem_variaveis", "entradas_indice")
                else item[coluna]
                for coluna in _COLUNAS_MEDICAO
            )
            for item in medicoes
        ],
    )


def inserir_medicoes(medicoes: list[dict]) -> None:
    with _conexao() as conn:
        _inserir_medicoes_na_conexao(conn, medicoes)


def concluir_execucao(execucao_id: int, total_medicoes: int) -> None:
    with _conexao() as conn:
        conn.execute(
            "UPDATE execucoes SET status='concluida', total_medicoes=?, concluido_em=? WHERE id=?",
            (total_medicoes, _agora(), execucao_id),
        )


def falhar_execucao(execucao_id: int, erro: str) -> None:
    with _conexao() as conn:
        conn.execute("DELETE FROM medicoes WHERE execucao_id=?", (execucao_id,))
        conn.execute(
            "UPDATE execucoes SET status='falhou', erro=?, concluido_em=? WHERE id=?",
            (str(erro)[:1000], _agora(), execucao_id),
        )


def listar_execucoes(limite: int = 20) -> list[dict]:
    with _conexao(escrita=False) as conn:
        linhas = conn.execute(
            """
            SELECT e.*, COUNT(he.medicao_id) AS medicoes_copiadas
            FROM execucoes e
            LEFT JOIN medicoes m ON m.execucao_id = e.id
            LEFT JOIN historico_exportado he ON he.medicao_id = m.id
            GROUP BY e.id
            ORDER BY e.id DESC LIMIT ?
            """,
            (max(1, min(100, int(limite))),),
        ).fetchall()
    return [dict(linha) for linha in linhas]


def obter_execucao(execucao_id: int) -> dict | None:
    with _conexao(escrita=False) as conn:
        linha = conn.execute("SELECT * FROM execucoes WHERE id=?", (execucao_id,)).fetchone()
    return dict(linha) if linha else None


def excluir_medicoes(execucao_id: int | None = None) -> int:
    with _conexao() as conn:
        if execucao_id is None:
            total = conn.execute("SELECT COUNT(*) FROM medicoes").fetchone()[0]
            conn.execute("DELETE FROM execucoes")
        else:
            total = conn.execute(
                "SELECT COUNT(*) FROM medicoes WHERE execucao_id=?", (execucao_id,)
            ).fetchone()[0]
            conn.execute("DELETE FROM execucoes WHERE id=?", (execucao_id,))
    return int(total)


def obter_medicoes_csv(execucao_id: int | None = None) -> tuple[list[str], list[tuple]]:
    colunas = [coluna for coluna in _COLUNAS_MEDICAO if coluna != "execucao_id"]
    with _conexao(escrita=False) as conn:
        if execucao_id is None:
            linhas = conn.execute(
                f"SELECT {','.join(colunas)} FROM medicoes ORDER BY execucao_id,zona_id,timestamp_utc"
            ).fetchall()
        else:
            linhas = conn.execute(
                f"SELECT {','.join(colunas)} FROM medicoes WHERE execucao_id=? "
                "ORDER BY zona_id,timestamp_utc",
                (execucao_id,),
            ).fetchall()
    return colunas, [tuple(linha[coluna] for coluna in colunas) for linha in linhas]


def iterar_medicoes_csv(
    execucao_id: int | None = None, *, tamanho_lote: int = 500
) -> tuple[list[str], Iterator[tuple]]:
    """Devolve as medições em lotes, mantendo a conexão só durante a iteração.

    A exportação HTTP consome esse iterador incrementalmente. Assim, nem o
    resultado SQL nem o CSV completo precisam coexistir em memória — condição
    importante no contêiner ICT, cujo limite é deliberadamente pequeno.
    """
    colunas = [coluna for coluna in _COLUNAS_MEDICAO if coluna != "execucao_id"]
    lote = max(1, min(5000, int(tamanho_lote)))

    def _linhas() -> Iterator[tuple]:
        with _conexao(escrita=False) as conn:
            if execucao_id is None:
                resultado = conn.execute(
                    f"SELECT {','.join(colunas)} FROM medicoes "
                    "ORDER BY execucao_id,zona_id,timestamp_utc"
                )
            else:
                resultado = conn.execute(
                    f"SELECT {','.join(colunas)} FROM medicoes WHERE execucao_id=? "
                    "ORDER BY zona_id,timestamp_utc",
                    (execucao_id,),
                )
            while linhas := resultado.fetchmany(lote):
                for linha in linhas:
                    yield tuple(linha[coluna] for coluna in colunas)

    return colunas, _linhas()


def obter_cache_clima(chave: str) -> dict | None:
    with _conexao(escrita=False) as conn:
        linha = conn.execute(
            "SELECT resposta_json FROM cache_clima WHERE chave=?", (chave,)
        ).fetchone()
    return json.loads(linha["resposta_json"]) if linha else None


def salvar_cache_clima(chave: str, resposta: dict, fonte: str) -> None:
    with _conexao() as conn:
        conn.execute(
            """
            INSERT INTO cache_clima (chave, resposta_json, fonte, consultado_em)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(chave) DO UPDATE SET resposta_json=excluded.resposta_json,
                fonte=excluded.fonte, consultado_em=excluded.consultado_em
            """,
            (chave, json.dumps(resposta), fonte, _agora()),
        )


def excluir_cache_clima(chave: str) -> None:
    with _conexao() as conn:
        conn.execute("DELETE FROM cache_clima WHERE chave=?", (chave,))


def copiar_medicoes_para_historico(execucao_id: int) -> dict:
    """Copia uma geração concluída ao schema ``historico`` uma única vez."""
    with _conexao() as conn:
        execucao = conn.execute(
            "SELECT status, total_medicoes FROM execucoes WHERE id=?",
            (execucao_id,),
        ).fetchone()
        if execucao is None:
            raise ConfiguracaoDadosEntradaError(f"Execução {execucao_id} não encontrada.")
        if execucao["status"] != "concluida":
            raise ConfiguracaoDadosEntradaError("Somente uma geração concluída pode ser copiada.")
        pendentes = int(
            conn.execute(
                """
            SELECT COUNT(*) FROM medicoes m
            LEFT JOIN historico_exportado he ON he.medicao_id = m.id
            WHERE m.execucao_id=? AND he.medicao_id IS NULL
            """,
                (execucao_id,),
            ).fetchone()[0]
        )
        agora = _agora()
        if pendentes:
            conn.execute(
                """
                INSERT INTO historico.leituras
                    (especie, indice, valor, status, entradas, criado_em, zona_id)
                SELECT m.especie, m.indice, m.valor_indice, m.status_termico,
                       m.entradas_indice, substr(m.timestamp_local, 1, 16), m.zona_id
                FROM medicoes m LEFT JOIN historico_exportado he ON he.medicao_id = m.id
                WHERE m.execucao_id=? AND he.medicao_id IS NULL
                ORDER BY m.zona_id, m.timestamp_utc
                """,
                (execucao_id,),
            )
            conn.execute(
                """
                INSERT INTO historico_exportado (medicao_id, copiado_em)
                SELECT m.id, ? FROM medicoes m
                LEFT JOIN historico_exportado he ON he.medicao_id = m.id
                WHERE m.execucao_id=? AND he.medicao_id IS NULL
                """,
                (agora, execucao_id),
            )
        total_copiado = int(
            conn.execute(
                """
            SELECT COUNT(*) FROM historico_exportado he
            JOIN medicoes m ON m.id = he.medicao_id WHERE m.execucao_id=?
            """,
                (execucao_id,),
            ).fetchone()[0]
        )
    return {
        "execucao_id": execucao_id,
        "novas_copiadas": pendentes,
        "total_copiado": total_copiado,
        "arquivo_destino": "PostgreSQL (schema historico)",
    }
