"""API real do coletor sobre banco e simulação exclusivos do piloto."""

import os

from waitress import serve

from app.app_factory import AppConfig, criar_app_coletor

if os.environ.get("BROWSER_TEST_SERVER") != "1":
    raise RuntimeError("Use somente compose.browser.yaml.")

app = criar_app_coletor(AppConfig(False, "127.0.0.1", 5000, True, 1_000_000, True))
serve(app, host="0.0.0.0", port=5000, threads=4)
