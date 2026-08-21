"""A Content-Security-Policy e os cabecalhos defensivos estao fechados.

Este arquivo existe com o mesmo nome nos quatro projetos do mantenedor. Uma
politica que afrouxa nao quebra nada visivelmente -- a pagina continua
carregando --, entao so um teste percebe.

Ate esta rodada a afirmacao aqui era sobre as constantes, com um teste de
fiacao por inspecao de codigo-fonte no fim: o comentario da suite dizia que o
factory conectava ao banco e que uma resposta HTTP de verdade seria
impossivel. Nao era o caso -- `criar_app_ict()` nao toca o banco na criacao,
como `conftest.py` registra --, e agora o arquivo afirma sobre a resposta,
igual aos outros tres projetos.
"""

from __future__ import annotations

import pytest

from app.app_factory import CABECALHOS_SEGURANCA, CONTENT_SECURITY_POLICY

CABECALHOS_ESPERADOS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "same-origin",
    "Cross-Origin-Opener-Policy": "same-origin",
    "X-Permitted-Cross-Domain-Policies": "none",
}


@pytest.mark.parametrize(("cabecalho", "valor"), sorted(CABECALHOS_ESPERADOS.items()))
def test_cabecalho_defensivo_declarado(cabecalho, valor):
    assert CABECALHOS_SEGURANCA.get(cabecalho) == valor


def test_permissions_policy_restringe_dispositivos():
    # `browsing-topics` entrou no conjunto comum vindo do ControleRendaVariavel,
    # onde o Flask-Talisman o escrevia sozinho: recusar a Topics API e
    # estritamente mais restritivo que nao declarar nada.
    politica = CABECALHOS_SEGURANCA.get("Permissions-Policy", "")
    for recurso in (
        "camera=()",
        "microphone=()",
        "geolocation=()",
        "browsing-topics=()",
    ):
        assert recurso in politica


def test_csp_fecha_img_src_sem_data_uri():
    # O `data:` que estava aqui era sobra: nada neste projeto usa URI `data:`,
    # e o favicon e arquivo servido por rota, nao SVG embutido.
    assert "img-src 'self'" in CONTENT_SECURITY_POLICY
    assert "data:" not in CONTENT_SECURITY_POLICY


def test_csp_fechada_na_propria_origem():
    assert "default-src 'self'" in CONTENT_SECURITY_POLICY
    assert "script-src 'self'" in CONTENT_SECURITY_POLICY
    assert "style-src 'self'" in CONTENT_SECURITY_POLICY
    assert "object-src 'none'" in CONTENT_SECURITY_POLICY
    assert "frame-ancestors 'none'" in CONTENT_SECURITY_POLICY


def test_csp_nao_admite_inline_nem_origem_externa():
    assert "unsafe-inline" not in CONTENT_SECURITY_POLICY
    assert "unsafe-eval" not in CONTENT_SECURITY_POLICY
    assert "http://" not in CONTENT_SECURITY_POLICY
    assert "https://" not in CONTENT_SECURITY_POLICY


@pytest.mark.parametrize(("cabecalho", "valor"), sorted(CABECALHOS_ESPERADOS.items()))
def test_cabecalho_defensivo_chega_na_resposta(client, cabecalho, valor):
    # Sem isto, alguem poderia deixar as constantes corretas e parar de
    # aplica-las: os testes acima continuariam verdes e nenhuma resposta
    # carregaria os cabecalhos. Antes esta garantia era inspecao do
    # codigo-fonte do factory procurando o nome das constantes -- fragil, e
    # quebrou assim que o registro passou a vir da biblioteca. Agora e a
    # resposta de verdade.
    assert client.get("/login").headers.get(cabecalho) == valor


def test_csp_chega_na_resposta(client):
    assert client.get("/login").headers.get("Content-Security-Policy") == (
        CONTENT_SECURITY_POLICY
    )
