"""O papel da aplicação insere na trilha de auditoria, mas não a altera nem a apaga.

O `db-provision` reconcede DML em todas as tabelas a cada subida, então a
proteção é um gatilho (migração 20261111), não um REVOKE.
"""

from __future__ import annotations

from uuid import uuid4

import psycopg
import pytest
from psycopg import sql

pytestmark = pytest.mark.usefixtures("banco")

INSERIR = (
    "INSERT INTO historico.auditoria_eventos (evento, categoria, acao, sucesso, ator_login, "
    "ator_perfil, contexto, detalhes, criado_em) "
    "VALUES (%s, 'teste', 'teste', 1, 'qa', 'administrador', '{}', '{}', '2026-11-11T00:00:00')"
)


@pytest.fixture
def papel_da_aplicacao(banco_de_teste):
    """Conexão de superusuário e um papel restrito como o `conforto_app` (DML sem posse)."""
    nome = "qa_app_" + uuid4().hex[:8]
    url = banco_de_teste.replace("postgresql+psycopg://", "postgresql://")
    with psycopg.connect(url, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE ROLE {} NOLOGIN").format(sql.Identifier(nome)))
        admin.execute(sql.SQL("GRANT USAGE ON SCHEMA historico TO {}").format(sql.Identifier(nome)))
        admin.execute(
            sql.SQL("GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE ON historico.auditoria_eventos TO {}")
            .format(sql.Identifier(nome))
        )
        admin.execute(
            sql.SQL("GRANT USAGE ON ALL SEQUENCES IN SCHEMA historico TO {}").format(sql.Identifier(nome))
        )
        try:
            yield admin, nome
        finally:
            admin.execute("DELETE FROM historico.auditoria_eventos WHERE categoria = 'teste'")
            admin.execute(sql.SQL("DROP OWNED BY {}").format(sql.Identifier(nome)))
            admin.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(nome)))


def _como_aplicacao(admin, nome: str, comando: str, parametros=()):
    admin.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(nome)))
    try:
        return admin.execute(comando, parametros)
    finally:
        admin.execute("RESET ROLE")


def test_papel_da_aplicacao_insere_mas_nao_altera_apaga_nem_trunca_a_trilha(papel_da_aplicacao):
    admin, nome = papel_da_aplicacao
    _como_aplicacao(admin, nome, INSERIR, ("QA_INSERIDO",))

    for comando in (
        "UPDATE historico.auditoria_eventos SET acao = 'adulterado' WHERE evento = 'QA_INSERIDO'",
        "DELETE FROM historico.auditoria_eventos WHERE evento = 'QA_INSERIDO'",
        "TRUNCATE historico.auditoria_eventos",
    ):
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            _como_aplicacao(admin, nome, comando)

    restante = admin.execute(
        "SELECT acao FROM historico.auditoria_eventos WHERE evento = 'QA_INSERIDO'"
    ).fetchall()
    assert restante == [("teste",)]


def test_administrador_ainda_pode_corrigir_a_trilha(papel_da_aplicacao):
    admin, nome = papel_da_aplicacao
    _como_aplicacao(admin, nome, INSERIR, ("QA_CORRIGIR",))
    admin.execute("UPDATE historico.auditoria_eventos SET acao = 'corrigido' WHERE evento = 'QA_CORRIGIR'")
    admin.execute("DELETE FROM historico.auditoria_eventos WHERE evento = 'QA_CORRIGIR'")
    assert not admin.execute(
        "SELECT 1 FROM historico.auditoria_eventos WHERE evento = 'QA_CORRIGIR'"
    ).fetchall()
