"""Guardas de runtime que não exigem PostgreSQL nem um servidor HTTP real."""

from __future__ import annotations

import pytest
from werkzeug.exceptions import BadRequest, InternalServerError

from app.app_factory import (
    MENSAGEM_ERRO_INTERNO,
    AppConfig,
    _validar_debug,
    _validar_testing,
)


def _config(*, debug: bool, host: str, development: bool) -> AppConfig:
    return AppConfig(
        debug=debug,
        host=host,
        port=5000,
        threaded=True,
        max_content_length=1_000_000,
        development=development,
    )


def test_debug_exige_desenvolvimento_explicito():
    with pytest.raises(RuntimeError, match="CONFORTO_DEVELOPMENT"):
        _validar_debug(_config(debug=True, host="127.0.0.1", development=False))


def test_debug_exige_loopback_mesmo_em_desenvolvimento():
    with pytest.raises(RuntimeError, match="loopback"):
        _validar_debug(_config(debug=True, host="0.0.0.0", development=True))


def test_debug_local_explicito_e_aceito():
    _validar_debug(_config(debug=True, host="127.0.0.1", development=True))


def test_testing_exige_desenvolvimento_explicito():
    """`CONFORTO_TESTING` não é um rótulo: ela remove duas proteções.

    Ligada sozinha, desliga o rate limiter inteiro (`_criar_limiter` usa
    `habilitado=not app.testing`) e permite subir com chave de sessão gerada
    em vez de exigida. Antes, o que impedia isso em produção era apenas a
    variável não estar em nenhum Compose.
    """
    with pytest.raises(RuntimeError, match="CONFORTO_DEVELOPMENT"):
        _validar_testing(True, _config(debug=False, host="127.0.0.1", development=False))


def test_testing_exige_loopback_mesmo_em_desenvolvimento():
    with pytest.raises(RuntimeError, match="loopback"):
        _validar_testing(True, _config(debug=False, host="0.0.0.0", development=True))


def test_testing_local_explicito_e_aceito():
    _validar_testing(True, _config(debug=False, host="127.0.0.1", development=True))


def test_sem_testing_nao_ha_exigencia_nenhuma():
    # O caminho de produção normal: a variável desligada não exige nada.
    _validar_testing(False, _config(debug=False, host="0.0.0.0", development=False))


def test_api_nao_expoe_descricao_de_http_500(app, client, caplog, monkeypatch):
    @app.get("/api/teste-http-500")
    def erro_http_500():
        raise InternalServerError(description="detalhe interno confidencial")

    monkeypatch.setattr(app, "before_request_funcs", {})
    with caplog.at_level("ERROR"):
        resposta = client.get("/api/teste-http-500")

    assert resposta.status_code == 500
    assert resposta.get_json() == {"erro": MENSAGEM_ERRO_INTERNO}
    assert "detalhe interno confidencial" not in resposta.get_data(as_text=True)
    assert "detalhe interno confidencial" in caplog.text


def test_api_preserva_mensagem_controlada_de_http_4xx(app, client, monkeypatch):
    @app.get("/api/teste-http-400")
    def erro_http_400():
        raise BadRequest(description="entrada inválida")

    monkeypatch.setattr(app, "before_request_funcs", {})
    resposta = client.get("/api/teste-http-400")

    assert resposta.status_code == 400
    assert resposta.get_json() == {"erro": "entrada inválida"}
