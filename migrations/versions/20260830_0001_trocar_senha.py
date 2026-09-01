"""Marca de troca de senha pendente em historico.usuarios.

Contas existentes nascem com a marca desligada. Ligá-la para todo mundo
obrigaria quem já usa o sistema a trocar a senha ao mesmo tempo, sem aviso, e
não há motivo: a senha dessas pessoas não é conhecida por terceiros. A marca
passa a ser ligada apenas pela criação de conta e pela redefinição feita por
um administrador.

``INTEGER NOT NULL DEFAULT 0`` acompanha a coluna ``ativo`` da mesma tabela,
que também é inteiro 0/1 -- a camada de persistência deste projeto já trata
booleano assim (``coagir_booleano``), e um ``BOOLEAN`` aqui seria a única
exceção da tabela.

Coluna nova com padrão no servidor: a imagem anterior a ignora, o que mantém a
migração compatível com o rollback de código e imagem do ``deploy.sh`` (que não
reverte schema).
"""

from alembic import op

revision = "20260830_0001_trocar_senha"
down_revision = "20260815_0001_leituras_idx"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE historico.usuarios "
        "ADD COLUMN trocar_senha INTEGER NOT NULL DEFAULT 0"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE historico.usuarios DROP COLUMN trocar_senha")
