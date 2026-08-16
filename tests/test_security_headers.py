"""A Content-Security-Policy e os cabecalhos defensivos estao fechados.

Este arquivo existe com o mesmo nome nos quatro projetos do mantenedor. Uma
politica que afrouxa nao quebra nada visivelmente -- a pagina continua
carregando --, entao so um teste percebe.

Diferente dos outros tres, aqui a afirmacao e sobre as constantes e nao sobre
uma resposta HTTP: o factory deste projeto conecta ao banco, e a suite minima
nao tem banco por desenho. O acoplamento entre as constantes e a resposta e
uma linha so, coberta pelo teste de fiacao no fim do arquivo.
"""

from __future__ import annotations

import inspect

import pytest

from app.app_factory import CABECALHOS_SEGURANCA, CONTENT_SECURITY_POLICY, _criar_app_base

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
    politica = CABECALHOS_SEGURANCA.get("Permissions-Policy", "")
    for recurso in ("camera=()", "microphone=()", "geolocation=()"):
        assert recurso in politica


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


def test_as_constantes_estao_ligadas_a_resposta():
    # Sem isto, alguem poderia deixar as constantes corretas e parar de
    # aplica-las: os testes acima continuariam verdes e nenhuma resposta
    # carregaria os cabecalhos.
    fonte = inspect.getsource(_criar_app_base)
    assert "CABECALHOS_SEGURANCA" in fonte
    assert "CONTENT_SECURITY_POLICY" in fonte
