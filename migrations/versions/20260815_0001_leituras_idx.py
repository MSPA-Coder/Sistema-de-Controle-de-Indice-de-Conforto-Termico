"""Índice (zona_id, id) em historico.leituras para o fallback de histórico
recente sem indice fixo.

O fallback de ``obter_historicos_recentes_zonas`` (zona sem janela recente
em ``leituras_recentes_zona``) filtra só por ``zona_id`` e ordena por ``id
DESC``, sem filtrar ``indice``. Os índices existentes
(``idx_leituras_zona_indice_id``, ``idx_leituras_zona_indice_criado_em``)
têm ``indice`` como segunda coluna e não atendem esse padrão de acesso.
"""

from alembic import op

revision = "20260815_0001_leituras_idx"
down_revision = "20260803_0001_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX idx_leituras_zona_id ON historico.leituras (zona_id, id)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS historico.idx_leituras_zona_id")
