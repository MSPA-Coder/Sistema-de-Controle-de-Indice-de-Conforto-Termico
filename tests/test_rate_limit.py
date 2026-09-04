"""O login aplica `LIMITE_LOGIN_PADRAO` pelo limiter registrado na app.

A fixture deste arquivo cria a aplicação sem `CONFORTO_TESTING=1`, pois a
fixture geral desliga o rate limiter e não permite medir o enforcement real.
Por isso não reaproveita a fixture `app` de `conftest.py` e repete aqui o
`DATABASE_URL` para uma porta sem nada escutando -- e, pelo mesmo motivo
descrito em `tests/_stub_banco.py` (Windows nunca observa a recusa de
conexão e trava em `psycopg.waiting.wait_conn`), também precisa repetir
`recusar_conexao_com_banco`.
"""

from __future__ import annotations

import pytest
from sharedauth.ratelimit import LIMITE_LOGIN_PADRAO

from _stub_banco import recusar_conexao_com_banco

from app.app_factory import AppConfig, criar_app_ict


@pytest.fixture
def client_com_rate_limit(monkeypatch):
    # Deliberadamente SEM CONFORTO_TESTING=1: `_criar_limiter` usa
    # `enabled=not app.testing`, e a fixture geral (conftest.py) desliga o
    # rate-limiter para o resto da suíte não se atropelar no mesmo limite.
    monkeypatch.delenv("CONFORTO_TESTING", raising=False)
    monkeypatch.setenv("CONFORTO_SECRET_KEY", "chave-de-teste-nao-usada-em-execucao-real")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://test:test@localhost:5999/test")
    recusar_conexao_com_banco(monkeypatch)
    app = criar_app_ict(
        AppConfig(
            debug=False,
            host="127.0.0.1",
            port=5000,
            threaded=False,
            max_content_length=1_000_000,
        )
    )
    app.config["TESTING"] = True
    return app.test_client()


def test_limite_de_login_e_dez_por_minuto():
    assert LIMITE_LOGIN_PADRAO == "10 per minute"


def test_login_bloqueia_apos_o_limite(client_com_rate_limit):
    for _ in range(10):
        resposta = client_com_rate_limit.get("/login")
        assert resposta.status_code == 200
    resposta = client_com_rate_limit.get("/login")
    assert resposta.status_code == 429
