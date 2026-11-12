"""Duas colunas de instante que a revisão anterior deixou em TEXT viram `timestamptz`.

`20261111_instantes_com_fuso` converteu 36 colunas, mas `dados_entrada.cache_clima.
consultado_em` e `dados_entrada.historico_exportado.copiado_em` ficaram de fora
sem motivo registrado (ADR 012, git log e a própria revisão não dizem nada; foi
omissão). O código sempre gravou nelas o UTC com offset (`timestamp_utc()` até
10/11, `agora_utc()` depois), então a regra é a mesma da revisão anterior: texto
com offset vale como está; sem offset é lido como UTC. Texto vazio ou fora dos
formatos aceitos, numa coluna NOT NULL, aborta a revisão inteira (DDL
transacional): nunca vira data inventada.

A regra de conversão, a recusa e o formato do `downgrade` são as da revisão
anterior, reaproveitadas dela. Idempotente: coluna que já é `timestamptz` fica
como está. Ao final a revisão confere que as duas colunas são `timestamptz`.
"""

import importlib.util
from pathlib import Path

from alembic import op

revision = "20261111_instantes_restantes"
down_revision = "20261111_instantes_com_fuso"
branch_labels = None
depends_on = None


def _revisao_anterior():
    caminho = Path(__file__).with_name("20261111_instantes_com_fuso.py")
    spec = importlib.util.spec_from_file_location("revisao_instantes_com_fuso", caminho)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


_base = _revisao_anterior()

# (esquema, tabela, coluna, aceita NULL, fuso do texto sem offset, formato do downgrade)
COLUNAS = [
    ("dados_entrada", "cache_clima", "consultado_em", False, "utc", "utc_offset"),
    ("dados_entrada", "historico_exportado", "copiado_em", False, "utc", "utc_offset"),
]


def upgrade() -> None:
    conn = op.get_bind()
    for esquema, tabela, coluna, aceita_nulo, naive, _volta in COLUNAS:
        if _base._tipo_atual(conn, esquema, tabela, coluna) == "timestamp with time zone":
            continue
        _base._rejeitar_ou_anular(
            conn, esquema, tabela, coluna, aceita_nulo, _base._quando_valido(coluna, naive)
        )
        conn.exec_driver_sql(
            f"ALTER TABLE {esquema}.{tabela} ALTER COLUMN {coluna} "
            f"TYPE timestamptz USING {_base._usando(coluna, naive)}"
        )
    restantes = [
        f"{esquema}.{tabela}.{coluna}"
        for esquema, tabela, coluna, *_ in COLUNAS
        if _base._tipo_atual(conn, esquema, tabela, coluna) != "timestamp with time zone"
    ]
    if restantes:
        raise RuntimeError(f"Colunas que continuam fora de timestamptz: {', '.join(restantes)}")


def downgrade() -> None:
    conn = op.get_bind()
    for esquema, tabela, coluna, _nulo, _naive, volta in reversed(COLUNAS):
        if _base._tipo_atual(conn, esquema, tabela, coluna) != "timestamp with time zone":
            continue
        conn.exec_driver_sql(
            f"ALTER TABLE {esquema}.{tabela} ALTER COLUMN {coluna} "
            f"TYPE text USING {_base._texto_de(coluna, volta)}"
        )
