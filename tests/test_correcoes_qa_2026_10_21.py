"""Correções da rodada de testes de 21/10/2026 que não precisam de PostgreSQL.

Cada teste nasceu de um defeito reproduzido contra a pilha local; o relatório
(`RELATORIO_QA_2026-10-21.md`) traz o número de cada um. A parte que só o banco
mostra (ACL das leituras agregadas, revogação de sessão, trilha de auditoria)
está em `test_correcoes_qa_postgres.py`.
"""

from __future__ import annotations

import re

import pytest
from sharedauth.session import marca_de_sessao

from app import models
from app.dados_entrada import gerador_dados
from app.dados_entrada import rotas as dados_entrada_rotas
from app.database import comum, equipamentos, zonas
from app.seguranca import auth
from app.seguranca import zonas as acl_zonas

# ---------------------------------------------------------------------------
# Validação de cadastro (defeitos 9 e 10)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("host", ["192.168.0.10", "10.0.0.1", "::1", "clp-galpao1", "plc.local"])
def test_host_valido_passa(host):
    assert equipamentos.validar_host(host) == host


@pytest.mark.parametrize(
    "host",
    [
        "",
        "http://evil/",
        "999.999.999.999",
        "192.168.11.3.1",  # IP com cinco octetos: o seed local tinha 29 assim
        "1.2.3",
        "a b",
        "-x.com",
        "x" * 300,
    ],
)
def test_host_invalido_e_recusado_com_o_campo(host):
    with pytest.raises(zonas.ZonaInvalidaError) as erro:
        equipamentos.validar_host(host)
    assert erro.value.campo == "host"
    assert "IP" in str(erro.value)


def test_normalizar_texto_recusa_o_que_virava_lixo():
    kwargs = {"maximo": 5, "erro": ValueError}
    assert comum.normalizar_texto("  ab  ", "nome", **kwargs) == "ab"
    for ruim in (None, 12, ["a"], "a\x00b", "a\nb", "abcdef"):
        with pytest.raises(ValueError):
            comum.normalizar_texto(ruim, "nome", **kwargs)


def test_exigir_booleano_nao_aceita_talvez():
    assert comum.exigir_booleano(True, "ativa", erro=ValueError) is True
    assert comum.exigir_booleano("não", "ativa", erro=ValueError) is False
    with pytest.raises(ValueError):
        comum.exigir_booleano("talvez", "ativa", erro=ValueError)


@pytest.mark.parametrize(
    "mudanca,campo",
    [
        ({"nome": None}, "nome"),
        ({"nome": "a\x00b"}, "nome"),
        ({"nome": "   "}, "nome"),
        ({"ativa": "talvez"}, "ativa"),
        ({"especie": ["frangos"]}, "especie"),
        ({"ciclos_expiracao_leitura": 9}, "ciclos_expiracao_leitura"),
    ],
)
def test_zona_invalida_aponta_o_campo(mudanca, campo):
    dados = {"nome": "QA", "especie": "frangos", "indice": "ITU", **mudanca}
    with pytest.raises(zonas.ZonaInvalidaError) as erro:
        zonas._validar_zona(dados)
    assert erro.value.campo == campo


def test_equipamento_tcp_sem_host_aponta_o_host():
    dados = {
        "tipo": "ventilador",
        "nome": "V1",
        "modo_conexao": "tcp",
        "host": "",
        "tipo_registrador": "coil",
        "endereco_registrador": 1,
    }
    with pytest.raises(zonas.ZonaInvalidaError) as erro:
        equipamentos.validar_equipamento(dados)
    assert erro.value.campo == "host"
    assert "Host" in str(erro.value) or "host" in str(erro.value)


# ---------------------------------------------------------------------------
# Datas nos extremos do calendário (defeito 8) e Stull (defeito 3)
# ---------------------------------------------------------------------------


