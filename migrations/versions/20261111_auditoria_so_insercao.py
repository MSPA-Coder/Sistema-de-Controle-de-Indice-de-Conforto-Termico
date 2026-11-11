"""A trilha de auditoria aceita inserção; alterar e apagar ficam com o administrador.

O papel da aplicação (`conforto_app`) tinha UPDATE e DELETE em
`historico.auditoria_eventos`: o `db-provision` concede DML em todas as tabelas
a cada subida, então um REVOKE não duraria. O código nunca altera nem apaga a
trilha, mas um defeito, ou alguém com a sessão da aplicação, podia apagar o
próprio rastro.

O gatilho recusa UPDATE, DELETE e TRUNCATE de quem não é superusuário. O papel
administrativo (o do `schema`, do backup e da suíte) é superusuário e não é
afetado: expurgo e correção da trilha continuam possíveis, por ele.

Idempotente: num banco que já tem o gatilho, nada muda.
"""

from alembic import op

revision = "20261111_auditoria_so_insercao"
down_revision = "20261104_idioma_usuario"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE OR REPLACE FUNCTION historico.auditoria_somente_insercao() RETURNS trigger
            LANGUAGE plpgsql
            AS $$
        BEGIN
            IF (SELECT rolsuper FROM pg_roles WHERE rolname = current_user) THEN
                IF TG_LEVEL = 'STATEMENT' THEN
                    RETURN NULL;
                END IF;
                RETURN COALESCE(NEW, OLD);
            END IF;
            RAISE EXCEPTION 'auditoria_eventos aceita apenas insercao (papel %)', current_user
                USING ERRCODE = 'insufficient_privilege';
        END;
        $$
    """)
    op.execute("DROP TRIGGER IF EXISTS auditoria_somente_insercao ON historico.auditoria_eventos")
    op.execute("""
        CREATE TRIGGER auditoria_somente_insercao
            BEFORE UPDATE OR DELETE ON historico.auditoria_eventos
            FOR EACH ROW EXECUTE FUNCTION historico.auditoria_somente_insercao()
    """)
    op.execute(
        "DROP TRIGGER IF EXISTS auditoria_sem_truncate ON historico.auditoria_eventos"
    )
    op.execute("""
        CREATE TRIGGER auditoria_sem_truncate
            BEFORE TRUNCATE ON historico.auditoria_eventos
            FOR EACH STATEMENT EXECUTE FUNCTION historico.auditoria_somente_insercao()
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS auditoria_sem_truncate ON historico.auditoria_eventos")
    op.execute("DROP TRIGGER IF EXISTS auditoria_somente_insercao ON historico.auditoria_eventos")
    op.execute("DROP FUNCTION IF EXISTS historico.auditoria_somente_insercao()")
