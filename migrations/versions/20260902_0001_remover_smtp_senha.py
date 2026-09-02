"""Remove a senha SMTP persistida em texto claro (CT-03).

`smtpSenha` deixou de ter chave em `CONFIGURACOES_PADRAO`
(`app/database_configuracoes.py`): a aplicação nunca mais grava nem lê esse
valor do banco -- a senha agora vem exclusivamente de segredo do Compose ou da
variável `SMTP_PASS` (`models._resolver_senha_smtp`). Sem esta migração, o
valor já gravado por uma configuração anterior continuaria na tabela --
invisível pela API, mas presente em qualquer dump, backup restaurado ou
réplica de desenvolvimento, que é exatamente o vazamento que o achado descreve.
"""

from alembic import op

revision = "20260902_0001_remover_smtp_senha"
down_revision = "20260901_0001_audit_frescor"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DELETE FROM historico.configuracoes WHERE chave = 'smtpSenha'")


def downgrade() -> None:
    # Deliberadamente sem downgrade de dados: restaurar um valor de senha
    # apagado por esta migração reintroduziria o próprio vazamento que ela
    # existe para fechar. Reverter esta revisão apenas libera a aplicação
    # para voltar a gravar a chave, caso um dia isso seja decidido de novo --
    # não recupera a senha antiga.
    pass
