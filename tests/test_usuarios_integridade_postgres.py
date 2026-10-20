"""Administração por HTTP conserva acesso e invalida sessões antigas."""

import pytest
from test_acl_zonas_http_postgres import operador as operador
from test_cadastro_http_postgres import acesso as acesso
from test_operacao_http_postgres import ponte as ponte

from app import database as db


def test_administrador_nao_se_exclui_ou_remove_proprio_perfil(acesso):
    cliente, headers = acesso
    with cliente.session_transaction() as sessao:
        uid = sessao["usuario_id"]
    antes = db.obter_usuario(uid)
    assert cliente.post(f"/usuarios/{uid}/excluir", headers=headers).status_code == 302
    assert db.obter_usuario(uid)["ativo"]
    resposta = cliente.post(f"/usuarios/{uid}/editar", data={**antes, "perfil": "operador", "ativo": "1"}, headers=headers)
    assert resposta.status_code == 200
    assert db.obter_usuario(uid)["perfil"] == "administrador"


@pytest.mark.parametrize("campo,valor", [("login", ""), ("perfil", "inexistente"), ("nome", "")])
def test_edicao_invalida_preserva_conta(operador, campo, valor):
    admin, headers, _, _, uid = operador
    antes = db.obter_usuario(uid)
    resposta = admin.post(f"/usuarios/{uid}/editar", data={**antes, "ativo": "1", campo: valor}, headers=headers)
    assert resposta.status_code == 200
    assert db.obter_usuario(uid) == antes


@pytest.mark.parametrize("acao", ["desativar", "senha"])
def test_alteracao_administrativa_invalida_sessao_ja_aberta(operador, acao):
    admin, headers, cliente, _, uid = operador
    usuario = db.obter_usuario(uid)
    assert cliente.get("/api/configuracao-interface").status_code == 200
    if acao == "desativar":
        assert admin.post(f"/usuarios/{uid}/editar", data={**usuario, "ativo": ""}, headers=headers).status_code == 302
        assert not db.obter_usuario(uid)["ativo"]
    else:
        assert admin.post(f"/usuarios/{uid}/redefinir-senha", headers=headers).status_code == 200
        assert db.obter_usuario(uid)["trocar_senha"]
    assert cliente.get("/api/configuracao-interface").status_code == 401


def test_operador_nao_pode_alterar_outro_usuario(operador):
    admin, _, cliente, headers, uid = operador
    with admin.session_transaction() as sessao:
        aid = sessao["usuario_id"]
    antes = db.obter_usuario(aid)
    assert cliente.post(f"/usuarios/{aid}/editar", data={"perfil": "operador"}, headers=headers).status_code == 302
    assert cliente.post(f"/usuarios/{aid}/excluir", headers=headers).status_code == 302
    assert db.obter_usuario(aid) == antes
    assert db.obter_usuario(uid)["perfil"] == "operador"
