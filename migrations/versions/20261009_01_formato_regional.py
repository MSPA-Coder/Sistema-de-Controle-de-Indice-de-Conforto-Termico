"""Formato regional (Brasil/EUA) de datas e números, escolhido por usuário.

Só apresentação: nada do que já está gravado muda. Toda conta existente fica em
``br``, o formato que o sistema sempre mostrou.

Coluna nova com padrão no servidor: a imagem anterior a ignora, o que mantém a
migração compatível com o rollback de código e imagem do ``deploy.sh`` (que não
reverte schema).
"""

from alembic import op

revision = "20261009_01_formato_regional"
down_revision = "20260919_02_acl_zonas"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE historico.usuarios "
        "ADD COLUMN formato_regional TEXT NOT NULL DEFAULT 'br' "
        "CONSTRAINT ck_usuarios_formato_regional CHECK (formato_regional IN ('br', 'us'))"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE historico.usuarios DROP COLUMN formato_regional")
