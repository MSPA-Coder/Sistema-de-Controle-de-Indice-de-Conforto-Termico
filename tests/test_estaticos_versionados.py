"""Este app instalou `sharedauth.estaticos`, e as páginas recebem a URL versionada."""

from __future__ import annotations

import re

from flask import url_for
from sharedauth.ui import UM_ANO_EM_SEGUNDOS


def test_login_referencia_estaticos_com_a_versao(client):
    pagina = client.get("/login").get_data(as_text=True)
    referencias = re.findall(r'(?:href|src)="(/static/[^"]+)"', pagina)
    assert any("/static/css/style.css" in r for r in referencias)
    for referencia in referencias:
        assert re.fullmatch(r"[^?]+\?v=[0-9a-f]{12}", referencia), referencia


def test_estatico_versionado_vem_com_um_ano_de_cache(app, client):
    with app.test_request_context():
        url = url_for("static", filename="css/style.css")
    cache = client.get(url).cache_control
    assert cache.max_age == UM_ANO_EM_SEGUNDOS
    assert cache.immutable
    assert "no-store" not in client.get(url).headers.get("Cache-Control", "")
