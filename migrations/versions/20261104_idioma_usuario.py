"""Guarda o idioma de interface por usuário, sem alterar dados existentes."""

from alembic import op

revision = "20261104_idioma_usuario"
down_revision = "20261021_01_sessoes_revogadas"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE historico.usuarios
        ADD COLUMN idioma TEXT NOT NULL DEFAULT 'pt-br'
        CONSTRAINT ck_usuarios_idioma CHECK (idioma IN ('pt-br', 'en'))
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE historico.usuarios DROP COLUMN idioma")
