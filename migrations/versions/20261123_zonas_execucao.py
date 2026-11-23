"""Preserva o escopo das novas gerações antes de receber o primeiro lote."""

from alembic import op

revision = "20261123_zonas_execucao"
down_revision = "20261123_ordem_leituras"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE dados_entrada.execucoes ADD COLUMN zonas_previstas bigint[]")


def downgrade() -> None:
    op.execute("ALTER TABLE dados_entrada.execucoes DROP COLUMN zonas_previstas")
