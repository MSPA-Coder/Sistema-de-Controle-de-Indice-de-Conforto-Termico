"""Fixtures para os testes que exercitam requisições HTTP de verdade.

`criar_app_ict()` não conecta ao banco na criação -- `db.iniciar_banco()` e
`dados_entrada.db.iniciar_banco()` são no-ops (o schema é exclusivo do
Alembic); só rotas que de fato consultam dados (ex.: `/health`) tocam o
banco. Isso permite `app.test_client()` de verdade para o gate de login, o
CSRF e o rate-limit, sem precisar de PostgreSQL -- ao contrário do que
comentários mais antigos nesta suíte assumiam.

`CONFORTO_TESTING=1` desliga o rate-limiter (`_criar_limiter` usa
`enabled=not app.testing`); é o padrão aqui para não fazer os testes se
atropelarem no mesmo limite. O teste dedicado de rate-limit
(`test_rate_limit.py`) cria a própria app sem essa variável, de propósito.

`DATABASE_URL` abaixo aponta para uma porta sem nada escutando -- de
propósito, para as rotas que de fato tocam o banco (ex.: `/health`) verem
uma falha real em vez de um mock. Em Linux isso basta: o SO recusa o
`connect()` na hora. Em Windows, com psycopg 3.2.13 e Python 3.14, a recusa
nunca chega a acordar `psycopg.waiting.wait_conn`, e o teste trava para
sempre -- `_stub_banco.recusar_conexao_com_banco` cobre isso fazendo o
`sqlalchemy.create_engine` usado por `app/db_backend.py` recusar a conexão
sem abrir socket nenhum; ver o docstring de `tests/_stub_banco.py` para o
mecanismo completo do travamento e por que `connect_timeout` não resolve.
"""

from __future__ import annotations

import pytest
from _stub_banco import recusar_conexao_com_banco

from app.app_factory import AppConfig, criar_app_ict


def _config() -> AppConfig:
    return AppConfig(
        debug=False,
        host="127.0.0.1",
        port=5000,
        threaded=False,
        max_content_length=1_000_000,
        # `CONFORTO_TESTING` desliga o rate limiter e libera a chave de sessão
        # gerada; por isso `_validar_testing` passou a exigir que ela venha
        # acompanhada de desenvolvimento explícito e host de loopback --
        # ligada sozinha, em produção, removeria as duas proteções em
        # silêncio. A suíte é um contexto de desenvolvimento e declara isso
        # aqui, no mesmo objeto que a fábrica lê.
        development=True,
    )


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setenv("CONFORTO_TESTING", "1")
    monkeypatch.setenv("CONFORTO_SECRET_KEY", "chave-de-teste-nao-usada-em-execucao-real")
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql+psycopg://test:test@localhost:5999/test"
    )
    recusar_conexao_com_banco(monkeypatch)
    application = criar_app_ict(_config())
    application.config["TESTING"] = True
    return application


@pytest.fixture
def client(app):
    return app.test_client()
