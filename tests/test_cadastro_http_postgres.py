"""Cadastro público com autenticação, CSRF, auditoria e PostgreSQL reais."""

import re
from uuid import uuid4

import pytest

from app import database as db
from app.app_factory import AppConfig, criar_app_ict
from app.database.configuracoes import limpar_cache_configuracoes
from app.seguranca import auth

pytestmark = pytest.mark.usefixtures("banco")


@pytest.fixture
def acesso(banco, monkeypatch):
    monkeypatch.setenv("CONFORTO_TESTING", "1")
    monkeypatch.setenv("CONFORTO_SECRET_KEY", "qa-http-sintetico-sem-uso-operacional")
    config = AppConfig(False, "127.0.0.1", 5000, False, 1_000_000, development=True)
    app = criar_app_ict(config)
    login = "qa-" + uuid4().hex[:12]
    usuario = db.criar_usuario({"nome": "QA", "login": login, "perfil": "administrador",
                               "senha_hash": auth.gerar_hash_senha("Senha-sintetica-2026!")}, exigir_troca=False)
    cliente = app.test_client()
    html = cliente.get("/login").get_data(as_text=True)
    token = re.search(r'name="_csrf_token"[^>]*value="([^"]+)"', html).group(1)
    assert cliente.post("/login", data={"login": login, "senha": "Senha-sintetica-2026!", "_csrf_token": token}).status_code == 302
    # O login renova a sessão; o próximo formulário entrega o token novo.
    html = cliente.get("/preferencias").get_data(as_text=True)
    token = re.search(r'name="_csrf_token"[^>]*value="([^"]+)"', html).group(1)
    limpar_cache_configuracoes()
    try:
        yield cliente, {"X-CSRF-Token": token}
    finally:
        with banco() as conn:
            conn.execute("DELETE FROM usuarios WHERE id=?", (usuario["id"],))
        limpar_cache_configuracoes()


def zona(nome="QA"):
    return {"nome": nome, "especie": "frangos", "indice": "ITU"}


def equipamento(**mudancas):
    return {"nome": "Sensor", "tipo": "sensor", "campo_medido": "tbs", "modo_conexao": "tcp",
            "host": "sensor.invalid", "tipo_registrador": "holding", "endereco_registrador": 7, **mudancas}


def test_equipamento_de_outra_zona_nao_muda_apos_resposta_404(acesso):
    cliente, headers = acesso
    a = db.criar_zona(zona("A"))
    b = db.criar_zona(zona("B"))
    sensor = db.criar_equipamento(b["id"], equipamento())
    response = cliente.put(f"/api/zonas/{a['id']}/equipamentos/{sensor['id']}",
                           json=equipamento(nome="Não pode gravar"), headers=headers)
    assert response.status_code == 404
    assert db.obter_equipamento(sensor["id"])["nome"] == "Sensor"


def test_cadastro_http_persiste_alteracoes_e_auditoria(acesso):
    cliente, headers = acesso
    response = cliente.post("/api/zonas", json=zona(), headers=headers)
    assert response.status_code == 201
    zid = response.json["id"]
    assert cliente.put(f"/api/zonas/{zid}", json=zona("Atualizada"), headers=headers).status_code == 200
    response = cliente.post(f"/api/zonas/{zid}/equipamentos", json=equipamento(), headers=headers)
    assert response.status_code == 201
    eid = response.json["id"]
    assert cliente.put(f"/api/zonas/{zid}/equipamentos/{eid}", json=equipamento(nome="Atualizado"), headers=headers).status_code == 200
    assert cliente.get(f"/api/zonas/{zid}").json["equipamentos"][0]["nome"] == "Atualizado"
    assert cliente.delete(f"/api/zonas/{zid}/equipamentos/{eid}", headers=headers).status_code == 200
    assert cliente.delete(f"/api/zonas/{zid}", headers=headers).status_code == 200
    assert db.obter_zona(zid) is None
    response = cliente.get("/api/auditoria?limite=20")
    assert response.status_code == 200 and response.json["eventos"]


@pytest.mark.parametrize("metodo,caminho,dados,esperado", [
    ("post", "/api/zonas", {"nome": "inválida"}, 400),
    ("put", "/api/zonas/2147483647", zona(), 404),
    ("delete", "/api/zonas/2147483647", None, 404),
    ("post", "/api/zonas/2147483647/equipamentos", equipamento(), 404),
    ("put", "/api/zonas/2147483647/equipamentos/2147483647", equipamento(), 404),
    ("delete", "/api/zonas/2147483647/equipamentos/2147483647", None, 404),
    ("get", "/api/auditoria?limite=inválido", None, 400),
])
def test_cadastro_invalido_ou_inexistente_recusa_sem_escrita(acesso, metodo, caminho, dados, esperado):
    cliente, headers = acesso
    response = getattr(cliente, metodo)(caminho, json=dados, headers=headers)
    assert response.status_code == esperado
    assert db.listar_zonas() == []
