# -*- coding: utf-8 -*-
"""
database.py
============
Persistencia SQLite do historico de leituras, configuracoes, zonas Modbus e
equipamentos.

Todas as operacoes passam por `_conexao()`, que serializa o acesso no processo,
ativa WAL, aplica timeout de lock, garante commit/rollback e fecha a conexao.
Configuracoes persistidas sao sempre sanitizadas em leitura e escrita; valores
invalidos voltam ao padrao seguro da chave.
"""

from __future__ import annotations

import datetime
import json
import os
import re
import sqlite3
import threading
from contextlib import contextmanager, nullcontext
from typing import Iterator

from . import thermal_indices as ti

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INSTANCE_DIR = os.path.join(PROJECT_ROOT, "instance")
DB_PATH = os.path.join(INSTANCE_DIR, "historico.db")

# So serializa ESCRITAS (INSERT/UPDATE/DELETE/DDL) entre threads deste
# processo. Leituras (`_conexao(escrita=False)`) nao adquirem nada: em modo
# WAL (ver `iniciar_banco`) leitores concorrentes tem sua propria snapshot e
# nao bloqueiam nem sao bloqueados por um escritor, entao serializa-las so
# custaria latencia sem trazer nenhum ganho de seguranca.
_write_lock = threading.Lock()
_SEM_LOCK = nullcontext()
INTERVALO_MINIMO_LEITURAS = datetime.timedelta(minutes=1)

# Tempo (segundos) que uma conexao espera por um lock antes de desistir com
# "database is locked". O `_write_lock` ja serializa escritas dentro do MESMO
# processo; este timeout cobre o caso de outro processo (ex.: uma ferramenta
# externa) escrevendo no mesmo arquivo ao mesmo tempo.
TIMEOUT_CONEXAO_SEGUNDOS = 30.0

MODOS_OPERACAO = ("desligado", "manual", "automatico", "manutencao")
MODO_OPERACAO_PADRAO = "manual"
_NAO_INFORMADO = object()

