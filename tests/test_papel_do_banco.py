"""A aplicação recusa atender como superusuário do PostgreSQL."""

from __future__ import annotations

import pytest
from sqlalchemy import event

from app.nucleo import db_backend
from app.nucleo.papel_do_banco import (
    VARIAVEL,
    PapelPrivilegiadoError,
    conferir_conexao,
)


class _CursorFalso:
    def __init__(self, valor: str) -> None:
        self.valor = valor
        self.consultas: list[str] = []

    def execute(self, sql: str) -> None:
        self.consultas.append(sql)

    def fetchone(self):
        return (self.valor,)

    def close(self) -> None:
        pass


class _ConexaoFalsa:
    autocommit = False

    def __init__(self, valor: str) -> None:
        self.cursor_falso = _CursorFalso(valor)
        self.desfeitas = 0

    def cursor(self):
        return self.cursor_falso

    def rollback(self) -> None:
        self.desfeitas += 1


def test_superusuario_e_recusado_quando_exigido(monkeypatch):
    monkeypatch.setenv(VARIAVEL, "1")
    with pytest.raises(PapelPrivilegiadoError):
        conferir_conexao(_ConexaoFalsa("on"))


def test_papel_restrito_passa_e_devolve_a_conexao_limpa(monkeypatch):
    monkeypatch.setenv(VARIAVEL, "1")
    conexao = _ConexaoFalsa("off")
    conferir_conexao(conexao)
    assert conexao.cursor_falso.consultas == ["SHOW is_superuser"]
    assert conexao.desfeitas == 1


def test_sem_a_variavel_nem_pergunta(monkeypatch):
    """O `schema` (Alembic) usa o superusuário de propósito."""
    monkeypatch.delenv(VARIAVEL, raising=False)
    conexao = _ConexaoFalsa("on")
    conferir_conexao(conexao)
    assert conexao.cursor_falso.consultas == []


@pytest.mark.parametrize(
    ("exigido", "arquivo"),
    [("1", "postgres_app_password"), ("0", "postgres_password")],
)
def test_cada_papel_so_le_o_proprio_segredo(monkeypatch, exigido, arquivo):
    """Com a trava ligada, o processo não consegue ler a senha administrativa."""
    capturado = {}

    def falso(nome, *, aceitar_variavel, caminho_esperado):
        capturado["caminho"] = caminho_esperado
        return "x"

    monkeypatch.setenv(VARIAVEL, exigido)
    monkeypatch.setattr(db_backend, "resolver_segredo", falso)
    db_backend._ler_segredo("DB_PASSWORD")
    assert capturado["caminho"].name == arquivo


def test_todo_engine_criado_recebe_a_trava():
    """Sem o `instalar` em `_engine`, a trava existiria e nunca rodaria.

    Criar o engine não abre conexão, então o teste não precisa de banco.
    """
    url = "postgresql+psycopg://u:s@127.0.0.1:1/teste_trava"
    engine = db_backend._engine(url)
    try:
        assert event.contains(engine, "connect", conferir_conexao)
    finally:
        db_backend._engines_criados.pop(url, None)
        engine.dispose()
