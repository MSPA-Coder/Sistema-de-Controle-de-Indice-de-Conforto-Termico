"""Índices para a última amostra e as páginas cronológicas por zona."""

from alembic import op

revision = "20261123_ordem_leituras"
down_revision = "20261112_checks_de_dominio"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE INDEX idx_leituras_zona_criado_id ON historico.leituras (zona_id, criado_em, id)")
    op.execute(
        "CREATE INDEX idx_leituras_zona_indice_amostra ON historico.leituras "
        "(zona_id, indice, (COALESCE(timestamp_utc, criado_em)))"
    )


def downgrade() -> None:
    op.execute("DROP INDEX historico.idx_leituras_zona_indice_amostra")
    op.execute("DROP INDEX historico.idx_leituras_zona_criado_id")
