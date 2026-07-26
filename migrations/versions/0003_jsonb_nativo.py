"""Usa JSONB para documentos consultados no PostgreSQL."""

from alembic import op

revision = "0003_jsonb_nativo"
down_revision = "0002_otimiza_postgres"
branch_labels = None
depends_on = None

COLUNAS = (
    ("historico", "leituras", "entradas"),
    ("historico", "estado_equipamentos", "falhas"),
    ("historico", "eventos_operacao", "detalhes"),
    ("historico", "leituras_recentes_zona", "entradas"),
    ("historico", "agregados_15min", "entradas_medias"),
    ("dados_entrada", "medicoes", "origem_variaveis"),
    ("dados_entrada", "medicoes", "entradas_indice"),
    ("dados_entrada", "cache_clima", "resposta_json"),
)


def upgrade() -> None:
    op.execute(
        "ALTER TABLE historico.estado_equipamentos "
        "ALTER COLUMN falhas DROP DEFAULT"
    )
    for schema, tabela, coluna in COLUNAS:
        op.execute(
            f"""
            ALTER TABLE {schema}.{tabela}
            ALTER COLUMN {coluna} TYPE JSONB
            USING {coluna}::jsonb
            """
        )
    op.execute(
        "ALTER TABLE historico.estado_equipamentos "
        "ALTER COLUMN falhas SET DEFAULT '[]'::jsonb"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE historico.estado_equipamentos "
        "ALTER COLUMN falhas DROP DEFAULT"
    )
    for schema, tabela, coluna in reversed(COLUNAS):
        op.execute(
            f"""
            ALTER TABLE {schema}.{tabela}
            ALTER COLUMN {coluna} TYPE TEXT
            USING {coluna}::text
            """
        )
    op.execute(
        "ALTER TABLE historico.estado_equipamentos "
        "ALTER COLUMN falhas SET DEFAULT '[]'::text"
    )
