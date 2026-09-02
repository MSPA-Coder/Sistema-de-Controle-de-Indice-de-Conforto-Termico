"""Persistência, cache e validação das configurações operacionais."""

from __future__ import annotations

import datetime
import json
import re
from typing import Any, cast

from . import cache as cache_module
from . import thermal_indices as ti
from .database_comum import coagir_booleano as _coagir_booleano
from .database_comum import conexao

# Cache global para configurações e dados de referência (TTL: 5 minutos)
_cache_configuracoes = cache_module.obter_cache(ttl_segundos=300.0)

CONFIGURACOES_PADRAO = {
    "coletarDados": False,
    "habilitarSons": False,
    "enviarEmails": False,
    "habilitarEquipamentos": False,
    "emailDestino": "alertas@example.invalid",
    "statusMinimoEmail": "conforto",
    "intervaloLeituraSegundos": 1,
    "intervaloGravacaoMinutos": 1,
    "modoPontoOrvalho": "medido",
    "modoUmidadeRelativa": "calculado",
    "altitudeMetros": 0,
    "limiteUmidadeNebulizador": 70,
    # Especie/indice selecionados na interface e persistidos como parametro
    # do sistema, validados em conjunto.
    "especie": "frangos",
    "indice": "ITU",
    # Parametros SMTP editaveis pela interface. Variaveis de ambiente SMTP_*
    # continuam como fallback por campo (ver models.Email.enviar). "" (vazio)
    # para host/usuario significa "nao configurado".
    #
    # A SENHA nao tem chave aqui, de proposito (CT-03): ate 01/09/2026 ela
    # persistia em texto claro nesta tabela -- o dump que o BackupRestore gera
    # e cataloga todo dia a replicava sem passar por tela nenhuma. Agora vem
    # exclusivamente de `models.senha_smtp_configurada`/`_resolver_senha_smtp`
    # (segredo do Compose ou a variavel `SMTP_PASS`, ja documentada em
    # `.env.example`).
    "smtpHost": "",
    "smtpPorta": 587,
    "smtpUsuario": "",
    # Modo simulado para as Zonas Modbus: quando ligado (padrao, ja que
    # normalmente ainda nao ha hardware Modbus real conectado), leitura de
    # sensor/escrita em atuador/teste de conexao das zonas nao tocam a rede
    # de verdade -- geram valores plausiveis do mesmo jeito que o sensor
    # simulado da aba Principal ja faz (ver modbus_simulador.py). Desligue
    # quando o hardware Modbus real estiver conectado.
    "modoSimuladoZonas": True,
}

# Regex pragmatica (nao e uma validacao RFC 5322 completa) para pegar os
# casos que importam aqui: formato minimamente plausivel de e-mail e,
# principalmente, ausencia de espacos/CR/LF que permitiriam injetar
# cabecalhos SMTP adicionais (ex.: "Bcc:") caso este valor va parar dentro
# de um cabecalho de e-mail (ver models.Email).
_EMAIL_REGEX = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def _coagir_numero(valor, padrao: float, minimo: float, maximo: float) -> float:
    try:
        numero = float(str(valor).replace(",", "."))
    except (TypeError, ValueError):
        return padrao
    if numero != numero:  # NaN nunca e igual a si mesmo
        return padrao
    # `float(...)` explicito no retorno: sem isso, `max(minimo, ...)` pode
    # devolver o proprio `minimo` (int) sem conversao quando o valor
    # limitado empata exatamente com o piso, deixando esse campo como int
    # enquanto os demais campos numericos da mesma configuracao viram
    # float -- inconsistencia de tipo inofensiva, mas desnecessaria.
    return float(max(minimo, min(maximo, numero)))


def _coagir_enum(valor, padrao: str, permitidos: tuple[str, ...]) -> str:
    return valor if isinstance(valor, str) and valor in permitidos else padrao


def _coagir_email(valor, padrao: str) -> str:
    if isinstance(valor, str):
        candidato = valor.strip()
        if _EMAIL_REGEX.fullmatch(candidato):
            return candidato
    return padrao


def _coagir_especie(valor, padrao: str) -> str:
    return valor if isinstance(valor, str) and valor in ti.ESPECIES_VALIDAS else padrao