def test_data_fim_no_extremo_do_calendario_nao_estoura():
    inicio, fim = models.limites_utc_do_periodo("2026-10-01", "9999-12-31")
    assert inicio is not None
    assert fim is None  # sem limite superior: não existe "o dia seguinte"
    assert models.limites_utc_do_periodo("0001-01-01", None)[1] is None


def test_bulbo_umido_de_stull_nao_passa_do_bulbo_seco_por_arredondamento():
    # Reproduzido em 19-20/09 e 12-13/10/2026: UR perto de 100 % e calor.
    for ur in (99.5, 99.8, 100.0):
        for tbs in (20.0, 25.0, 30.0):
            assert gerador_dados.calcular_bulbo_umido(tbs, ur) <= tbs


def test_bulbo_umido_muito_acima_do_seco_continua_sendo_recusado(monkeypatch):
    monkeypatch.setattr(gerador_dados.math, "atan", lambda _x: 10.0)
    with pytest.raises(gerador_dados.GeracaoDadosError):
        gerador_dados.calcular_bulbo_umido(20.0, 90.0)


# ---------------------------------------------------------------------------
# CSV de dados de entrada (defeito 7)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("texto", ["=1+1", "+1", "-1+2", "@SUM(A1)", "\tx", "\rx"])
def test_csv_neutraliza_formula(texto):
    assert dados_entrada_rotas._neutralizar_formula(texto) == "'" + texto


@pytest.mark.parametrize("valor", ["Aviário 1", "", -3.5, 0, None])
def test_csv_nao_mexe_no_que_nao_e_formula(valor):
    assert dados_entrada_rotas._neutralizar_formula(valor) == valor


# ---------------------------------------------------------------------------
# Filtro de zonas pela ACL (defeito 1) -- a regra pura, sem banco
# ---------------------------------------------------------------------------


def test_filtrar_por_zona_respeita_as_permitidas():
    itens = [{"zona_id": 1}, {"zona_id": 2}, {"zona_id": None}]
    assert acl_zonas.filtrar_por_zona(itens, None) == itens
    assert acl_zonas.filtrar_por_zona(itens, frozenset({2})) == [{"zona_id": 2}]
    assert acl_zonas.filtrar_por_zona(itens, frozenset()) == []


def test_zonas_permitidas_administrador_e_global_e_anonimo_nao_ve_nada(monkeypatch):
    assert acl_zonas.zonas_permitidas({"id": 1, "perfil": "administrador"}) is None
    assert acl_zonas.zonas_permitidas(None) == frozenset()
    monkeypatch.setattr(
        "app.database.listar_zonas_do_usuario", lambda _uid: [{"id": 3}, {"id": 7}]
    )
    assert acl_zonas.zonas_permitidas({"id": 9, "perfil": "analista"}) == frozenset({3, 7})


# ---------------------------------------------------------------------------
# Corpo JSON que não é objeto (defeito 2) e cabeçalhos (defeito 13)
# ---------------------------------------------------------------------------


@pytest.fixture
def admin(app, client, monkeypatch):
    monkeypatch.setattr(
        auth.db,
        "obter_usuario",
        lambda _id: {
            "id": 1,
            "nome": "Admin",
            "login": "admin",
            "perfil": "administrador",
            "ativo": True,
        },
    )
    monkeypatch.setattr(auth.db, "obter_hash_de_senha", lambda _id: "hash-de-teste")
    monkeypatch.setattr(auth.db, "sessao_revogada", lambda _sid: False)
    with client.session_transaction() as sessao:
        sessao["usuario_id"] = 1
        sessao[auth.CHAVE_MARCA_DE_SENHA] = marca_de_sessao(
            "hash-de-teste", chave_secreta=app.secret_key
        )
    token = re.search(
        r'name="csrf-token" content="([^"]+)"|name="_csrf_token"[^>]*value="([^"]+)"',
        client.get("/preferencias").get_data(as_text=True),
    )
    assert token, "a tela autenticada precisa trazer o token CSRF"
    client.csrf = {"X-CSRF-Token": token.group(1) or token.group(2)}
    return client


