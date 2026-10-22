"""Sessões encerradas pelo usuário (logout) deixam de valer no servidor.

A sessão é um cookie assinado, sem estado no servidor: sair apenas apagava o
cookie do navegador, e uma cópia guardada antes do logout seguia aceita até
vencer. A sessão passa a ter um identificador (`sid`); o logout o registra aqui
e a requisição seguinte com esse `sid` é tratada como deslogada. A linha some
sozinha depois do vencimento natural da sessão.

Tabela nova: a imagem anterior a ignora, o que mantém a migração compatível com
o rollback de código e imagem do ``deploy.sh`` (que não reverte schema).
"""

from alembic import op

revision = "20261021_01_sessoes_revogadas"
down_revision = "20261009_01_formato_regional"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE historico.sessoes_revogadas (
            sid TEXT PRIMARY KEY,
            expira_em TEXT NOT NULL
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_sessoes_revogadas_expira ON historico.sessoes_revogadas (expira_em)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS historico.idx_sessoes_revogadas_expira")
    op.execute("DROP TABLE historico.sessoes_revogadas")
