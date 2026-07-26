"""Otimiza consultas temporais e remove configuração global obsoleta."""

from alembic import op

revision = "0002_otimiza_postgres"
down_revision = "0001_postgresql_inicial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Usado pela consolidação de janelas e pelos filtros cronológicos.
    op.execute(
        """
        CREATE INDEX idx_leituras_zona_indice_criado_em
        ON historico.leituras (zona_id, indice, criado_em)
        """
    )
    op.execute(
        """
        CREATE INDEX idx_leituras_criado_em_id
        ON historico.leituras (criado_em, id)
        """
    )

    # A antiga chave global foi substituída por controle individual por zona.
    # A limpeza pertence à migração, não ao caminho de inicialização de cada
    # processo e de cada réplica.
    op.execute(
        """
        DELETE FROM historico.configuracoes
        WHERE chave = 'modoAutomatico'
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX historico.idx_leituras_criado_em_id")
    op.execute("DROP INDEX historico.idx_leituras_zona_indice_criado_em")
