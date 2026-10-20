"""Ciclo e comandos reais do coletor; apenas a rede industrial é substituída."""

from threading import Event

import pytest

from app import database as db
from app.coletor.controle import GerenciadorControleZonas, ModoOperacaoError, ZonaOcupadaError
from app.database.configuracoes import limpar_cache_configuracoes
from app.termico.zona_service import ZonaCalculoError, ZonaService

pytestmark = pytest.mark.usefixtures("banco")


@pytest.fixture
def malha(banco):
    limpar_cache_configuracoes()
    db.salvar_configuracoes({"habilitarEquipamentos": True, "enviarEmails": False})
    valores, estados, escritas = {}, {}, []

    def escrever(equipamento, ligar):
        escritas.append((equipamento["id"], ligar))
        estados[equipamento["id"]] = ligar
        return True

    servico = ZonaService(
        db.obter_zona, db.salvar_leitura, db.obter_configuracoes,
        db.obter_historico_por_zona, db.salvar_estado_equipamentos,
        db.obter_controle_zona,
        ler_modbus_real=lambda e: valores.get(e["id"]),
        escrever_modbus_real=escrever,
        ler_estado_atuador_real=lambda e: estados.get(e["id"]),
        salvar_leitura_recente=db.salvar_leitura_recente_zona,
    )
    yield GerenciadorControleZonas(servico), valores, estados, escritas
    limpar_cache_configuracoes()


def cadastrar(nome="Galpão", ativa=True):
    zona = db.criar_zona({"nome": nome, "especie": "frangos", "indice": "ITU", "ativa": ativa})
    equipamentos = []
    for tipo, campo in [("sensor", "tbs"), ("sensor", "tbu"), ("ventilador", None), ("nebulizador", None)]:
        equipamentos.append(db.criar_equipamento(zona["id"], {
            "nome": f"{nome}-{campo or tipo}", "tipo": tipo, "campo_medido": campo,
            "modo_conexao": "tcp", "host": "sensor.invalid", "porta": 502,
            "tipo_registrador": "holding", "endereco_registrador": len(equipamentos),
        }))
    return zona, equipamentos


def test_cadastro_controle_e_exclusao_preservam_historico(malha):
    gerente, _, _, _ = malha
    zona, equipamentos = cadastrar()
    zid = zona["id"]
    assert db.obter_controle_zona(zid)["acionamento_habilitado"] is False
    assert "host" not in db.listar_zonas()[0]["equipamentos"][0]
    assert db.listar_zonas(com_fiacao=True)[0]["equipamentos"][0]["host"] == "sensor.invalid"
    resultado = gerente.calcular_manual(zid, {"tbs": 30, "tbu": 22})
    assert resultado["leitura_gravada"] is True
    assert resultado["estado_confirmado"] == {"ventilador": None, "nebulizador": None}
    assert db.obter_leituras_recentes_zona(zid)[0]["valor"] == resultado["valor"]
    db.atualizar_equipamento(equipamentos[0]["id"], {**equipamentos[0], "nome": "Novo sensor"})
    assert db.obter_equipamento(equipamentos[0]["id"])["nome"] == "Novo sensor"
    assert db.excluir_equipamento(equipamentos[0]["id"])
    assert not db.excluir_equipamento(equipamentos[0]["id"])
    assert db.excluir_zona(zid)
    assert db.obter_zona(zid) is None
    assert db.obter_equipamento(equipamentos[1]["id"]) is None
    assert db.contar_leituras() == 1


def test_ciclo_isola_falha_sensor_zona_manual_e_zona_inativa(malha):
    gerente, valores, _, escritas = malha
    ruim, _ = cadastrar("Sem resposta")
    boa, sensores = cadastrar("Saudável")
    manual, _ = cadastrar("Manual")
    inativa, _ = cadastrar("Inativa", ativa=False)
    for zona in (ruim, boa, inativa):
        gerente.alterar_controle(zona["id"], {"modo": "automatico", "acionamento_habilitado": True})
    valores.update({sensores[0]["id"]: 35, sensores[1]["id"]: 25})
    resultados = gerente.executar_ciclo_automatico()
    assert {r["zona_id"] for r in resultados} == {ruim["id"], boa["id"]}
    assert "erro" in resultados[0]
    assert resultados[1]["leitura_gravada"]
    assert db.obter_status_coletor()["online"]
    estados = {e["zona_id"]: e for e in db.obter_estado_operacional_zonas()}
    assert estados[ruim["id"]]["qualidade"] == "falha"
    assert estados[boa["id"]]["qualidade"] == "boa"
    assert estados[manual["id"]]["qualidade"] == "sem_leitura"
    assert {eid for eid, _ in escritas} <= {e["id"] for e in sensores}
    assert any(e["acao"] == "falha" for e in db.listar_eventos_operacao(ruim["id"]))


