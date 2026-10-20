"""ICT → HTTP privado → malha simulada → PostgreSQL, sem hardware externo."""

import smtplib
from email import message_from_string
from threading import Thread

import pytest
from test_cadastro_http_postgres import acesso as acesso
from test_cadastro_http_postgres import equipamento, zona
from werkzeug.serving import make_server

from app import database as db
from app.app_factory import AppConfig, criar_app_coletor
from app.coletor.estado import zona_service
from app.database.configuracoes import limpar_cache_configuracoes
from app.seguranca import auth

pytestmark = pytest.mark.usefixtures("banco")


@pytest.fixture
def ponte(acesso, monkeypatch):
    monkeypatch.setenv("CONFORTO_INTERNO_TOKEN_LEITURA", "qa-raiz-leitura-somente-sintetica")
    monkeypatch.setenv("CONFORTO_INTERNO_TOKEN_CONTROLE", "qa-raiz-controle-somente-sintetica")
    anterior = db.obter_configuracoes(usar_cache=False)
    db.salvar_configuracoes({"modoSimuladoZonas": True, "habilitarEquipamentos": True,
                             "enviarEmails": False, "habilitarSons": False})
    zona_service.limpar_historico_grafico()
    zona_service.limpar_resfriador()
    coletor = criar_app_coletor(AppConfig(False, "127.0.0.1", 5000, False, 1_000_000, True))
    servidor = make_server("127.0.0.1", 0, coletor)
    thread = Thread(target=servidor.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setenv("COLETOR_URL", f"http://127.0.0.1:{servidor.server_port}")
    try:
        yield acesso, coletor, servidor
    finally:
        servidor.shutdown()
        servidor.server_close()
        thread.join(timeout=5)
        assert not thread.is_alive()
        zona_service.limpar_historico_grafico()
        zona_service.limpar_resfriador()
        db.salvar_configuracoes(anterior)
        limpar_cache_configuracoes()


def test_calculo_controle_e_comando_atravessam_http_e_persistem(ponte):
    (cliente, headers), _, _ = ponte
    galpao = db.criar_zona(zona())
    outra = db.criar_zona(zona("Outra"))
    zid = galpao["id"]
    sensor = db.criar_equipamento(zid, equipamento())
    db.criar_equipamento(zid, equipamento(nome="Ventilador", tipo="ventilador",
                                         campo_medido=None, tipo_registrador="coil"))
    url = f"/api/zonas/{zid}"
    resposta = cliente.post(url + f"/equipamentos/{sensor['id']}/testar-conexao", json={}, headers=headers)
    assert resposta.status_code == 200 and resposta.json == {"conectado": True, "modo_simulado": True}
    assert cliente.put(url + "/controle", json={"acionamento_habilitado": True}, headers=headers).status_code == 200
    resposta = cliente.post(url + "/comando", json={"tipo": "ventilador", "ligar": True}, headers=headers)
    assert resposta.status_code == 200 and resposta.json["confirmado"] is True
    resposta = cliente.post(url + "/calcular", json={"entradas": {"tbs": 30, "tbu": 22}}, headers=headers)
    assert resposta.status_code == 200 and resposta.json["leitura_gravada"]
    assert db.obter_leituras_recentes_zona(zid)[0]["valor"] == resposta.json["valor"]
    assert db.obter_leituras_recentes_zona(outra["id"]) == []
    assert db.obter_controle_zona(outra["id"])["acionamento_habilitado"] is False


@pytest.mark.parametrize("metodo,sufixo,dados", [
    ("post", "/calcular", {"entradas": {"tbs": 900, "tbu": 22}}),
    ("put", "/controle", {"modo": "inexistente"}),
    ("put", "/controle", {"acionamento_habilitado": "true"}),
    ("post", "/comando", {"tipo": "sensor", "ligar": True}),
    ("post", "/comando", {"tipo": "ventilador", "ligar": "true"}),
    ("post", "/comando", {"tipo": 42, "ligar": True}),
])
def test_recusa_de_negocio_nao_vira_indisponibilidade_nem_gravacao(ponte, metodo, sufixo, dados):
    (cliente, headers), _, _ = ponte
    zid = db.criar_zona(zona())["id"]
    antes = db.obter_controle_zona(zid)
    resposta = getattr(cliente, metodo)(f"/api/zonas/{zid}" + sufixo, json=dados, headers=headers)
    assert resposta.status_code == 400
    assert "circuit_breaker" not in resposta.json
    assert db.obter_controle_zona(zid) == antes
    assert db.obter_leituras_recentes_zona(zid) == []


@pytest.mark.parametrize("token", ["", "qa-raiz-controle-somente-sintetica", "leitura"])
def test_token_ausente_bruto_ou_de_leitura_nao_autoriza_controle(ponte, token):
    _, coletor, _ = ponte
    zid = db.criar_zona(zona())["id"]
    if token == "leitura":
        token = auth.obter_token_interno("leitura")
    resposta = coletor.test_client().put(f"/api/interno/zonas/{zid}/controle",
                                        json={"modo": "automatico"}, headers={"X-Interno-Token": token})
    assert resposta.status_code == 403
    assert db.obter_controle_zona(zid)["modo"] == "manual"


def test_coletor_inacessivel_nao_confirma_acionamento(ponte):
    (cliente, headers), _, servidor = ponte
    zid = db.criar_zona(zona())["id"]
    antes = db.obter_controle_zona(zid)
    servidor.shutdown()
    servidor.server_close()
    resposta = cliente.put(f"/api/zonas/{zid}/controle", json={"acionamento_habilitado": True}, headers=headers)
    assert resposta.status_code == 502 and resposta.json["circuit_breaker"] == "ativo"
    assert db.obter_controle_zona(zid) == antes


@pytest.mark.parametrize("falha", [False, True])
def test_notificacao_manual_confirma_resultado_smtp_sem_perder_medicao(ponte, monkeypatch, falha):
    (cliente, headers), _, _ = ponte
    zid = db.criar_zona(zona("Galpão de pesquisa"))["id"]
    db.salvar_configuracoes({"enviarEmails": True, "statusMinimoEmail": "conforto",
                             "emailDestino": "qa@example.invalid", "smtpHost": "smtp.invalid",
                             "smtpUsuario": "qa@example.invalid", "habilitarSons": True})
    monkeypatch.setenv("SMTP_PASS", "credencial-smtp-apenas-sintetica")
    enviados = []

    class SMTP:
        def __init__(self, host, port, timeout):
            assert host == "smtp.invalid" and timeout == 10

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def starttls(self):
            self.tls = True

        def login(self, usuario, senha):
            assert self.tls and usuario == "qa@example.invalid"
            if falha:
                raise smtplib.SMTPAuthenticationError(535, b"recusa sintetica")

        def sendmail(self, remetente, destinos, conteudo):
            enviados.append((destinos, message_from_string(conteudo)))

    monkeypatch.setattr(smtplib, "SMTP", SMTP)
    resposta = cliente.post(f"/api/zonas/{zid}/calcular",
                            json={"entradas": {"tbs": 35, "tbu": 25}}, headers=headers)
    assert resposta.status_code == 200 and resposta.json["leitura_gravada"]
    assert resposta.json["email"]["enviado_de_verdade"] is (not falha)
    assert len(db.obter_leituras_recentes_zona(zid)) == 1
    if falha:
        assert enviados == []
    else:
        destinos, mensagem = enviados[0]
        assert destinos == ["qa@example.invalid"]
        corpo = mensagem.get_payload(decode=True).decode("utf-8")
        assert "Galpão de pesquisa" in corpo and "ITU" in corpo
