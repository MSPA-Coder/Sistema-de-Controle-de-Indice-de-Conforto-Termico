"""Conexões do papel restrito têm teto de tempo; as do superusuário (Alembic) não.

Sem `statement_timeout`, uma consulta de histórico sem limite prende uma
conexão do pool (5 + 10 por processo) até o servidor acabar. Sem
`idle_in_transaction_session_timeout`, uma transação esquecida segura locks.
"""

from __future__ import annotations

from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError

from app.nucleo import db_backend
from app.nucleo.papel_do_banco import VARIAVEL

pytestmark = pytest.mark.usefixtures("banco")


@pytest.fixture
def conectar_como_papel_restrito(banco_de_teste, monkeypatch):
    """Devolve uma função que abre uma conexão da aplicação com um papel sem privilégios."""
    nome = "qa_teto_" + uuid4().hex[:8]
    senha = uuid4().hex
    url = make_url(banco_de_teste)
    admin_url = url.set(drivername="postgresql").render_as_string(hide_password=False)
    with psycopg.connect(admin_url, autocommit=True) as admin:
        admin.execute(
            sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(
                sql.Identifier(nome), sql.Literal(senha)
            )
        )
        admin.execute(
            sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                sql.Identifier(url.database), sql.Identifier(nome)
            )
        )
        monkeypatch.setenv(
            "DATABASE_URL",
            url.set(username=nome, password=senha).render_as_string(hide_password=False),
        )
        monkeypatch.setenv(VARIAVEL, "1")
        db_backend._engine.cache_clear()
        abertas = []

        def abrir():
            conexao = db_backend.abrir_conexao_postgres("historico")
            abertas.append(conexao)
            return conexao

        try:
            yield abrir
        finally:
            for conexao in abertas:
                conexao.close()
            for engine in list(db_backend._engines_criados.values()):
                engine.dispose()
            db_backend._engines_criados.clear()
            db_backend._engine.cache_clear()
            admin.execute(sql.SQL("DROP OWNED BY {}").format(sql.Identifier(nome)))
            admin.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(nome)))


def _mostrar(conexao, parametro: str) -> str:
    return conexao.execute(f"SHOW {parametro}").fetchone()[0]


def test_papel_restrito_abre_com_os_tetos_padrao(conectar_como_papel_restrito):
    conexao = conectar_como_papel_restrito()
    assert _mostrar(conexao, "statement_timeout") == "15min"
    assert _mostrar(conexao, "idle_in_transaction_session_timeout") == "5min"


def test_consulta_que_passa_do_teto_e_cancelada(conectar_como_papel_restrito, monkeypatch):
    monkeypatch.setenv("DB_STATEMENT_TIMEOUT_MS", "300")
    conexao = conectar_como_papel_restrito()
    assert _mostrar(conexao, "statement_timeout") == "300ms"
    with pytest.raises(OperationalError, match="statement timeout"):
        conexao.execute("SELECT pg_sleep(3)")


def test_valor_que_nao_e_numero_e_recusado(monkeypatch):
    monkeypatch.setenv(VARIAVEL, "1")
    monkeypatch.setenv("DB_STATEMENT_TIMEOUT_MS", "1000 -c search_path=public")
    with pytest.raises(RuntimeError, match="DB_STATEMENT_TIMEOUT_MS"):
        db_backend.opcoes_de_sessao()


def test_sem_a_trava_de_papel_nao_ha_teto(monkeypatch):
    """O `schema` (Alembic) migra tabela grande; teto ali cortaria a migração."""
    monkeypatch.delenv(VARIAVEL, raising=False)
    assert db_backend.opcoes_de_sessao() == "-c timezone=UTC"