@pytest.mark.parametrize("modo", ["desligado", "manutencao"])
def test_parada_desliga_mesmo_com_acionamento_bloqueado(malha, modo):
    gerente, _, _, escritas = malha
    zona, equipamentos = cadastrar()
    gerente.alterar_controle(zona["id"], {"acionamento_habilitado": True})
    gerente.comandar_manual(zona["id"], "ventilador", True)
    gerente.comandar_manual(zona["id"], "nebulizador", True)
    assert db.obter_estado_operacional_zonas()[0]["confirmado"] == {"ventilador": True, "nebulizador": True}
    resposta = gerente.alterar_controle(zona["id"], {"modo": modo, "acionamento_habilitado": False})
    assert resposta["desligamento"]["confirmado"] == {"ventilador": False, "nebulizador": False}
    assert set(escritas[-2:]) == {(equipamentos[2]["id"], False), (equipamentos[3]["id"], False)}
    with pytest.raises(ModoOperacaoError):
        gerente.calcular_manual(zona["id"], {"tbs": 30, "tbu": 22})
    with pytest.raises(ZonaCalculoError):
        gerente.comandar_manual(zona["id"], "ventilador", True)


def test_lock_recusa_mesma_zona_libera_apos_erro_e_nao_bloqueia_outra(malha):
    gerente, _, _, _ = malha
    a, _ = cadastrar("A")
    b, _ = cadastrar("B")
    with gerente._lock_zona(a["id"]):
        with pytest.raises(ZonaOcupadaError):
            gerente.calcular_manual(a["id"], {"tbs": 30, "tbu": 22})
        assert gerente.calcular_manual(b["id"], {"tbs": 20, "tbu": 18})["zona_id"] == b["id"]
    with pytest.raises(ZonaCalculoError):
        gerente.calcular_manual(a["id"], {"tbs": 900, "tbu": 22})
    assert gerente.calcular_manual(a["id"], {"tbs": 35, "tbu": 25})["zona_id"] == a["id"]
    assert gerente.zona_service.resfriador_da_zona(a["id"]) is not gerente.zona_service.resfriador_da_zona(b["id"])


@pytest.mark.parametrize("confirmacao", [None, False])
def test_comando_sem_confirmacao_nao_anuncia_sucesso_e_retry_e_limitado(malha, confirmacao):
    gerente, _, estados, escritas = malha
    zona, equipamentos = cadastrar()
    gerente.alterar_controle(zona["id"], {"acionamento_habilitado": True})
    # Fronteira de leitura do dispositivo, não o método de negócio.
    gerente.zona_service._ler_estado_atuador_real = lambda e: confirmacao
    resultado = gerente.comandar_manual(zona["id"], "ventilador", True)
    assert resultado["failsafe_ativo"]
    assert resultado["tentativas"] == 2
    assert resultado["confirmado"] is confirmacao
    assert estados[equipamentos[2]["id"]] is True
    assert len(escritas) == 2
    estado = db.obter_estado_operacional_zonas()[0]
    assert estado["desejado"]["ventilador"] is True
    assert estado["confirmado"]["ventilador"] is confirmacao
    assert estado["qualidade"] == "degradada"


@pytest.mark.parametrize("dados", [{"modo": "inexistente"}, {"acionamento_habilitado": "true"}])
def test_controle_invalido_nao_persiste(malha, dados):
    zona, _ = cadastrar()
    anterior = db.obter_controle_zona(zona["id"])
    with pytest.raises(db.ZonaInvalidaError):
        malha[0].alterar_controle(zona["id"], dados)
    assert db.obter_controle_zona(zona["id"]) == anterior


def test_zona_excluida_perde_histerese_e_historico_transitorio(malha):
    gerente, valores, _, _ = malha
    zona, sensores = cadastrar()
    valores.update({sensores[0]["id"]: 35, sensores[1]["id"]: 25})
    gerente.alterar_controle(zona["id"], {"modo": "automatico"})
    gerente.executar_ciclo_automatico()
    anterior = gerente.zona_service.resfriador_da_zona(zona["id"])
    db.excluir_zona(zona["id"])
    assert gerente.executar_ciclo_automatico() == []
    assert gerente.zona_service.resfriador_da_zona(zona["id"]) is not anterior
    assert zona["id"] not in gerente.zona_service._historicos_grafico


def test_coletor_inicia_uma_thread_processa_e_encerra_com_heartbeat(malha):
    gerente, valores, _, _ = malha
    zona, sensores = cadastrar()
    valores.update({sensores[0]["id"]: 30, sensores[1]["id"]: 22})
    db.salvar_configuracoes({"intervaloLeituraSegundos": 0.2})
    gerente.alterar_controle(zona["id"], {"modo": "automatico"})
    leu = Event()

    def ler(equipamento):
        leu.set()
        return valores.get(equipamento["id"])

    gerente.zona_service._ler_modbus_real = ler
    try:
        gerente.iniciar()
        thread = gerente._thread
        gerente.iniciar()
        assert gerente._thread is thread
        assert leu.wait(5), "o coletor não iniciou um ciclo no prazo"
    finally:
        gerente.parar()
    assert not thread.is_alive()
    assert db.obter_status_coletor()["status"] == "offline"
    assert db.contar_leituras() == 1
