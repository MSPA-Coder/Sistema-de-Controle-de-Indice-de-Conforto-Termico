"""Concessão e revogação de zona têm efeito na sessão já autenticada."""

import re
from uuid import uuid4

import pytest
from test_cadastro_http_postgres import acesso as acesso
from test_cadastro_http_postgres import zona
from test_operacao_http_postgres import ponte as ponte

from app import database as db
from app.seguranca import auth

pytestmark = pytest.mark.usefixtures("banco")


@pytest.fixture
def operador(ponte, banco):
    (admin, headers), _, _ = ponte
    login = "operador-" + uuid4().hex[:12]
    senha = "Senha-sintetica-operador-2026!"
    usuario = db.criar_usuario({"nome": "Operador QA", "login": login, "perfil": "operador",
                               "senha_hash": auth.gerar_hash_senha(senha)}, exigir_troca=False)
    cliente = admin.application.test_client()
    try:
        html = cliente.get("/login").get_data(as_text=True)
        token = re.search(r'name="_csrf_token"[^>]*value="([^"]+)"', html).group(1)
        assert cliente.post("/login", data={"login": login, "senha": senha, "_csrf_token": token}).status_code == 302
        html = cliente.get("/preferencias").get_data(as_text=True)
        token = re.search(r'name="_csrf_token"[^>]*value="([^"]+)"', html).group(1)
        yield admin, headers, cliente, {"X-CSRF-Token": token}, usuario["id"]
    finally:
        with banco() as conn:
            conn.execute("DELETE FROM usuarios WHERE id=?", (usuario["id"],))


def test_concessao_idempotente_e_revogacao_valem_sem_novo_login(operador):
    admin, headers, cliente, operador_headers, uid = operador
    zid = db.criar_zona(zona())["id"]
    acl = f"/usuarios/api/{uid}/zonas/{zid}"
    comando = f"/api/zonas/{zid}/calcular"
    dados = {"entradas": {"tbs": 30, "tbu": 22}}
    assert cliente.post(comando, json=dados, headers=operador_headers).status_code == 403
    for _ in range(2):
        assert admin.post(acl, json={}, headers=headers).status_code == 200
    assert [z["id"] for z in admin.get(f"/usuarios/api/{uid}/zonas").json["zonas"]] == [zid]
    assert db.usuario_tem_acesso_zona(uid, zid)
    assert cliente.post(comando, json=dados, headers=operador_headers).status_code == 200
    assert len(db.obter_leituras_recentes_zona(zid)) == 1
    assert admin.delete(acl, headers=headers).status_code == 200
    assert not db.usuario_tem_acesso_zona(uid, zid)
    assert admin.get(f"/usuarios/api/{uid}/zonas").json["zonas"] == []
    assert cliente.post(comando, json=dados, headers=operador_headers).status_code == 403
    # A administração fica fora de /api: recusa HTML redireciona à página inicial.
    resposta = cliente.post(acl, json={}, headers=operador_headers)
    assert resposta.status_code == 302 and resposta.location == "/"
    assert not db.usuario_tem_acesso_zona(uid, zid)
    assert len(db.obter_leituras_recentes_zona(zid)) == 1


@pytest.mark.parametrize("metodo", ["get", "post", "delete"])
def test_acl_recusa_usuario_inexistente_sem_criar_associacoes(acesso, banco, metodo):
    cliente, headers = acesso
    zid = db.criar_zona(zona())["id"]
    sufixo = "" if metodo == "get" else f"/{zid}"
    resposta = getattr(cliente, metodo)("/usuarios/api/2147483647/zonas" + sufixo, headers=headers)
    assert resposta.status_code == 404
    with banco() as conn:
        assert conn.execute("SELECT count(*) AS total FROM usuario_zonas").fetchone()["total"] == 0


def test_acl_recusa_zona_inexistente(operador):
    admin, headers, _, _, uid = operador
    resposta = admin.post(f"/usuarios/api/{uid}/zonas/2147483647", json={}, headers=headers)
    assert resposta.status_code == 302 and resposta.location == "/"
    assert db.listar_zonas_do_usuario(uid) == []