def _coagir_indice(valor, especie: str, padrao: str) -> str:
    """Valida o indice em funcao da especie ja resolvida (nao existe indice
    "generico" -- ITUV so faz sentido para frangos, por exemplo). Se nem o
    valor recebido nem o padrao servirem para a especie atual (ex.: especie
    mudou e o indice salvo ficou orfao), cai para o primeiro indice
    disponivel daquela especie, que sempre existe."""
    disponiveis = ti.INDICES_POR_ESPECIE.get(especie, ())
    if isinstance(valor, str) and valor in disponiveis:
        return valor
    if padrao in disponiveis:
        return padrao
    return disponiveis[0] if disponiveis else padrao


def _coagir_texto_livre(valor, padrao: str, tamanho_maximo: int = 255) -> str:
    """Sanitizador para campos de texto livre (host/usuario/senha SMTP):
    aceita apenas string, remove caracteres de controle (CR/LF/NUL -- nunca
    legitimos nesses campos e sinal classico de tentativa de injecao) e
    limita o tamanho. Diferente dos demais coercers, uma string vazia AQUI
    e um valor valido (significa "SMTP nao configurado", nao um erro)."""
    if not isinstance(valor, str):
        return padrao
    limpo = re.sub(r"[\r\n\x00]", "", valor).strip()
    return limpo[:tamanho_maximo]


def _sanitizar_configuracoes(configuracoes: dict, *, base: dict | None = None) -> dict:
    """Valida tipo, faixa e formato de cada chave de configuracao conhecida.

    Mistura os valores recebidos com o estado atual (ou os padroes para a
    primeira gravacao; chaves desconhecidas sao descartadas) e entao aplica
    um "validador" especifico por chave. Um
    valor invalido (tipo errado, fora da faixa, e-mail malformado) nunca
    lanca excecao: ele simplesmente volta a usar o padrao daquele campo. Ver
    a nota de seguranca no topo do modulo sobre `emailDestino`."""
    padrao: dict[str, Any] = CONFIGURACOES_PADRAO
    bruto: dict[str, Any] = {
        **padrao,
        **{k: v for k, v in (base or {}).items() if k in padrao},
        **{k: v for k, v in (configuracoes or {}).items() if k in padrao},
    }

    # `indice` depende de `especie` (ITUV so existe para frangos, etc.) --
    # por isso especie e resolvida primeiro e passada para o coercer do
    # indice, em vez de cada campo ser validado de forma totalmente
    # independente como os demais.
    especie = _coagir_especie(bruto["especie"], padrao["especie"])

    return {
        "coletarDados": _coagir_booleano(bruto["coletarDados"], padrao["coletarDados"]),
        "habilitarSons": _coagir_booleano(bruto["habilitarSons"], padrao["habilitarSons"]),
        "enviarEmails": _coagir_booleano(bruto["enviarEmails"], padrao["enviarEmails"]),
        "habilitarEquipamentos": _coagir_booleano(
            bruto["habilitarEquipamentos"], padrao["habilitarEquipamentos"]
        ),
        "emailDestino": _coagir_email(bruto["emailDestino"], padrao["emailDestino"]),
        "statusMinimoEmail": _coagir_enum(
            bruto["statusMinimoEmail"],
            padrao["statusMinimoEmail"],
            tuple(ti.STATUS_PESO.keys()),
        ),
        "intervaloLeituraSegundos": _coagir_numero(
            bruto["intervaloLeituraSegundos"], padrao["intervaloLeituraSegundos"], 1, 3600
        ),
        "intervaloGravacaoMinutos": _coagir_numero(
            bruto["intervaloGravacaoMinutos"], padrao["intervaloGravacaoMinutos"], 0, 1440
        ),
        "modoPontoOrvalho": _coagir_enum(
            bruto["modoPontoOrvalho"], padrao["modoPontoOrvalho"], ("medido", "calculado")
        ),
        "modoUmidadeRelativa": _coagir_enum(
            bruto["modoUmidadeRelativa"], padrao["modoUmidadeRelativa"], ("medido", "calculado")
        ),
        "altitudeMetros": _coagir_numero(
            bruto["altitudeMetros"], padrao["altitudeMetros"], -500, 9000
        ),
        "limiteUmidadeNebulizador": _coagir_numero(
            bruto["limiteUmidadeNebulizador"], padrao["limiteUmidadeNebulizador"], 0, 100
        ),
        "especie": especie,
        "indice": _coagir_indice(bruto["indice"], especie, padrao["indice"]),
        "smtpHost": _coagir_texto_livre(bruto["smtpHost"], padrao["smtpHost"]),
        "smtpPorta": _coagir_numero(bruto["smtpPorta"], padrao["smtpPorta"], 1, 65535),
        "smtpUsuario": _coagir_texto_livre(bruto["smtpUsuario"], padrao["smtpUsuario"]),
        # Sem "smtpSenha" aqui de proposito (CT-03): a senha do SMTP nao mora
        # mais nesta tabela. Ver `models.senha_smtp_configurada` e a migracao
        # `20260902_0001_remover_smtp_senha`, que apaga o valor ja persistido.
        "modoSimuladoZonas": _coagir_booleano(
            bruto["modoSimuladoZonas"], padrao["modoSimuladoZonas"]
        ),
    }


