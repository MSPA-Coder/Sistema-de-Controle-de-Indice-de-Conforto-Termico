"""O login tem limite de tentativas.

O rate-limit de "5 per minute" documentado no login nunca chegou a
funcionar: usava um `Limiter` órfão (`auth.obter_limiter()`), criado sem
`app=` e sem `init_app()` -- seu hook de enforcement nunca era registrado
neste app, e na prática só o default global (20/min) protegia a rota.
Reproduzido de fato antes desta correção: 11 requisições seguidas
devolviam 200 (ver `tests/conftest.py` para a fixture geral, que desliga o
rate-limiter via `CONFORTO_TESTING=1` -- este arquivo cria a própria app
SEM essa variável, de propósito, para poder medir o limite de verdade).

A correção reaproveita o limiter de verdade da aplicação
(`app.extensions["conforto_rate_limiter"]`) e usa o mesmo limite
padronizado nos três apps Flask do mantenedor (`LIMITE_LOGIN_PADRAO`,
10/min) em vez do 5/min original -- ver PLANO_UNIFICAR_AUTENTICACAO.md no
repositório `_manutencao`, seção 11 (Fase 4).
"""

from __future__ import annotations

import pytest
from sharedauth.ratelimit import LIMITE_LOGIN_PADRAO

from app.app_factory import AppConfig, criar_app_ict


@pytest.fixture
def client_com_rate_limit(monkeypatch):
    # Deliberadamente SEM CONFORTO_TESTING=1: `_criar_limiter` usa
    # `enabled=not app.testing`, e a fixture geral (conftest.py) desliga o
    # rate-limiter para o resto da suíte não se atropelar no mesmo limite.
    monkeypatch.delenv("CONFORTO_TESTING", raising=False)
    monkeypatch.setenv("CONFORTO_SECRET_KEY", "chave-de-teste-nao-usada-em-execucao-real")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://test:test@localhost:5999/test")
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