CONFIGURACOES_PADRAO = {
    "coletarDados": False,
    "habilitarSons": False,
    "enviarEmails": False,
    "habilitarEquipamentos": False,
    "emailDestino": "produtor@fazenda.com.br",
    "statusMinimoEmail": "conforto",
    "modoAutomatico": False,
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
    # para host/usuario/senha significa "nao configurado".
    "smtpHost": "",
    "smtpPorta": 587,
    "smtpUsuario": "",
    "smtpSenha": "",
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


@contextmanager
def _conexao(*, escrita: bool = True) -> Iterator[sqlite3.Connection]:
    """Abre uma conexao SQLite, garante commit em caso de sucesso (ou
    rollback em caso de excecao) e SEMPRE fecha a conexao ao final.

    `escrita=True` (padrao, e o unico modo usado antes desta versao) serializa
    a conexao com qualquer outra escrita em andamento neste processo por meio
    de `_write_lock`. Isso e o que garante a "unicidade" logica de operacoes
    como "verificar se a zona existe e, se sim, inserir o equipamento":
    quando o codigo-chamador faz a checagem e a mutacao dentro do MESMO bloco
    `with _conexao() as conn:`, nenhuma outra thread consegue intercalar uma
    mudanca no meio do caminho (ver `criar_equipamento`, `atualizar_zona`,
    `atualizar_equipamento` e `salvar_configuracoes`).

    `escrita=False` e usado pelas funcoes somente-leitura (`obter_*`,
    `listar_*`, `contar_*`): elas dispensam o lock, permitindo que varias
    leituras concorrentes (ex.: o dashboard consultando o historico enquanto
    o modo automatico grava uma leitura) rodem em paralelo de verdade."""
    lock = _write_lock if escrita else _SEM_LOCK
    with lock:
        diretorio_banco = os.path.dirname(DB_PATH)
        if diretorio_banco:
            os.makedirs(diretorio_banco, exist_ok=True)
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


_TABELAS_CONHECIDAS = frozenset(
    {"leituras", "zonas", "equipamentos", "configuracoes", "estado_equipamentos"}
)


def _coluna_existe(conn: sqlite3.Connection, tabela: str, coluna: str) -> bool:
    # `tabela` nunca vem de entrada externa hoje, mas o allowlist evita que
    # um uso futuro descuidado (ex.: nome de tabela vindo de uma variavel
    # nao confiavel) abra uma brecha de injecao de SQL via f-string.
    if tabela not in _TABELAS_CONHECIDAS:
        raise ValueError(f"Tabela desconhecida: {tabela!r}")
    linhas = conn.execute(f"PRAGMA table_info({tabela})").fetchall()
    return any(linha["name"] == coluna for linha in linhas)


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

        # --- Zonas Modbus -------------------------------------------------
        # Uma zona agrupa N sensores + N ventiladores + N nebulizadores
        # (0 a N de cada) conectados via Modbus, e tem sua propria
        # especie/indice configurados -- o calculo do indice passa a ser
        # por zona, com a leitura de cada campo sendo a MEDIA de todos os
        # sensores daquela zona que medem aquele campo (ver ZonaService).
        # Criadas ANTES da migracao de `leituras.zona_id` logo abaixo, ja
        # que essa coluna referencia `zonas(id)`.
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS zonas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT NOT NULL,
                especie TEXT NOT NULL,
                indice TEXT NOT NULL,
                ativa INTEGER NOT NULL DEFAULT 1,
                criado_em TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS equipamentos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                zona_id INTEGER NOT NULL REFERENCES zonas(id) ON DELETE CASCADE,
                tipo TEXT NOT NULL,
                nome TEXT NOT NULL,
                modo_conexao TEXT NOT NULL,
                host TEXT,
                porta INTEGER,
                porta_serial TEXT,
                baud_rate INTEGER,
                unidade_id INTEGER NOT NULL DEFAULT 1,
                tipo_registrador TEXT NOT NULL,
                endereco_registrador INTEGER NOT NULL,
                tipo_dado TEXT NOT NULL DEFAULT 'int16',
                fator_escala REAL NOT NULL DEFAULT 1.0,
                campo_medido TEXT,
                criado_em TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_equipamentos_zona_id ON equipamentos (zona_id)"
        )
        # Usado por `listar_zonas(apenas_ativas=True)` (calculo automatico e
        # manual, que so processam zonas ativas -- ver web.py).
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_zonas_ativa ON zonas (ativa)"
        )

        # Estado ATUAL (ligado/desligado, intensidade) dos atuadores de cada
        # zona, persistido a cada ciclo de calculo por
        # `salvar_estado_equipamentos` (ver `zona_service.ZonaService.
        # calcular`). Uma linha por zona (a PK e o proprio `zona_id`; cada
        # gravacao faz UPSERT, nunca acumula historico aqui -- para isso
        # existe a tabela `leituras`). Existe para que o "Painel executivo
        # por zona" (`obter_painel_zonas`) saiba quantos equipamentos estao
        # ligados sem depender do estado em memoria do processo que roda a
        # malha de controle -- essencial a partir do momento em que o
        # dashboard (leitura) e o coletor (controle) passam a rodar em
        # processos separados (ver agents.md, secao de arquitetura).
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS estado_equipamentos (
                zona_id INTEGER PRIMARY KEY REFERENCES zonas(id) ON DELETE CASCADE,
                ventilador_ligado INTEGER NOT NULL DEFAULT 0,
                nebulizador_ligado INTEGER NOT NULL DEFAULT 0,
                intensidade TEXT,
                atualizado_em TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS controle_zonas (
                zona_id INTEGER PRIMARY KEY REFERENCES zonas(id) ON DELETE CASCADE,
                modo TEXT NOT NULL DEFAULT 'manual',
                acionamento_habilitado INTEGER NOT NULL DEFAULT 0,
                atualizado_em TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS estado_coletor (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                status TEXT NOT NULL,
                iniciado_em TEXT,
                heartbeat_em TEXT,
                ultimo_ciclo_em TEXT,
                proximo_ciclo_em TEXT,
                erro TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS eventos_operacao (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                zona_id INTEGER REFERENCES zonas(id) ON DELETE SET NULL,
                tipo TEXT NOT NULL,
                acao TEXT NOT NULL,
                detalhes TEXT NOT NULL,
                criado_em TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_eventos_operacao_zona_id "
            "ON eventos_operacao (zona_id, id)"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS leituras_recentes_zona (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                zona_id INTEGER NOT NULL REFERENCES zonas(id) ON DELETE CASCADE,
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
            "CREATE INDEX IF NOT EXISTS idx_leituras_recentes_zona_id "
            "ON leituras_recentes_zona (zona_id, id)"
        )

        # Evolucao do resumo legado para distinguir aquilo que o algoritmo
        # pediu daquilo que o equipamento realmente confirmou. Instalacoes
        # existentes recebem as colunas sem perder o estado ja persistido.
        colunas_estado = {
            "ventilador_desejado": "INTEGER",
            "nebulizador_desejado": "INTEGER",
            "ventilador_confirmado": "INTEGER",
            "nebulizador_confirmado": "INTEGER",
            "falhas": "TEXT NOT NULL DEFAULT '[]'",
            "qualidade": "TEXT NOT NULL DEFAULT 'sem_leitura'",
            "ultimo_ciclo_em": "TEXT",
        }
        for coluna, definicao in colunas_estado.items():
            if not _coluna_existe(conn, "estado_equipamentos", coluna):
                conn.execute(
                    f"ALTER TABLE estado_equipamentos ADD COLUMN {coluna} {definicao}"
                )

        # MIGRACAO: `zona_id` foi adicionado depois que a tabela `leituras`
        # ja existia em instalacoes anteriores (recurso de Zonas Modbus).
        # SQLite nao tem "ADD COLUMN IF NOT EXISTS", entao checamos manual.
        # Nulo para leituras existentes sem zona associada e para qualquer
        # leitura fora do fluxo de zonas.
        if not _coluna_existe(conn, "leituras", "zona_id"):
            conn.execute(
                "ALTER TABLE leituras ADD COLUMN zona_id INTEGER "
                "REFERENCES zonas(id) ON DELETE SET NULL"
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
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_leituras_zona_indice_id "
            "ON leituras (zona_id, indice, id)"
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
    zona_id: int | None = None,
) -> bool:
    """Grava uma leitura no historico. `zona_id` e opcional (None para o
    fluxo manual/simulado original -- Principal). Quando informado, o
    intervalo minimo entre gravacoes e verificado por (zona_id, indice),
    nao por (especie, indice): duas zonas com a mesma especie/indice nao
    devem se bloquear mutuamente, e uma leitura manual feita entre duas
    leituras automaticas da zona tambem nao deve interferir no intervalo
    da zona (por isso o fluxo manual so olha para linhas com
    `zona_id IS NULL` ao checar seu proprio intervalo)."""
    agora = datetime.datetime.now().replace(microsecond=0)
    intervalo_minimo = _intervalo_minimo_leituras(intervalo_minutos)
    with _conexao() as conn:
        if zona_id is not None:
            ultima = conn.execute(
                "SELECT criado_em FROM leituras WHERE zona_id = ? AND indice = ? "
                "ORDER BY id DESC LIMIT 1",
                (zona_id, indice),
            ).fetchone()
        else:
            ultima = conn.execute(
                "SELECT criado_em FROM leituras WHERE especie = ? AND indice = ? "
                "AND zona_id IS NULL ORDER BY id DESC LIMIT 1",
                (especie, indice),
            ).fetchone()
        if ultima:
            ultima_data = datetime.datetime.fromisoformat(ultima["criado_em"])
            if agora - ultima_data < intervalo_minimo:
                return False

        conn.execute(
            "INSERT INTO leituras (especie, indice, valor, status, entradas, criado_em, zona_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                especie,
                indice,
                valor,
                status,
                json.dumps(entradas),
                agora.isoformat(timespec="seconds"),
                zona_id,
            ),
        )
    return True


def obter_historico(especie: str, indice: str, limite: int = 20) -> list[dict]:
    with _conexao(escrita=False) as conn:
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


def obter_historico_por_zona(zona_id: int, limite: int = 20) -> list[dict]:
    """Mesma consulta de `obter_historico`, mas filtrando pela zona (em vez
    de por especie/indice) -- usado pela aba Zonas para mostrar o
    historico de uma zona especifica, isolado de leituras manuais/de
    outras zonas que porventura compartilhem a mesma especie/indice."""
    with _conexao(escrita=False) as conn:
        linhas = conn.execute(
            "SELECT * FROM leituras WHERE zona_id = ? ORDER BY id DESC LIMIT ?",
            (zona_id, limite),
        ).fetchall()
    dados = [dict(linha) for linha in linhas]
    dados.reverse()
    for item in dados:
        item["entradas"] = json.loads(item["entradas"])
    return dados


def salvar_leitura_recente_zona(
    zona_id: int,
    especie: str,
    indice: str,
    valor: float,
    status: str,
    entradas: dict,
    limite: int = 30,
) -> None:
    """Mantem uma janela curta para graficos entre processos separados."""
    agora = datetime.datetime.now().replace(microsecond=0).isoformat(timespec="seconds")
    limite = max(1, min(200, int(limite)))
    with _conexao() as conn:
        conn.execute(
            """
            INSERT INTO leituras_recentes_zona
                (zona_id, especie, indice, valor, status, entradas, criado_em)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (zona_id, especie, indice, valor, status, json.dumps(entradas), agora),
        )
        conn.execute(
            """
            DELETE FROM leituras_recentes_zona
            WHERE zona_id = ? AND id NOT IN (
                SELECT id FROM leituras_recentes_zona
                WHERE zona_id = ? ORDER BY id DESC LIMIT ?
            )
            """,
            (zona_id, zona_id, limite),
        )


def obter_leituras_recentes_zona(zona_id: int, limite: int = 30) -> list[dict]:
    limite = max(1, min(200, int(limite)))
    with _conexao(escrita=False) as conn:
        linhas = conn.execute(
            """
            SELECT * FROM leituras_recentes_zona
            WHERE zona_id = ? ORDER BY id DESC LIMIT ?
            """,
            (zona_id, limite),
        ).fetchall()
    dados = [dict(linha) for linha in reversed(linhas)]
    for item in dados:
        item["entradas"] = json.loads(item["entradas"])
    return dados


def obter_historico_leituras(
    limite: int = 30,
    deslocamento: int | None = None,
    zona_id: int | None = None,
    indice: str | None = None,
    status: str | None = None,
) -> dict:
    """Consulta paginada do historico persistido.

    Diferente de `obter_historico_por_zona`, que alimenta os graficos curtos
    em memoria da Dashboard, esta funcao navega pela tabela `leituras` em
    ordem cronologica e devolve metadados suficientes para a interface montar
    um controle de avanco/retrocesso sobre o banco inteiro.
    """
    limite = max(1, min(200, int(limite)))
    filtros = []
    parametros: list = []

    if zona_id is not None:
        filtros.append("l.zona_id = ?")
        parametros.append(zona_id)
    if indice:
        filtros.append("l.indice = ?")
        parametros.append(indice)
    if status:
        filtros.append("l.status = ?")
        parametros.append(status)

    where = ("WHERE " + " AND ".join(filtros)) if filtros else ""
    with _conexao(escrita=False) as conn:
        (total,) = conn.execute(
            f"SELECT COUNT(*) FROM leituras l {where}",
            parametros,
        ).fetchone()

        if deslocamento is None:
            deslocamento_calculado = max(0, total - limite)
        else:
            deslocamento_calculado = max(0, min(int(deslocamento), max(0, total - limite)))

        linhas = conn.execute(
            f"""
            SELECT l.*, z.nome AS zona_nome
            FROM leituras l
            LEFT JOIN zonas z ON z.id = l.zona_id
            {where}
            ORDER BY l.id ASC
            LIMIT ? OFFSET ?
            """,
            [*parametros, limite, deslocamento_calculado],
        ).fetchall()

    leituras = [dict(linha) for linha in linhas]
    for item in leituras:
        item["entradas"] = json.loads(item["entradas"])
    return {
        "leituras": leituras,
        "total": total,
        "limite": limite,
        "deslocamento": deslocamento_calculado,
    }


def limpar_historico(especie: str | None = None, indice: str | None = None) -> None:
    with _conexao() as conn:
        if especie and indice:
            conn.execute(
                "DELETE FROM leituras WHERE especie = ? AND indice = ?", (especie, indice)
            )
            conn.execute(
                "DELETE FROM leituras_recentes_zona WHERE especie = ? AND indice = ?",
                (especie, indice),
            )
        elif especie:
            conn.execute("DELETE FROM leituras WHERE especie = ?", (especie,))
            conn.execute("DELETE FROM leituras_recentes_zona WHERE especie = ?", (especie,))
        else:
            conn.execute("DELETE FROM leituras")
            conn.execute("DELETE FROM leituras_recentes_zona")


def criar_backup_banco() -> dict:
    """Cria um backup consistente do SQLite no mesmo diretorio do banco."""
    diretorio = os.path.dirname(DB_PATH)
    nome_base = os.path.splitext(os.path.basename(DB_PATH))[0] or "historico"
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    caminho_backup = os.path.join(diretorio, f"{nome_base}_backup_{timestamp}.db")

    # Usa o mesmo lock de escrita (nao `_conexao()`) porque `Connection.backup`
    # gerencia suas proprias transacoes na origem e no destino; so precisamos
    # garantir que nenhuma escrita deste processo comece no meio da copia.
    with _write_lock:
        origem = sqlite3.connect(DB_PATH, timeout=TIMEOUT_CONEXAO_SEGUNDOS)
        destino = sqlite3.connect(caminho_backup)
        try:
            origem.backup(destino)
        finally:
            destino.close()
            origem.close()

    return {
        "arquivo": os.path.basename(caminho_backup),
        "caminho": caminho_backup,
        "tamanho_bytes": os.path.getsize(caminho_backup),
    }


def salvar_estado_equipamentos(
    zona_id: int,
    ventilador_ligado: bool,
    nebulizador_ligado: bool,
    intensidade: str | None,
    ventilador_desejado=_NAO_INFORMADO,
    nebulizador_desejado=_NAO_INFORMADO,
    ventilador_confirmado=_NAO_INFORMADO,
    nebulizador_confirmado=_NAO_INFORMADO,
    falhas: list[str] | None = None,
    qualidade: str = "boa",
) -> None:
    """Persiste estado desejado, confirmado e qualidade do ultimo ciclo.

    Os quatro primeiros argumentos preservam o contrato anterior. Quando os
    novos campos nao sao informados, o estado legado e tratado como desejado
    e confirmado; quando a confirmacao e explicitamente ``None``, a interface
    mostra que houve comando sem realimentacao disponivel.
    """
    if ventilador_desejado is _NAO_INFORMADO:
        ventilador_desejado = bool(ventilador_ligado)
    if nebulizador_desejado is _NAO_INFORMADO:
        nebulizador_desejado = bool(nebulizador_ligado)
    if ventilador_confirmado is _NAO_INFORMADO:
        ventilador_confirmado = bool(ventilador_ligado)
    if nebulizador_confirmado is _NAO_INFORMADO:
        nebulizador_confirmado = bool(nebulizador_ligado)

    def _bool_sql(valor):
        return None if valor is None else int(bool(valor))

    agora = datetime.datetime.now().replace(microsecond=0).isoformat(timespec="seconds")
    with _conexao() as conn:
        conn.execute(
            """
            INSERT INTO estado_equipamentos
                (zona_id, ventilador_ligado, nebulizador_ligado, intensidade, atualizado_em,
                 ventilador_desejado, nebulizador_desejado,
                 ventilador_confirmado, nebulizador_confirmado,
                 falhas, qualidade, ultimo_ciclo_em)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(zona_id) DO UPDATE SET
                ventilador_ligado = excluded.ventilador_ligado,
                nebulizador_ligado = excluded.nebulizador_ligado,
                intensidade = excluded.intensidade,
                atualizado_em = excluded.atualizado_em,
                ventilador_desejado = excluded.ventilador_desejado,
                nebulizador_desejado = excluded.nebulizador_desejado,
                ventilador_confirmado = excluded.ventilador_confirmado,
                nebulizador_confirmado = excluded.nebulizador_confirmado,
                falhas = excluded.falhas,
                qualidade = excluded.qualidade,
                ultimo_ciclo_em = excluded.ultimo_ciclo_em
            """,
            (
                zona_id,
                int(bool(ventilador_confirmado)) if ventilador_confirmado is not None else 0,
                int(bool(nebulizador_confirmado)) if nebulizador_confirmado is not None else 0,
                intensidade,
                agora,
                _bool_sql(ventilador_desejado),
                _bool_sql(nebulizador_desejado),
                _bool_sql(ventilador_confirmado),
                _bool_sql(nebulizador_confirmado),
                json.dumps(falhas or []),
                qualidade,
                agora,
            ),
        )


def salvar_comando_manual_atuador(
    zona_id: int,
    tipo: str,
    desejado: bool,
    confirmado: bool | None,
    falhas: list[str] | None = None,
) -> None:
    """Atualiza apenas o atuador comandado, preservando o outro grupo."""
    if tipo not in ("ventilador", "nebulizador"):
        raise ValueError("Tipo de atuador invalido.")
    agora = datetime.datetime.now().replace(microsecond=0).isoformat(timespec="seconds")
    coluna_desejada = f"{tipo}_desejado"
    coluna_confirmada = f"{tipo}_confirmado"
    coluna_legada = f"{tipo}_ligado"
    qualidade = "boa" if not falhas else "degradada"

    with _conexao() as conn:
        conn.execute(
            """
            INSERT INTO estado_equipamentos
                (zona_id, ventilador_ligado, nebulizador_ligado, intensidade,
                 atualizado_em, ventilador_desejado, nebulizador_desejado,
                 ventilador_confirmado, nebulizador_confirmado, falhas,
                 qualidade, ultimo_ciclo_em)
            VALUES (?, 0, 0, 'manual', ?, 0, 0, NULL, NULL, ?, ?, ?)
            ON CONFLICT(zona_id) DO NOTHING
            """,
            (zona_id, agora, json.dumps(falhas or []), qualidade, agora),
        )
        # Os nomes de coluna nunca vem de entrada externa: foram escolhidos
        # pelo allowlist de ``tipo`` acima.
        conn.execute(
            f"""
            UPDATE estado_equipamentos
            SET {coluna_desejada} = ?,
                {coluna_confirmada} = ?,
                {coluna_legada} = ?,
                intensidade = 'manual',
                falhas = ?, qualidade = ?,
                atualizado_em = ?, ultimo_ciclo_em = ?
            WHERE zona_id = ?
            """,
            (
                int(desejado),
                None if confirmado is None else int(confirmado),
                int(bool(confirmado)) if confirmado is not None else 0,
                json.dumps(falhas or []),
                qualidade,
                agora,
                agora,
                zona_id,
            ),
        )


def registrar_falha_operacional_zona(zona_id: int, mensagem: str) -> None:
    """Marca falha do ciclo sem inventar um novo estado dos equipamentos."""
    agora = datetime.datetime.now().replace(microsecond=0).isoformat(timespec="seconds")
    with _conexao() as conn:
        conn.execute(
            """
            INSERT INTO estado_equipamentos
                (zona_id, ventilador_ligado, nebulizador_ligado, intensidade,
                 atualizado_em, falhas, qualidade, ultimo_ciclo_em)
            VALUES (?, 0, 0, NULL, ?, ?, 'falha', ?)
            ON CONFLICT(zona_id) DO UPDATE SET
                falhas = excluded.falhas,
                qualidade = excluded.qualidade,
                atualizado_em = excluded.atualizado_em,
                ultimo_ciclo_em = excluded.ultimo_ciclo_em
            """,
            (zona_id, agora, json.dumps([mensagem]), agora),
        )


def salvar_status_coletor(
    status: str,
    *,
    iniciado_em: str | None = None,
    ultimo_ciclo_em: str | None = None,
    proximo_ciclo_em: str | None = None,
    erro: str | None = None,
) -> dict:
    agora = datetime.datetime.now().replace(microsecond=0).isoformat(timespec="seconds")
    with _conexao() as conn:
        atual = conn.execute("SELECT * FROM estado_coletor WHERE id = 1").fetchone()
        inicio = iniciado_em or (atual["iniciado_em"] if atual else None) or agora
        ultimo = ultimo_ciclo_em or (atual["ultimo_ciclo_em"] if atual else None)
        conn.execute(
            """
            INSERT INTO estado_coletor
                (id, status, iniciado_em, heartbeat_em, ultimo_ciclo_em, proximo_ciclo_em, erro)
            VALUES (1, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                status = excluded.status,
                iniciado_em = excluded.iniciado_em,
                heartbeat_em = excluded.heartbeat_em,
                ultimo_ciclo_em = excluded.ultimo_ciclo_em,
                proximo_ciclo_em = excluded.proximo_ciclo_em,
                erro = excluded.erro
            """,
            (status, inicio, agora, ultimo, proximo_ciclo_em, erro),
        )
    return {
        "status": status,
        "iniciado_em": inicio,
        "heartbeat_em": agora,
        "ultimo_ciclo_em": ultimo,
        "proximo_ciclo_em": proximo_ciclo_em,
        "erro": erro,
    }


def obter_status_coletor() -> dict:
    with _conexao(escrita=False) as conn:
        linha = conn.execute("SELECT * FROM estado_coletor WHERE id = 1").fetchone()
    if linha is None:
        return {
            "status": "offline",
            "online": False,
            "iniciado_em": None,
            "heartbeat_em": None,
            "ultimo_ciclo_em": None,
            "proximo_ciclo_em": None,
            "erro": None,
        }

    dados = dict(linha)
    heartbeat = datetime.datetime.fromisoformat(dados["heartbeat_em"])
    intervalo = float(obter_configuracoes().get("intervaloLeituraSegundos") or 1)
    limite = datetime.timedelta(seconds=max(10.0, intervalo * 3))
    dados["online"] = (
        dados["status"] == "online" and datetime.datetime.now() - heartbeat <= limite
    )
    if not dados["online"] and dados["status"] == "online":
        dados["status"] = "sem_heartbeat"
    dados.pop("id", None)
    return dados


def registrar_evento_operacao(
    tipo: str, acao: str, *, zona_id: int | None = None, detalhes: dict | None = None
) -> None:
    agora = datetime.datetime.now().replace(microsecond=0).isoformat(timespec="seconds")
    with _conexao() as conn:
        conn.execute(
            "INSERT INTO eventos_operacao (zona_id, tipo, acao, detalhes, criado_em) "
            "VALUES (?, ?, ?, ?, ?)",
            (zona_id, tipo, acao, json.dumps(detalhes or {}), agora),
        )


def listar_eventos_operacao(zona_id: int | None = None, limite: int = 30) -> list[dict]:
    filtro = "WHERE zona_id = ?" if zona_id is not None else ""
    parametros = (zona_id, limite) if zona_id is not None else (limite,)
    with _conexao(escrita=False) as conn:
        linhas = conn.execute(
            f"SELECT * FROM eventos_operacao {filtro} ORDER BY id DESC LIMIT ?",
            parametros,
        ).fetchall()
    resultado = []
    for linha in linhas:
        item = dict(linha)
        item["detalhes"] = json.loads(item["detalhes"])
        resultado.append(item)
    return resultado


def contar_leituras() -> int:
    """Utilitario de diagnostico: total de linhas gravadas na tabela."""
    with _conexao(escrita=False) as conn:
        (total,) = conn.execute("SELECT COUNT(*) FROM leituras").fetchone()
    return total


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

TIPOS_EQUIPAMENTO = ("sensor", "ventilador", "nebulizador")
MODOS_CONEXAO = ("tcp", "rtu")
TIPOS_DADO = ("int16", "uint16", "float32")
CAMPOS_MEDIVEIS = tuple(ti.CAMPO_METADADOS.keys())


class ZonaInvalidaError(ValueError):
    """Erro de validacao ao criar/atualizar uma zona ou equipamento Modbus."""


class ZonaNaoEncontradaError(ZonaInvalidaError):
    """Subclasse especifica para "zona_id nao existe", usada por
    `criar_equipamento`. Existe para que a camada HTTP (web.py) saiba
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

    acionamento = dados.get(
        "acionamento_habilitado", atual["acionamento_habilitado"]
    )
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
        "ativa": _coagir_booleano(dados.get("ativa", True), True),
    }


def _validar_equipamento(dados: dict) -> dict:
    tipo = dados.get("tipo")
    if tipo not in TIPOS_EQUIPAMENTO:
        raise ZonaInvalidaError(
            f"Tipo de equipamento inválido: {tipo!r} (esperado um de {TIPOS_EQUIPAMENTO})."
        )

    nome = str(dados.get("nome", "")).strip()
    if not nome:
        raise ZonaInvalidaError("Informe um nome para o equipamento.")

    modo_conexao = dados.get("modo_conexao")
    if modo_conexao not in MODOS_CONEXAO:
        raise ZonaInvalidaError(
            f"Modo de conexão inválido: {modo_conexao!r} (esperado 'tcp' ou 'rtu')."
        )

    host = porta = porta_serial = baud_rate = None
    if modo_conexao == "tcp":
        host = str(dados.get("host", "")).strip()
        if not host:
            raise ZonaInvalidaError("Informe o host/IP para conexão Modbus TCP.")
        porta = _validar_inteiro(dados.get("porta", 502), "porta", 1, 65535)
    else:
        porta_serial = str(dados.get("porta_serial", "")).strip()
        if not porta_serial:
            raise ZonaInvalidaError(
                "Informe a porta serial (ex.: /dev/ttyUSB0 ou COM3) para conexão Modbus RTU."
            )
        baud_rate = _validar_inteiro(dados.get("baud_rate", 9600), "baud_rate", 300, 921600)

    unidade_id = _validar_inteiro(dados.get("unidade_id", 1), "unidade_id", 1, 247)

    registradores_validos = ("holding", "input") if tipo == "sensor" else ("holding", "coil")
    tipo_registrador = dados.get("tipo_registrador")
    if tipo_registrador not in registradores_validos:
        raise ZonaInvalidaError(
            f"Tipo de registrador inválido para {tipo}: {tipo_registrador!r} "
            f"(esperado um de {registradores_validos})."
        )

    endereco_registrador = _validar_inteiro(
        dados.get("endereco_registrador"), "endereco_registrador", 0, 65535
    )

    tipo_dado = dados.get("tipo_dado", "int16")
    if tipo_dado not in TIPOS_DADO:
        raise ZonaInvalidaError(f"Tipo de dado inválido: {tipo_dado!r} (esperado um de {TIPOS_DADO}).")

    fator_escala = _validar_numero(dados.get("fator_escala", 1.0), "fator_escala")
    if fator_escala == 0:
        raise ZonaInvalidaError("O fator de escala não pode ser zero.")

    campo_medido = dados.get("campo_medido")
    if tipo == "sensor":
        if campo_medido not in CAMPOS_MEDIVEIS:
            raise ZonaInvalidaError(
                f"Campo medido inválido para sensor: {campo_medido!r} "
                f"(esperado um de {CAMPOS_MEDIVEIS})."
            )
    else:
        campo_medido = None

    return {
        "tipo": tipo,
        "nome": nome[:255],
        "modo_conexao": modo_conexao,
        "host": host,
        "porta": porta,
        "porta_serial": porta_serial,
        "baud_rate": baud_rate,
        "unidade_id": unidade_id,
        "tipo_registrador": tipo_registrador,
        "endereco_registrador": endereco_registrador,
        "tipo_dado": tipo_dado,
        "fator_escala": fator_escala,
        "campo_medido": campo_medido,
    }


def criar_zona(dados: dict) -> dict:
    validado = _validar_zona(dados)
    agora = datetime.datetime.now().replace(microsecond=0).isoformat(timespec="seconds")
    with _conexao() as conn:
        cursor = conn.execute(
            "INSERT INTO zonas (nome, especie, indice, ativa, criado_em) VALUES (?, ?, ?, ?, ?)",
            (validado["nome"], validado["especie"], validado["indice"], int(validado["ativa"]), agora),
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
        "criado_em": agora,
        "equipamentos": [],
        "controle": {
            "modo": MODO_OPERACAO_PADRAO,
            "acionamento_habilitado": False,
            "atualizado_em": agora,
        },
    }


def listar_zonas(*, apenas_ativas: bool = False) -> list[dict]:
    filtro = "WHERE ativa = 1" if apenas_ativas else ""
    with _conexao(escrita=False) as conn:
        linhas_zonas = conn.execute(f"SELECT * FROM zonas {filtro} ORDER BY id").fetchall()
        # Uma unica consulta para os equipamentos de TODAS as zonas, em vez
        # de uma consulta por zona (N+1): antes, listar 20 zonas abria 21
        # conexoes/consultas; agora abre so 2, dentro da mesma conexao.
        linhas_equipamentos = conn.execute(
            "SELECT * FROM equipamentos ORDER BY zona_id, tipo, id"
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
        "acionamento_habilitado": bool(controle["acionamento_habilitado"])
        if controle
        else False,
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

    resultado = []
    for zona in zonas:
        estado = estados.get(zona["id"], {})
        falhas = estado.get("falhas") or "[]"
        try:
            falhas = json.loads(falhas)
        except (TypeError, json.JSONDecodeError):
            falhas = []
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
                "qualidade": estado.get("qualidade") or "sem_leitura",
                "falhas": falhas,
                "ultimo_ciclo_em": estado.get("ultimo_ciclo_em"),
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
            "UPDATE zonas SET nome = ?, especie = ?, indice = ?, ativa = ? WHERE id = ?",
            (validado["nome"], validado["especie"], validado["indice"], int(validado["ativa"]), zona_id),
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
        "acionamento_habilitado": bool(controle["acionamento_habilitado"])
        if controle
        else False,
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
    return cursor.rowcount > 0


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
        zonas = conn.execute(
            "SELECT id, nome, especie, indice FROM zonas ORDER BY id"
        ).fetchall()
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
        zonas = conn.execute(
            "SELECT id, nome, especie, indice FROM zonas ORDER BY id"
        ).fetchall()
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
        leituras_por_zona: dict[int, list[sqlite3.Row]] = {}
        for zona in zonas:
            leituras_por_zona[zona["id"]] = list(
                reversed(
                    conn.execute(
                        "SELECT valor, status, entradas, criado_em FROM leituras "
                        "WHERE zona_id = ? AND indice = ? ORDER BY id DESC LIMIT ?",
                        (zona["id"], zona["indice"], LIMITE_LEITURAS_PAINEL_EXECUTIVO),
                    ).fetchall()
                )
            )

    sensores_por_zona: dict[int, list[sqlite3.Row]] = {}
    for linha in linhas_sensores:
        sensores_por_zona.setdefault(linha["zona_id"], []).append(linha)

    totais_por_zona: dict[int, dict[str, int]] = {}
    for linha in linhas_atuadores:
        totais_por_zona.setdefault(linha["zona_id"], {"ventilador": 0, "nebulizador": 0})
        totais_por_zona[linha["zona_id"]][linha["tipo"]] = linha["total"]

    estado_por_zona: dict[int, sqlite3.Row] = {linha["zona_id"]: linha for linha in linhas_estado}

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
    zona: sqlite3.Row,
    leituras: list[sqlite3.Row],
    sensores: list[sqlite3.Row],
    totais_equipamento: dict[str, int],
    estado_atuadores: sqlite3.Row | None,
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

    ultima = leituras[-1]
    ultima_dt = datetime.datetime.fromisoformat(ultima["criado_em"])
    base["status_atual"] = ultima["status"]
    base["valor_atual"] = round(ultima["valor"], 2)
    base["ultima_leitura_em"] = ultima["criado_em"]

    def _valor_referencia(minutos: int) -> float | None:
        alvo = ultima_dt - datetime.timedelta(minutes=minutos)
        candidato = None
        for linha in leituras:
            if datetime.datetime.fromisoformat(linha["criado_em"]) <= alvo:
                candidato = linha
            else:
                break
        return candidato["valor"] if candidato is not None else None

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
    leituras_24h = [
        l for l in leituras if datetime.datetime.fromisoformat(l["criado_em"]) >= corte_24h
    ]
    if leituras_24h:
        conforto = sum(1 for l in leituras_24h if l["status"] == "Conforto")
        base["percentual_conforto_24h"] = round(100 * conforto / len(leituras_24h), 1)
    else:
        base["percentual_conforto_24h"] = None

    # Tempo continuo no status atual: anda para tras a partir da leitura
    # mais recente enquanto o status nao muda, e usa o inicio dessa
    # sequencia como o momento em que o status atual "comecou".
    inicio_sequencia = ultima_dt
    for linha in reversed(leituras):
        if linha["status"] != ultima["status"]:
            break
        inicio_sequencia = datetime.datetime.fromisoformat(linha["criado_em"])
    base["tempo_continuo_status_minutos"] = round(
        (agora - inicio_sequencia).total_seconds() / 60, 1
    )

    leituras_hoje = [
        l for l in leituras if datetime.datetime.fromisoformat(l["criado_em"]) >= inicio_dia
    ]
    if leituras_hoje:
        base["nivel_maximo_dia"] = max(
            leituras_hoje,
            key=lambda l: ti.STATUS_PESO[ti.normalizar_chave_texto(l["status"]).lower()],
        )["status"]
    else:
        base["nivel_maximo_dia"] = None

    # Minutos em Perigo/Emergencia hoje: integra o intervalo entre cada
    # leitura e a proxima (o status da leitura mais antiga do par "vale"
    # durante esse intervalo); o ultimo intervalo se estende ate agora,
    # para que o tempo no status atual continue contando em tempo real.
    minutos_por_status = {"Perigo": 0.0, "Emergência": 0.0}
    for posicao, linha in enumerate(leituras_hoje):
        inicio_intervalo = datetime.datetime.fromisoformat(linha["criado_em"])
        if posicao + 1 < len(leituras_hoje):
            fim_intervalo = datetime.datetime.fromisoformat(leituras_hoje[posicao + 1]["criado_em"])
        else:
            fim_intervalo = agora
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
    for linha in leituras:
        dt = datetime.datetime.fromisoformat(linha["criado_em"])
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
    campos_relevantes |= (
        {"tbs", "tbu", "ur", "tpo"} if zona["indice"] == "IGNU" else {"ur", "tpo"}
    )
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
        partes.append(
            "O índice ainda está subindo nos últimos 15 minutos: reforce o resfriamento."
        )
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


def criar_equipamento(zona_id: int, dados: dict) -> dict:
    """Confere a existencia da zona, valida os dados e insere o equipamento,

    tudo na MESMA transacao (ver a nota em `atualizar_zona` sobre por que
    checagem+mutacao precisam estar juntas). A ordem -- zona primeiro, dados
    depois -- e proposital e igual a de antes desta funcao virar uma unica
    transacao: se a zona nao existe E os dados tambem sao invalidos, quem
    chama recebe "zona não encontrada" (404), o problema mais fundamental,
    em vez de um erro de validacao dos dados de um equipamento que nem
    poderia ser criado de qualquer forma. Isso tambem elimina o round-trip
    extra que existia antes: a checagem de existencia era uma conexao
    (`obter_zona`), a insercao outra, e a releitura do resultado uma
    terceira -- agora e tudo uma unica conexao/transacao."""
    agora = datetime.datetime.now().replace(microsecond=0).isoformat(timespec="seconds")
    with _conexao() as conn:
        zona_existe = conn.execute("SELECT 1 FROM zonas WHERE id = ?", (zona_id,)).fetchone()
        if zona_existe is None:
            raise ZonaNaoEncontradaError(f"Zona {zona_id} não encontrada.")
        validado = _validar_equipamento(dados)
        cursor = conn.execute(
            """
            INSERT INTO equipamentos (
                zona_id, tipo, nome, modo_conexao, host, porta, porta_serial, baud_rate,
                unidade_id, tipo_registrador, endereco_registrador, tipo_dado, fator_escala,
                campo_medido, criado_em
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                zona_id,
                validado["tipo"],
                validado["nome"],
                validado["modo_conexao"],
                validado["host"],
                validado["porta"],
                validado["porta_serial"],
                validado["baud_rate"],
                validado["unidade_id"],
                validado["tipo_registrador"],
                validado["endereco_registrador"],
                validado["tipo_dado"],
                validado["fator_escala"],
                validado["campo_medido"],
                agora,
            ),
        )
        equipamento_id = cursor.lastrowid
        linha = conn.execute(
            "SELECT * FROM equipamentos WHERE id = ?", (equipamento_id,)
        ).fetchone()
    return dict(linha)


def obter_equipamento(equipamento_id: int) -> dict | None:
    with _conexao(escrita=False) as conn:
        linha = conn.execute(
            "SELECT * FROM equipamentos WHERE id = ?", (equipamento_id,)
        ).fetchone()
    return dict(linha) if linha else None


def atualizar_equipamento(equipamento_id: int, dados: dict) -> dict | None:
    validado = _validar_equipamento(dados)
    with _conexao() as conn:
        existe = conn.execute(
            "SELECT 1 FROM equipamentos WHERE id = ?", (equipamento_id,)
        ).fetchone()
        if existe is None:
            return None
        conn.execute(
            """
            UPDATE equipamentos SET
                tipo = ?, nome = ?, modo_conexao = ?, host = ?, porta = ?, porta_serial = ?,
                baud_rate = ?, unidade_id = ?, tipo_registrador = ?, endereco_registrador = ?,
                tipo_dado = ?, fator_escala = ?, campo_medido = ?
            WHERE id = ?
            """,
            (
                validado["tipo"],
                validado["nome"],
                validado["modo_conexao"],
                validado["host"],
                validado["porta"],
                validado["porta_serial"],
                validado["baud_rate"],
                validado["unidade_id"],
                validado["tipo_registrador"],
                validado["endereco_registrador"],
                validado["tipo_dado"],
                validado["fator_escala"],
                validado["campo_medido"],
                equipamento_id,
            ),
        )
        linha = conn.execute(
            "SELECT * FROM equipamentos WHERE id = ?", (equipamento_id,)
        ).fetchone()
    return dict(linha)


def excluir_equipamento(equipamento_id: int) -> bool:
    with _conexao() as conn:
        cursor = conn.execute("DELETE FROM equipamentos WHERE id = ?", (equipamento_id,))
    return cursor.rowcount > 0


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
        "statusMinimoEmail": _coagir_enum(
            bruto["statusMinimoEmail"],
            padrao["statusMinimoEmail"],
            tuple(ti.STATUS_PESO.keys()),
        ),
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
        "modoSimuladoZonas": _coagir_booleano(bruto["modoSimuladoZonas"], padrao["modoSimuladoZonas"]),
    }


def _decodificar_configuracoes(linhas) -> dict:
    configuracoes = dict(CONFIGURACOES_PADRAO)
    for linha in linhas:
        try:
            configuracoes[linha["chave"]] = json.loads(linha["valor"])
        except json.JSONDecodeError:
            configuracoes[linha["chave"]] = linha["valor"]
    return configuracoes


def obter_configuracoes() -> dict:
    with _conexao(escrita=False) as conn:
        linhas = conn.execute("SELECT chave, valor FROM configuracoes").fetchall()
    # Sanitiza tambem na leitura: protege contra um valor corrompido ou
    # editado manualmente no arquivo .db (defesa em profundidade -- a
    # escrita ja e validada em salvar_configuracoes).
    return _sanitizar_configuracoes(_decodificar_configuracoes(linhas))


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
    #
    # A leitura do valor atual e a escrita do valor final agora acontecem
    # dentro da MESMA transacao (mesma conexao, mesmo `with`). Antes, eram
    # duas conexoes separadas: se duas requisicoes salvassem configuracoes
    # em paralelo, uma podia ler a senha "antiga" DEPOIS que a outra ja
    # tinha calculado (mas ainda nao gravado) uma senha nova, e a gravacao
    # da primeira sobrescreveria a da segunda com um valor desatualizado
    # ("lost update" classico). Com tudo em uma transacao serializada por
    # `_write_lock`, isso deixa de ser possivel.
    agora = datetime.datetime.now().replace(microsecond=0).isoformat(timespec="seconds")
    with _conexao() as conn:
        if not str(configuracoes.get("smtpSenha", "")).strip():
            linhas = conn.execute("SELECT chave, valor FROM configuracoes").fetchall()
            configuracoes["smtpSenha"] = _decodificar_configuracoes(linhas).get("smtpSenha", "")

        salvas = _sanitizar_configuracoes(configuracoes)
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
