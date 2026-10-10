"""Formato regional (Brasil/EUA) por usuário: só apresentação.

Risco que protege: o usuário escolher EUA e ver data ou número em formato
trocado pela metade, ou a escolha de um usuário vazar para a requisição
seguinte. O que é gravado, importado e calculado não passa por esta camada e
não deve mudar.

A suíte não tem banco (ver `conftest.py`): a persistência é substituída e o que
se exercita é a decisão das rotas e o que chega ao HTML.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path

import pytest
from sharedauth.session import marca_de_sessao

from app.nucleo import regional
from app.nucleo.regional import REGIONAL_FORMAT_BR, REGIONAL_FORMAT_US, normalize_regional_format
from app.seguranca import auth

RAIZ = Path(__file__).resolve().parent.parent
HASH_EM_VIGOR = "hash-de-teste"


def _usuario(formato: str = "br", perfil: str = "administrador") -> dict:
    return {
        "id": 1, "nome": "Fulano", "login": "fulano", "perfil": perfil, "ativo": True,
        "trocar_senha": False, "formato_regional": formato,
    }


@pytest.fixture
def entrar(app, client, monkeypatch):
    def logar(formato: str = "br"):
        monkeypatch.setattr(auth.db, "obter_usuario", lambda _id: _usuario(formato))
        monkeypatch.setattr(auth.db, "obter_hash_de_senha", lambda _id: HASH_EM_VIGOR)
        with client.session_transaction() as sessao:
            sessao["usuario_id"] = 1
            sessao[auth.CHAVE_MARCA_DE_SENHA] = marca_de_sessao(
                HASH_EM_VIGOR, chave_secreta=app.secret_key
            )
        return client

    return logar


def test_sem_requisicao_vale_o_formato_do_brasil():
    assert regional.formato_ativo() == REGIONAL_FORMAT_BR
    assert regional.formatar_data(date(2026, 12, 31)) == "31/12/2026"
    assert regional.formatar_data_hora(datetime(2026, 12, 31, 8, 5, 9), segundos=True) == "31/12/2026 08:05:09"


def test_formato_desconhecido_cai_no_brasil():
    assert normalize_regional_format("xx") == REGIONAL_FORMAT_BR
    assert normalize_regional_format(None) == REGIONAL_FORMAT_BR


def test_datas_e_numeros_no_formato_dos_eua():
    token = regional.ativar(REGIONAL_FORMAT_US)
    try:
        assert regional.formatar_data(date(2026, 12, 31)) == "12/31/2026"
        assert regional.formatar_dia_mes(date(2026, 12, 31)) == "12/31"
        assert regional.adaptar_numero("1.234,56") == "1,234.56"
    finally:
        regional.desativar(token)
    assert regional.adaptar_numero("1.234,56") == "1.234,56"


def test_a_tela_usa_o_formato_do_usuario_e_nao_vaza(entrar):
    cliente = entrar("us")
    assert 'data-regional="us"' in cliente.get("/").get_data(as_text=True)
    assert regional.formato_ativo() == REGIONAL_FORMAT_BR

    cliente = entrar("br")
    assert 'data-regional="br"' in cliente.get("/").get_data(as_text=True)


def test_preferencias_mostra_as_duas_opcoes_e_a_escolhida(entrar):
    html = entrar("us").get("/preferencias").get_data(as_text=True)
    assert 'name="formato_regional" value="br"' in html
    assert re.search(r'value="us"[^>]*checked', html)
    assert not re.search(r'value="br"[^>]*checked', html)


def test_preferencias_grava_para_o_proprio_usuario(app, entrar, monkeypatch):
    app.config["WTF_CSRF_ENABLED"] = False
    gravado: list = []

    def gravar(usuario_id, formato):
        gravado.append((usuario_id, formato))
        return normalize_regional_format(formato)

    monkeypatch.setattr(auth.db, "atualizar_formato_regional", gravar)
    cliente = entrar("br")

    resposta = cliente.post("/preferencias", data={"formato_regional": "us"})
    assert resposta.status_code == 302
    assert gravado == [(1, "us")]


def test_preferencias_exige_login(client):
    resposta = client.get("/preferencias", follow_redirects=False)
    assert resposta.status_code == 302
    assert "/login" in resposta.headers["Location"]
