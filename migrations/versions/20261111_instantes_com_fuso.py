"""Colunas de instante deixam de ser TEXT: viram `timestamptz` (e `date`).

O banco guardava instantes como texto em três formatos que conviviam nas mesmas
tabelas: hora local sem offset (`2026-11-11T10:00:00`, de `datetime.now()` do
contêiner), UTC sem offset (janelas e horas agregadas) e UTC com `+00:00`.
Comparar, ordenar e agrupar exigia `::timestamp`, que descarta o offset, e não
usava índice. Esta revisão converte cada coluna e o código passa a gravar e ler
`datetime` com fuso.

Regra de cada coluna (ver `COLUNAS`): o texto que traz offset (`+00:00`, `-03:00`,
`Z`) vale como está; o texto SEM offset é lido no fuso que o código gravava nessa
coluna (`local` = America/Sao_Paulo, `utc`). A expressão distingue pelo próprio
texto, então uma coluna que recebeu mais de um formato ao longo do tempo é
convertida certo. Uma coluna cujo texto sem offset seria ambíguo (`naive=None`:
`medicoes.timestamp_local`, sempre gravada com offset) recusa o texto sem offset.

Texto vazio ou fora dos formatos aceitos nunca vira data inventada: numa coluna
que aceita NULL vira NULL; numa coluna NOT NULL a revisão inteira falha (o DDL é
transacional, nada fica pela metade). Texto no formato certo mas impossível
(mês 13) também aborta a conversão.

`execucoes.data_inicio` e `data_fim` são dias do calendário, não instantes: viram
`date`.

Idempotente: coluna que já é `timestamptz`/`date` fica como está. `downgrade`
devolve texto ISO no formato que o código anterior gravava em cada coluna.
"""

from alembic import op

revision = "20261111_instantes_com_fuso"
down_revision = "20261111_auditoria_so_insercao"
branch_labels = None
depends_on = None

FUSO_LOCAL = "America/Sao_Paulo"

# (esquema, tabela, coluna, aceita NULL, fuso do texto sem offset, formato do downgrade)
COLUNAS = [
    ("historico", "configuracoes", "atualizado_em", False, "local", "local"),
    ("historico", "usuarios", "criado_em", False, "local", "local"),
    ("historico", "usuarios", "atualizado_em", False, "local", "local"),
    ("historico", "usuarios", "ultimo_login_em", True, "local", "local"),
    ("historico", "zonas", "criado_em", False, "local", "local"),
    ("historico", "usuario_zonas", "concedido_em", False, "utc", "utc_offset"),
    ("historico", "leituras", "criado_em", False, "utc", "utc_offset"),
    ("historico", "leituras", "timestamp_utc", True, "utc", "utc_offset"),
    ("historico", "equipamentos", "criado_em", False, "local", "local"),
    ("historico", "estado_equipamentos", "atualizado_em", False, "local", "local"),
    ("historico", "estado_equipamentos", "ultimo_ciclo_em", True, "local", "local"),
    ("historico", "controle_zonas", "atualizado_em", False, "local", "local"),
    ("historico", "estado_coletor", "iniciado_em", True, "local", "local"),
    ("historico", "estado_coletor", "heartbeat_em", True, "local", "local"),
    ("historico", "estado_coletor", "ultimo_ciclo_em", True, "local", "local"),
    ("historico", "estado_coletor", "proximo_ciclo_em", True, "local", "local"),
    ("historico", "eventos_operacao", "criado_em", False, "local", "local"),
    ("historico", "leituras_recentes_zona", "criado_em", False, "utc", "utc_offset"),
    ("historico", "agregados_15min", "janela_inicio", False, "utc", "utc_ingenuo"),
    ("historico", "agregados_15min", "criado_em", False, "utc", "utc_offset"),
    ("historico", "resumos_horarios", "hora_inicio", False, "utc", "utc_ingenuo"),
    ("historico", "resumos_horarios", "criado_em", False, "utc", "utc_offset"),
    ("historico", "auditoria_eventos", "criado_em", False, "utc", "utc_offset"),
    ("historico", "notificacoes_outbox", "proxima_tentativa_em", True, "utc", "utc_offset"),
    ("historico", "notificacoes_outbox", "bloqueado_em", True, "utc", "utc_offset"),
    ("historico", "notificacoes_outbox", "criado_em", False, "utc", "utc_offset"),
    ("historico", "notificacoes_outbox", "enviado_em", True, "utc", "utc_offset"),
    ("historico", "sessoes_revogadas", "expira_em", False, "utc", "utc_offset"),
    ("dados_entrada", "configuracoes_zona", "atualizado_em", False, "utc", "utc_offset"),
    ("dados_entrada", "execucoes", "criado_em", False, "utc", "utc_offset"),
    ("dados_entrada", "execucoes", "concluido_em", True, "utc", "utc_offset"),
    ("dados_entrada", "execucoes", "lease_until", True, "utc", "utc_offset"),
    ("dados_entrada", "execucoes", "heartbeat_em", True, "utc", "utc_offset"),
    ("dados_entrada", "execucoes", "publicado_em", True, "utc", "utc_offset"),
    ("dados_entrada", "medicoes", "timestamp_utc", False, "utc", "utc_minuto"),
    ("dados_entrada", "medicoes", "timestamp_local", False, None, "local_da_linha"),
]

# Dias do calendário: (esquema, tabela, coluna)
DATAS = [
    ("dados_entrada", "execucoes", "data_inicio"),
    ("dados_entrada", "execucoes", "data_fim"),
]

