"""Guardas de runtime que não exigem PostgreSQL nem um servidor HTTP real."""

from __future__ import annotations

import pytest

from app.app_factory import AppConfig, _validar_debug


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
