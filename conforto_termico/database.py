# -*- coding: utf-8 -*-
"""
database.py
============
Persistencia simples em SQLite (biblioteca padrao do Python, sem
dependencias extras) do historico de leituras, para alimentar os graficos
de "ultimos 20 indices calculados" descritos na secao 3.4.1 (Area 04) da
dissertacao.

NOTA DE CORRECAO: a versao anterior deste modulo usava
`with _lock, sqlite3.connect(...) as conn:` para cada operacao. O
`sqlite3.Connection` como context manager apenas comita/desfaz a transacao
ao sair do bloco -- ele NAO fecha a conexao sozinho (isso e documentado no
proprio modulo sqlite3 da biblioteca padrao). Como resultado, cada chamada
abria uma conexao nova que nunca era fechada, vazando conexoes/descritores
de arquivo ao longo do tempo (principalmente com o modo automatico, que
calcula a cada 1s). Agora todas as operacoes passam pelo gerenciador de
contexto `_conexao()` abaixo, que garante `close()` mesmo se ocorrer erro.

NOTA DE PERFORMANCE/ESTABILIDADE: `_conexao()` agora tambem liga o modo WAL
(melhor throughput e menor chance de bloqueio entre leitores/escritores),
define um timeout de espera por lock e cria um indice composto em
(especie, indice, id) -- sem ele, toda leitura de historico e toda
verificacao de "ultima leitura gravada ha menos de X minutos" fazia uma
varredura completa da tabela `leituras`, que so piora com o tempo em modo
automatico (uma escrita a cada poucos minutos, para sempre).

NOTA DE SEGURANCA/ESTABILIDADE: `salvar_configuracoes`/`obter_configuracoes`
agora passam por `_sanitizar_configuracoes`, que valida tipo, faixa e
formato de cada campo (ex.: `emailDestino` precisa parecer um e-mail e nao
pode conter quebras de linha, o que evitaria injecao de cabecalhos SMTP se
esse valor chegasse a ser usado para montar um e-mail malicioso). Um valor
invalido nunca derruba a rota -- ele apenas volta a usar o padrao seguro
daquele campo especifico, seguindo o mesmo principio adotado no resto do
projeto (nunca deixar uma falha de um aspecto secundario quebrar o
restante do sistema).
"""

from __future__ import annotations

import datetime
import json
import os
import re
import sqlite3
import threading
from contextlib import contextmanager
from typing import Iterator

from . import thermal_indices as ti

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(PROJECT_ROOT, "historico.db")

_lock = threading.Lock()
INTERVALO_MINIMO_LEITURAS = datetime.timedelta(minutes=1)

# Tempo (segundos) que uma conexao espera por um lock antes de desistir com
# "database is locked". O `_lock` do Python ja serializa acessos dentro do
# MESMO processo; este timeout cobre o caso de outro processo (ex.: uma
# ferramenta externa) acessando o mesmo arquivo ao mesmo tempo.
TIMEOUT_CONEXAO_SEGUNDOS = 30.0

CONFIGURACOES_PADRAO = {
    "coletarDados": False,
    "habilitarSons": False,
    "enviarEmails": False,
    "habilitarEquipamentos": False,
    "emailDestino": "produtor@fazenda.com.br",
    "modoAutomatico": False,
    "intervaloLeituraSegundos": 1,
    "intervaloGravacaoMinutos": 1,
    "modoPontoOrvalho": "medido",
    "modoUmidadeRelativa": "calculado",
    "altitudeMetros": 0,
    "limiteUmidadeNebulizador": 70,
    # Especie/indice selecionados na interface (movidos do card "Principal"
    # para a aba "Configuracoes" a pedido do usuario): agora persistem como
    # mais um parametro do sistema, assim como os demais acima.
    "especie": "frangos",
    "indice": "ITU",
    # Parametros de SMTP para envio de e-mail de verdade -- mesmos quatro
    # valores ja documentados no README ("Envio de e-mails de verdade") como
    # variaveis de ambiente SMTP_HOST/SMTP_PORT/SMTP_USER/SMTP_PASS. Aqui
    # viram configuracao editavel pela interface e persistida no banco;
    # continuam funcionando como fallback caso as variaveis de ambiente
    # tambem estejam definidas (ver models.Email.enviar). "" (vazio) para
    # host/usuario/senha significa "nao configurado" -- nao e um erro.
    "smtpHost": "",
    "smtpPorta": 587,
    "smtpUsuario": "",
    "smtpSenha": "",
}

