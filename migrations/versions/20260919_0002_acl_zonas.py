"""Associação explícita de usuários às zonas autorizadas."""

from alembic import op


revision = "20260919_02_acl_zonas"
down_revision = "20260919_01_integridade"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE historico.usuario_zonas (
            usuario_id BIGINT NOT NULL REFERENCES historico.usuarios(id) ON DELETE CASCADE,
            zona_id BIGINT NOT NULL REFERENCES historico.zonas(id) ON DELETE CASCADE,
            concedido_em TEXT NOT NULL,
            PRIMARY KEY (usuario_id, zona_id)
        )
        """
    )
    op.execute(
        """
        INSERT INTO historico.usuario_zonas (usuario_id, zona_id, concedido_em)
        SELECT u.id, z.id, COALESCE(u.criado_em, z.criado_em)
        FROM historico.usuarios u
        CROSS JOIN historico.zonas z
        WHERE u.ativo = 1 AND u.perfil <> 'administrador'
        """
    )
    op.execute(
        "CREATE INDEX idx_usuario_zonas_zona ON historico.usuario_zonas (zona_id, usuario_id)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS historico.idx_usuario_zonas_zona")
    op.execute("DROP TABLE historico.usuario_zonas")
