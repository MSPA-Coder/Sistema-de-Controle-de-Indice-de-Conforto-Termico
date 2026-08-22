"""Escritas exigem token CSRF fornecido por `sharedauth.csrf` (Flask-WTF).

O nome do campo continua `_csrf_token` (configurado via
`WTF_CSRF_FIELD_NAME` em `app_factory.criar_app_ict`) para não precisar
tocar templates nem `api.js` -- por isso os testes abaixo continuam usando
esse nome, não o padrão `csrf_token` do Flask-WTF.
"""

from __future__ import annotations

from flask_wtf.csrf import generate_csrf


def test_get_nao_exige_token(client):
    resposta = client.get("/login")
    assert resposta.status_code == 200


def test_post_sem_token_e_recusado(client):
    resposta = client.post("/login", data={"login": "x", "senha": "y"})
    assert resposta.status_code == 400


def test_post_com_token_invalido_e_recusado(client):
    resposta = client.post(
        "/login",
        data={"login": "x", "senha": "y", "_csrf_token": "token-inventado"},
    )
    assert resposta.status_code == 400


def test_post_com_header_invalido_e_recusado(client):
    resposta = client.post(
        "/login",
        data={"login": "x", "senha": "y"},
        headers={"X-CSRF-Token": "token-inventado"},
    )
    assert resposta.status_code == 400


def test_formulario_de_login_traz_o_campo_do_token(client):
    corpo = client.get("/login").get_data(as_text=True)
    assert 'name="_csrf_token"' in corpo


def test_token_valido_e_aceito(app):
    # Exercita o validador direto em vez de um POST completo: um POST aceito
    # entraria na view de login, que consulta o banco -- a suíte não tem
    # banco por desenho (ver conftest.py).
    with app.test_request_context():
        from flask_wtf.csrf import validate_csrf

        validate_csrf(generate_csrf())  # não levantar é o resultado esperado


def test_referrer_policy_nao_anula_o_origin(client):
    """A causa raiz de uma falha real no projeto irmao em Django.

    `Referrer-Policy: no-referrer` faz o navegador serializar `Origin` como
    `null` também em POST de mesma origem (Fetch spec). O cabeçalho é
    compartilhado entre os quatro projetos do mantenedor; reintroduzi-lo
    aqui voltaria a propagá-lo.
    """
    assert client.get("/login").headers.get("Referrer-Policy") != "no-referrer"