@pytest.mark.parametrize("corpo", [[1], "x", 123, True])
@pytest.mark.parametrize(
    "metodo,caminho",
    [
        ("post", "/api/configuracoes"),
        ("post", "/api/zonas"),
        ("put", "/api/zonas/1"),
        ("post", "/api/zonas/1/calcular"),
        ("post", "/api/dados-entrada/gerar"),
        ("put", "/api/dados-entrada/configuracoes"),
    ],
)
def test_corpo_json_que_nao_e_objeto_recebe_400_e_nao_500(admin, metodo, caminho, corpo):
    resposta = getattr(admin, metodo)(caminho, json=corpo, headers=admin.csrf)
    assert resposta.status_code == 400, (caminho, corpo, resposta.status_code)
    assert "erro" in resposta.get_json()


def test_paginas_html_e_api_nao_ficam_em_cache(admin):
    for caminho in ("/preferencias", "/api/configuracao-interface"):
        cache = admin.get(caminho).headers.get("Cache-Control", "")
        assert "no-store" in cache, caminho


def test_hsts_so_com_https(admin, app):
    assert "Strict-Transport-Security" not in admin.get("/preferencias").headers
    com_tls = admin.get("/preferencias", base_url="https://localhost")
    assert "Strict-Transport-Security" in com_tls.headers


# ---------------------------------------------------------------------------
# Auditoria: o autor vem de `g.usuario` (defeito 4)
# ---------------------------------------------------------------------------


def test_ator_da_auditoria_e_o_usuario_autenticado(app):
    from app.seguranca import audit_log

    with app.test_request_context("/"):
        from flask import g

        g.usuario = {"id": 7, "login": "maria", "perfil": "gestor"}
        assert audit_log._obter_usuario_atual() == {"id": 7, "login": "maria", "perfil": "gestor"}
    with app.test_request_context("/"):
        assert audit_log._obter_usuario_atual()["login"] == "anonymous"


# ---------------------------------------------------------------------------
# Tempo do login (defeito 6)
# ---------------------------------------------------------------------------


def test_login_inexistente_tambem_gasta_o_hash(client, monkeypatch):
    chamadas = []
    monkeypatch.setattr(auth.db, "obter_usuario_por_login", lambda _login: None)
    monkeypatch.setattr(
        auth, "conferir_senha", lambda senha, hash_: chamadas.append((senha, hash_)) or False
    )
    html = client.get("/login").get_data(as_text=True)
    token = re.search(r'name="_csrf_token"[^>]*value="([^"]+)"', html).group(1)
    resposta = client.post(
        "/login", data={"login": "ninguem", "senha": "Senha-qualquer-1", "_csrf_token": token}
    )
    assert resposta.status_code == 200
    assert len(chamadas) == 1 and chamadas[0][1]  # verificou contra um hash de verdade


# ---------------------------------------------------------------------------
# Tela de zonas por conta (U1) e formato do último acesso (U6)
# ---------------------------------------------------------------------------


def test_tela_de_zonas_da_conta_existe_e_esta_no_mapa_de_areas(app):
    assert auth.AREA_POR_ENDPOINT["usuarios.zonas_usuario_rota"] == "usuarios"
    assert any(r.endpoint == "usuarios.zonas_usuario_rota" for r in app.url_map.iter_rules())


def test_filtro_de_data_hora_regional(app):
    filtro = app.jinja_env.filters["data_hora_regional"]
    assert filtro(None) == ""
    assert filtro("texto qualquer") == "texto qualquer"
    # 15:00 UTC é 12:00 em Brasília (UTC-3, sem horário de verão desde 2019).
    assert filtro("2026-10-21T15:00:00+00:00").endswith("12:00")
