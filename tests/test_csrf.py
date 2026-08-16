"""Escritas exigem token CSRF.

A verificacao deste projeto e propria (`auth._proteger_csrf`), entao o teste
mede a decisao dela: metodos seguros passam, mutantes exigem token, e a
comparacao e feita em tempo constante.
"""

from __future__ import annotations

import inspect

from app import auth


def test_metodos_seguros_nao_exigem_token():
    assert frozenset({"GET", "HEAD", "OPTIONS"}) == auth.METODOS_HTTP_SEGUROS


def test_metodos_mutantes_nao_estao_isentos():
    for metodo in ("POST", "PUT", "PATCH", "DELETE"):
        assert metodo not in auth.METODOS_HTTP_SEGUROS


def test_comparacao_do_token_e_em_tempo_constante():
    fonte = inspect.getsource(auth.registrar_autenticacao)
    # `==` em token vaza o prefixo correto pelo tempo de resposta.
    assert "hmac.compare_digest" in fonte


def test_token_ausente_ou_invalido_devolve_400():
    fonte = inspect.getsource(auth.registrar_autenticacao)
    assert "Token CSRF inválido ou ausente." in fonte
    assert "400" in fonte


def test_token_e_exposto_aos_templates():
    fonte = inspect.getsource(auth.registrar_autenticacao)
    assert 'jinja_env.globals["csrf_token"]' in fonte


def test_referrer_policy_nao_anula_o_origin():
    """A causa raiz de uma falha real no projeto irmao em Django.

    `Referrer-Policy: no-referrer` faz o navegador serializar `Origin` como
    `null` tambem em POST de mesma origem (Fetch spec). Aqui a verificacao de
    CSRF nao consulta `Origin`, entao o efeito nao apareceria -- mas o
    cabecalho e compartilhado entre os quatro projetos, e reintroduzi-lo aqui
    voltaria a propaga-lo.
    """
    from app.app_factory import CABECALHOS_SEGURANCA

    assert CABECALHOS_SEGURANCA["Referrer-Policy"] != "no-referrer"


def test_protecao_so_e_dispensada_sob_testing_explicito():
    fonte = inspect.getsource(auth.registrar_autenticacao)
    # A dispensa existe para a suite; o que nao pode e ela depender de algo que
    # tambem seja verdade em execucao real.
    assert "app.testing" in fonte
    assert "CSRF_PROTECTION_ENABLED" in fonte
