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
from contextlib import contextmanager
from typing import Iterator

from . import thermal_indices as ti

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INSTANCE_DIR = os.path.join(PROJECT_ROOT, "instance")
DB_PATH = os.path.join(INSTANCE_DIR, "historico.db")

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
def _conexao() -> Iterator[sqlite3.Connection]:
    """Abre uma conexao SQLite, garante commit em caso de sucesso (ou
    rollback em caso de excecao) e SEMPRE fecha a conexao ao final."""
    with _lock:
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


def _coluna_existe(conn: sqlite3.Connection, tabela: str, coluna: str) -> bool:
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


def obter_historico_por_zona(zona_id: int, limite: int = 20) -> list[dict]:
    """Mesma consulta de `obter_historico`, mas filtrando pela zona (em vez
    de por especie/indice) -- usado pela aba Zonas para mostrar o
    historico de uma zona especifica, isolado de leituras manuais/de
    outras zonas que porventura compartilhem a mesma especie/indice."""
    with _conexao() as conn:
        linhas = conn.execute(
            "SELECT * FROM leituras WHERE zona_id = ? ORDER BY id DESC LIMIT ?",
            (zona_id, limite),
        ).fetchall()
    dados = [dict(linha) for linha in linhas]
    dados.reverse()
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
    with _conexao() as conn:
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
        elif especie:
            conn.execute("DELETE FROM leituras WHERE especie = ?", (especie,))
        else:
            conn.execute("DELETE FROM leituras")


def criar_backup_banco() -> dict:
    """Cria um backup consistente do SQLite no mesmo diretorio do banco."""
    diretorio = os.path.dirname(DB_PATH)
    nome_base = os.path.splitext(os.path.basename(DB_PATH))[0] or "historico"
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    caminho_backup = os.path.join(diretorio, f"{nome_base}_backup_{timestamp}.db")

    with _lock:
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


def contar_leituras() -> int:
    """Utilitario de diagnostico: total de linhas gravadas na tabela."""
    with _conexao() as conn:
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


def _validar_inteiro(valor, nome_campo: str, minimo: int, maximo: int) -> int:
    try:
        numero = int(float(str(valor).replace(",", ".")))
    except (TypeError, ValueError):
        raise ZonaInvalidaError(f"O campo '{nome_campo}' precisa ser um número inteiro.")
    if not (minimo <= numero <= maximo):
        raise ZonaInvalidaError(f"O campo '{nome_campo}' precisa estar entre {minimo} e {maximo}.")
    return numero


def _validar_numero(valor, nome_campo: str) -> float:
    try:
        return float(str(valor).replace(",", "."))
    except (TypeError, ValueError):
        raise ZonaInvalidaError(f"O campo '{nome_campo}' precisa ser numérico.")


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
    return obter_zona(zona_id)


def listar_zonas() -> list[dict]:
    with _conexao() as conn:
        linhas = conn.execute("SELECT * FROM zonas ORDER BY id").fetchall()
    zonas = [dict(linha) for linha in linhas]
    for zona in zonas:
        zona["ativa"] = bool(zona["ativa"])
        zona["equipamentos"] = listar_equipamentos_da_zona(zona["id"])
    return zonas


def obter_zona(zona_id: int) -> dict | None:
    with _conexao() as conn:
        linha = conn.execute("SELECT * FROM zonas WHERE id = ?", (zona_id,)).fetchone()
    if not linha:
        return None
    zona = dict(linha)
    zona["ativa"] = bool(zona["ativa"])
    zona["equipamentos"] = listar_equipamentos_da_zona(zona_id)
    return zona


def atualizar_zona(zona_id: int, dados: dict) -> dict | None:
    if obter_zona(zona_id) is None:
        return None
    validado = _validar_zona(dados)
    with _conexao() as conn:
        conn.execute(
            "UPDATE zonas SET nome = ?, especie = ?, indice = ?, ativa = ? WHERE id = ?",
            (validado["nome"], validado["especie"], validado["indice"], int(validado["ativa"]), zona_id),
        )
    return obter_zona(zona_id)


def excluir_zona(zona_id: int) -> bool:
    """Remove a zona e (via ON DELETE CASCADE) seus equipamentos. O
    historico de leituras ja gravado permanece -- perder o registro
    historico so porque a zona foi reconfigurada/removida seria pior do
    que manter uma referencia a uma zona que não existe mais."""
    with _conexao() as conn:
        cursor = conn.execute("DELETE FROM zonas WHERE id = ?", (zona_id,))
    return cursor.rowcount > 0


def criar_equipamento(zona_id: int, dados: dict) -> dict:
    if obter_zona(zona_id) is None:
        raise ZonaInvalidaError(f"Zona {zona_id} não encontrada.")
    validado = _validar_equipamento(dados)
    agora = datetime.datetime.now().replace(microsecond=0).isoformat(timespec="seconds")
    with _conexao() as conn:
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
    return obter_equipamento(equipamento_id)


def listar_equipamentos_da_zona(zona_id: int) -> list[dict]:
    with _conexao() as conn:
        linhas = conn.execute(
            "SELECT * FROM equipamentos WHERE zona_id = ? ORDER BY tipo, id", (zona_id,)
        ).fetchall()
    return [dict(linha) for linha in linhas]


def obter_equipamento(equipamento_id: int) -> dict | None:
    with _conexao() as conn:
        linha = conn.execute(
            "SELECT * FROM equipamentos WHERE id = ?", (equipamento_id,)
        ).fetchone()
    return dict(linha) if linha else None


def atualizar_equipamento(equipamento_id: int, dados: dict) -> dict | None:
    if obter_equipamento(equipamento_id) is None:
        return None
    validado = _validar_equipamento(dados)
    with _conexao() as conn:
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
    return obter_equipamento(equipamento_id)


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