_HORA = r"\d{2}:\d{2}(:\d{2}(\.\d{1,6})?)?"
SEM_OFFSET = rf"^\d{{4}}-\d{{2}}-\d{{2}}[T ]{_HORA}$"
COM_OFFSET = rf"^\d{{4}}-\d{{2}}-\d{{2}}[T ]{_HORA}(Z|[+-]\d{{2}}(:\d{{2}})?)$"
SO_DATA = r"^\d{4}-\d{2}-\d{2}$"

ISO_SEGUNDO = "'YYYY-MM-DD\"T\"HH24:MI:SS'"
ISO_MINUTO = "'YYYY-MM-DD\"T\"HH24:MI'"


def _tipo_atual(conn, esquema: str, tabela: str, coluna: str) -> str:
    return conn.exec_driver_sql(
        "SELECT data_type FROM information_schema.columns "
        "WHERE table_schema = %s AND table_name = %s AND column_name = %s",
        (esquema, tabela, coluna),
    ).scalar_one()


def _quando_valido(coluna: str, naive: str | None) -> str:
    condicao = f"{coluna} ~ '{COM_OFFSET}'"
    if naive is not None:
        condicao += f" OR {coluna} ~ '{SEM_OFFSET}'"
    return condicao


def _usando(coluna: str, naive: str | None) -> str:
    if naive is None:
        return f"{coluna}::timestamptz"
    fuso = FUSO_LOCAL if naive == "local" else "UTC"
    return (
        f"CASE WHEN {coluna} ~ '{COM_OFFSET}' THEN {coluna}::timestamptz "
        f"ELSE ({coluna}::timestamp) AT TIME ZONE '{fuso}' END"
    )


def _rejeitar_ou_anular(conn, esquema, tabela, coluna, aceita_nulo, valido) -> None:
    ruins = conn.exec_driver_sql(
        f"SELECT count(*) FROM {esquema}.{tabela} WHERE {coluna} IS NOT NULL AND NOT ({valido})"
    ).scalar_one()
    if not ruins:
        return
    if not aceita_nulo:
        raise RuntimeError(
            f"{esquema}.{tabela}.{coluna}: {ruins} linha(s) com texto vazio ou fora dos "
            "formatos de data aceitos, e a coluna não aceita NULL. Nada foi alterado; "
            "corrija os valores antes de repetir a revisão."
        )
    conn.exec_driver_sql(
        f"UPDATE {esquema}.{tabela} SET {coluna} = NULL "
        f"WHERE {coluna} IS NOT NULL AND NOT ({valido})"
    )


def upgrade() -> None:
    conn = op.get_bind()
    for esquema, tabela, coluna, aceita_nulo, naive, _volta in COLUNAS:
        if _tipo_atual(conn, esquema, tabela, coluna) == "timestamp with time zone":
            continue
        _rejeitar_ou_anular(
            conn, esquema, tabela, coluna, aceita_nulo, _quando_valido(coluna, naive)
        )
        conn.exec_driver_sql(
            f"ALTER TABLE {esquema}.{tabela} ALTER COLUMN {coluna} "
            f"TYPE timestamptz USING {_usando(coluna, naive)}"
        )
    for esquema, tabela, coluna in DATAS:
        if _tipo_atual(conn, esquema, tabela, coluna) == "date":
            continue
        _rejeitar_ou_anular(conn, esquema, tabela, coluna, False, f"{coluna} ~ '{SO_DATA}'")
        conn.exec_driver_sql(
            f"ALTER TABLE {esquema}.{tabela} ALTER COLUMN {coluna} TYPE date USING {coluna}::date"
        )


def _texto_de(coluna: str, formato: str) -> str:
    utc = f"({coluna} AT TIME ZONE 'UTC')"
    if formato == "local":
        return f"to_char({coluna} AT TIME ZONE '{FUSO_LOCAL}', {ISO_SEGUNDO})"
    if formato == "utc_ingenuo":
        return f"to_char({utc}, {ISO_SEGUNDO})"
    if formato == "utc_offset":
        return (
            f"to_char({utc}, {ISO_SEGUNDO}) || "
            f"CASE WHEN mod(date_part('microseconds', {utc})::bigint, 1000000) <> 0 "
            f"THEN to_char({utc}, '.US') ELSE '' END || '+00:00'"
        )
    if formato == "utc_minuto":
        return f"to_char({utc}, {ISO_MINUTO}) || '+00:00'"
    if formato == "local_da_linha":
        local = f"({coluna} AT TIME ZONE fuso_horario)"
        desvio = f"({local} - {utc})"
        return (
            f"to_char({local}, {ISO_MINUTO}) || "
            f"CASE WHEN {desvio} < interval '0' THEN '-' ELSE '+' END || "
            f"to_char(CASE WHEN {desvio} < interval '0' THEN -{desvio} ELSE {desvio} END, 'HH24:MI')"
        )
    raise ValueError(formato)


def downgrade() -> None:
    conn = op.get_bind()
    for esquema, tabela, coluna, _nulo, _naive, volta in reversed(COLUNAS):
        if _tipo_atual(conn, esquema, tabela, coluna) != "timestamp with time zone":
            continue
        conn.exec_driver_sql(
            f"ALTER TABLE {esquema}.{tabela} ALTER COLUMN {coluna} "
            f"TYPE text USING {_texto_de(coluna, volta)}"
        )
    for esquema, tabela, coluna in DATAS:
        if _tipo_atual(conn, esquema, tabela, coluna) == "date":
            conn.exec_driver_sql(
                f"ALTER TABLE {esquema}.{tabela} ALTER COLUMN {coluna} TYPE text USING {coluna}::text"
            )