def _decodificar_configuracoes(linhas) -> dict:
    configuracoes = dict(CONFIGURACOES_PADRAO)
    for linha in linhas:
        try:
            configuracoes[linha["chave"]] = json.loads(linha["valor"])
        except json.JSONDecodeError:
            configuracoes[linha["chave"]] = linha["valor"]
    return configuracoes


def obter_configuracoes(*, usar_cache: bool = True) -> dict:
    """Obtém configurações do banco, opcionalmente usando o cache local.

    Processos ICT e coletor possuem caches independentes. Flags operacionais
    que protegem o acesso a hardware devem usar ``usar_cache=False`` para que
    uma mudança persistida pelo ICT seja observada já no próximo ciclo.
    """
    if usar_cache:
        valor_cached = _cache_configuracoes.get("configuracoes_gerais")
        if valor_cached is not None:
            return cast("dict", valor_cached)

    with conexao(escrita=False) as conn:
        linhas = conn.execute("SELECT chave, valor FROM configuracoes").fetchall()

    resultado = _sanitizar_configuracoes(_decodificar_configuracoes(linhas))
    if usar_cache:
        _cache_configuracoes.set("configuracoes_gerais", resultado)
    return resultado


def limpar_cache_configuracoes() -> None:
    """Limpa o cache de configurações (chamar após salvar novas configurações)."""
    _cache_configuracoes.delete("configuracoes_gerais")


def salvar_configuracoes(configuracoes: dict) -> dict:
    configuracoes = dict(configuracoes or {})

    # A leitura e a escrita ocorrem na mesma transacao. Em PostgreSQL, um
    # advisory lock protege o documento de configuracoes contra lost updates
    # entre processos diferentes; a serialização local do backend anterior não
    # oferecia essa garantia.
    agora = datetime.datetime.now().replace(microsecond=0).isoformat(timespec="seconds")
    with conexao() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(hashtext('conforto:configuracoes'))")
        linhas = conn.execute("SELECT chave, valor FROM configuracoes").fetchall()
        atuais = _decodificar_configuracoes(linhas)

        # `smtpSenha` nao esta mais em CONFIGURACOES_PADRAO (CT-03): o filtro
        # `if k in padrao` de `_sanitizar_configuracoes` ja descarta sozinho
        # qualquer valor de senha que um cliente antigo ainda envie, sem
        # precisar de tratamento especial aqui.
        salvas = _sanitizar_configuracoes(configuracoes, base=atuais)
        conn.executemany(
            """
            INSERT INTO configuracoes (chave, valor, atualizado_em)
            VALUES (?, ?, ?)
            ON CONFLICT(chave) DO UPDATE SET
                valor = excluded.valor,
                atualizado_em = excluded.atualizado_em
            """,
            [(chave, json.dumps(valor), agora) for chave, valor in salvas.items()],
        )

    # Limpa o cache após salvar novas configurações
    limpar_cache_configuracoes()
    return salvas