# Regex pragmatica (nao e uma validacao RFC 5322 completa) para pegar os
# casos que importam aqui: formato minimamente plausivel de e-mail e,
# principalmente, ausencia de espacos/CR/LF que permitiriam injetar
# cabecalhos SMTP adicionais (ex.: "Bcc:") caso este valor va parar dentro
# de um cabecalho de e-mail (ver models.Email).
_EMAIL_REGEX = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


@contextmanager
def _conexao() -> Iterator[sqlite3.Connection]:
    """Abre uma conexao SQLite, garante commit em caso de sucesso (ou
    rollback em caso de excecao) e SEMPRE fecha a conexao ao final."""
    with _lock:
        conn = sqlite3.connect(DB_PATH, timeout=TIMEOUT_CONEXAO_SEGUNDOS)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def iniciar_banco() -> None:
    with _conexao() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS leituras (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                especie TEXT NOT NULL,
                indice TEXT NOT NULL,
                valor REAL NOT NULL,
                status TEXT NOT NULL,
                entradas TEXT NOT NULL,
                criado_em TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS configuracoes (
                chave TEXT PRIMARY KEY,
                valor TEXT NOT NULL,
                atualizado_em TEXT NOT NULL
            )
            """
        )
        # Indice composto: toda consulta de historico e toda checagem do
        # intervalo minimo de gravacao filtram por (especie, indice) e
        # ordenam por id. Sem este indice, cada uma dessas consultas varre
        # a tabela inteira -- o que fica cada vez mais lento conforme o
        # historico cresce (a tabela nunca e podada em uso normal).
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_leituras_especie_indice_id "
            "ON leituras (especie, indice, id)"
        )


def _intervalo_minimo_leituras(intervalo_minutos: float | int | str | None) -> datetime.timedelta:
    if intervalo_minutos is None:
        return INTERVALO_MINIMO_LEITURAS

    try:
        minutos = float(intervalo_minutos)
    except (TypeError, ValueError):
        return INTERVALO_MINIMO_LEITURAS

    return datetime.timedelta(minutes=max(0, minutos))


def salvar_leitura(
    especie: str,
    indice: str,
    valor: float,
    status: str,
    entradas: dict,
    intervalo_minutos: float | int | str | None = None,
) -> bool:
    agora = datetime.datetime.now().replace(microsecond=0)
    intervalo_minimo = _intervalo_minimo_leituras(intervalo_minutos)
    with _conexao() as conn:
        ultima = conn.execute(
            "SELECT criado_em FROM leituras WHERE especie = ? AND indice = ? "
            "ORDER BY id DESC LIMIT 1",
            (especie, indice),
        ).fetchone()
        if ultima:
            ultima_data = datetime.datetime.fromisoformat(ultima["criado_em"])
            if agora - ultima_data < intervalo_minimo:
                return False

        conn.execute(
            "INSERT INTO leituras (especie, indice, valor, status, entradas, criado_em) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                especie,
                indice,
                valor,
                status,
                json.dumps(entradas),
                agora.isoformat(timespec="seconds"),
            ),
        )
    return True


def obter_historico(especie: str, indice: str, limite: int = 20) -> list[dict]:
    with _conexao() as conn:
        linhas = conn.execute(
            "SELECT * FROM leituras WHERE especie = ? AND indice = ? "
            "ORDER BY id DESC LIMIT ?",
            (especie, indice, limite),
        ).fetchall()
    dados = [dict(linha) for linha in linhas]
    dados.reverse()  # ordem cronologica (mais antigo -> mais recente) para os graficos
    for item in dados:
        item["entradas"] = json.loads(item["entradas"])
    return dados


def limpar_historico(especie: str | None = None, indice: str | None = None) -> None:
    with _conexao() as conn:
        if especie and indice:
            conn.execute(
                "DELETE FROM leituras WHERE especie = ? AND indice = ?", (especie, indice)
            )
        elif especie:
            conn.execute("DELETE FROM leituras WHERE especie = ?", (especie,))
        else:
            conn.execute("DELETE FROM leituras")


def contar_leituras() -> int:
    """Utilitario de diagnostico: total de linhas gravadas na tabela."""
    with _conexao() as conn:
        (total,) = conn.execute("SELECT COUNT(*) FROM leituras").fetchone()
    return total


def _coagir_booleano(valor, padrao: bool) -> bool:
    if isinstance(valor, bool):
        return valor
    if isinstance(valor, (int, float)):
        return bool(valor)
    if isinstance(valor, str):
        normalizado = valor.strip().lower()
        if normalizado in ("true", "1", "sim", "on"):
            return True
        if normalizado in ("false", "0", "nao", "não", "off", ""):
            return False
    return padrao


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


def _sanitizar_configuracoes(configuracoes: dict) -> dict:
    """Valida tipo, faixa e formato de cada chave de configuracao conhecida.

    Mistura os valores recebidos com os padroes (chaves desconhecidas sao
    descartadas) e entao aplica um "validador" especifico por chave. Um
    valor invalido (tipo errado, fora da faixa, e-mail malformado) nunca
    lanca excecao: ele simplesmente volta a usar o padrao daquele campo. Ver
    a nota de seguranca no topo do modulo sobre `emailDestino`."""
    padrao = CONFIGURACOES_PADRAO
    bruto = {**padrao, **{k: v for k, v in (configuracoes or {}).items() if k in padrao}}

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
        "modoAutomatico": _coagir_booleano(bruto["modoAutomatico"], padrao["modoAutomatico"]),
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
        "altitudeMetros": _coagir_numero(bruto["altitudeMetros"], padrao["altitudeMetros"], -500, 9000),
        "limiteUmidadeNebulizador": _coagir_numero(
            bruto["limiteUmidadeNebulizador"], padrao["limiteUmidadeNebulizador"], 0, 100
        ),
        "especie": especie,
        "indice": _coagir_indice(bruto["indice"], especie, padrao["indice"]),
        "smtpHost": _coagir_texto_livre(bruto["smtpHost"], padrao["smtpHost"]),
        "smtpPorta": _coagir_numero(bruto["smtpPorta"], padrao["smtpPorta"], 1, 65535),
        "smtpUsuario": _coagir_texto_livre(bruto["smtpUsuario"], padrao["smtpUsuario"]),
        "smtpSenha": _coagir_texto_livre(bruto["smtpSenha"], padrao["smtpSenha"]),
    }


def obter_configuracoes() -> dict:
    with _conexao() as conn:
        linhas = conn.execute("SELECT chave, valor FROM configuracoes").fetchall()

    configuracoes = dict(CONFIGURACOES_PADRAO)
    for linha in linhas:
        try:
            configuracoes[linha["chave"]] = json.loads(linha["valor"])
        except json.JSONDecodeError:
            configuracoes[linha["chave"]] = linha["valor"]
    # Sanitiza tambem na leitura: protege contra um valor corrompido ou
    # editado manualmente no arquivo .db (defesa em profundidade -- a
    # escrita ja e validada em salvar_configuracoes).
    return _sanitizar_configuracoes(configuracoes)


def salvar_configuracoes(configuracoes: dict) -> dict:
    configuracoes = dict(configuracoes or {})

    # `smtpSenha` e um campo "somente escrita": a API nunca devolve a senha
    # real de volta ao navegador (ver web._configuracoes_publicas), entao um
    # valor em branco aqui significa "o usuario nao mudou a senha", nao
    # "apague a senha". Sem este tratamento, salvar QUALQUER outro campo
    # (ex.: marcar uma checkbox) apagaria silenciosamente a senha SMTP ja
    # configurada, porque o front-end sempre envia o payload completo e o
    # campo de senha no navegador sempre chega vazio (nunca e preenchido de
    # volta a partir do servidor).
    if not str(configuracoes.get("smtpSenha", "")).strip():
        configuracoes["smtpSenha"] = obter_configuracoes().get("smtpSenha", "")

    salvas = _sanitizar_configuracoes(configuracoes)
    agora = datetime.datetime.now().replace(microsecond=0).isoformat(timespec="seconds")
    with _conexao() as conn:
        conn.executemany(
            """
            INSERT INTO configuracoes (chave, valor, atualizado_em)
            VALUES (?, ?, ?)
            ON CONFLICT(chave) DO UPDATE SET
                valor = excluded.valor,
                atualizado_em = excluded.atualizado_em
            """,
            [
                (chave, json.dumps(valor), agora)
                for chave, valor in salvas.items()
            ],
        )
    return salvas
