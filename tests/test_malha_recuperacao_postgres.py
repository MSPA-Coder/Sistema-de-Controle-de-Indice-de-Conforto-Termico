"""Falhas combinadas e recuperação por zona, usando persistência real."""

import pytest
from test_operacao_zonas_postgres import cadastrar
from test_operacao_zonas_postgres import malha as malha

from app import database as db


@pytest.mark.parametrize("falha", ["sensor", "escrita", "sem_confirmacao", "divergente"])
def test_falha_uma_zona_nao_interrompe_outra_e_ciclo_seguinte_recupera(malha, falha):
    gerente, valores, estados, escritas = malha
    a, ea = cadastrar("Com falha")
    b, eb = cadastrar("Saudável")
    for z, sensores in [(a, ea), (b, eb)]:
        valores.update({sensores[0]["id"]: 35, sensores[1]["id"]: 25})
        gerente.alterar_controle(z["id"], {"modo": "automatico", "acionamento_habilitado": True})
    escrever_original = gerente.zona_service._escrever_modbus_real
    ler_original = gerente.zona_service._ler_estado_atuador_real
    ativo = True

    def escrever(equipamento, ligar):
        if ativo and falha == "escrita" and equipamento["id"] == ea[2]["id"]:
            raise TimeoutError("dispositivo sintético indisponível")
        return escrever_original(equipamento, ligar)

    def ler(equipamento):
        if ativo and equipamento["id"] == ea[2]["id"]:
            if falha == "sem_confirmacao":
                return None
            if falha == "divergente":
                return False
        return ler_original(equipamento)

    gerente.zona_service._escrever_modbus_real = escrever
    gerente.zona_service._ler_estado_atuador_real = ler
    if falha == "sensor":
        valores[ea[0]["id"]] = None
    resultados = {r["zona_id"]: r for r in gerente.executar_ciclo_automatico()}
    assert resultados[b["id"]]["leitura_gravada"]
    operacionais = {e["zona_id"]: e for e in db.obter_estado_operacional_zonas()}
    assert operacionais[b["id"]]["qualidade"] == "boa"
    assert operacionais[a["id"]]["qualidade"] in {"falha", "degradada"}
    if falha == "sensor":
        assert "erro" in resultados[a["id"]]
        assert not any(eid in {e["id"] for e in ea} for eid, _ in escritas)
    else:
        assert resultados[a["id"]]["leitura_gravada"]
        assert resultados[a["id"]]["estado_confirmado"]["ventilador"] is not True
    ativo = False
    valores[ea[0]["id"]] = 35
    recuperados = {r["zona_id"]: r for r in gerente.executar_ciclo_automatico()}
    assert all("erro" not in r for r in recuperados.values())
    assert all(e["qualidade"] == "boa" and not e["falhas"] for e in db.obter_estado_operacional_zonas())
    assert estados[ea[2]["id"]] is True and estados[eb[2]["id"]] is True


def test_atuadores_do_mesmo_grupo_com_respostas_divergentes_nao_confirmam_grupo(malha):
    gerente, valores, _, _ = malha
    z, equipamentos = cadastrar()
    adicional = db.criar_equipamento(z["id"], {**equipamentos[2], "nome": "Segundo ventilador", "endereco_registrador": 20})
    valores.update({equipamentos[0]["id"]: 35, equipamentos[1]["id"]: 25})
    leitura = gerente.zona_service._ler_estado_atuador_real
    gerente.zona_service._ler_estado_atuador_real = lambda e: False if e["id"] == adicional["id"] else leitura(e)
    gerente.alterar_controle(z["id"], {"modo": "automatico", "acionamento_habilitado": True})
    resposta = gerente.executar_ciclo_automatico()[0]
    assert resposta["estado_confirmado"]["ventilador"] is None
    persistido = db.obter_estado_operacional_zonas()[0]
    assert persistido["qualidade"] == "degradada" and persistido["falhas"]
    assert persistido["confirmado"]["ventilador"] is None


def test_falhas_simultaneas_de_sensor_e_escrita_preservam_terceira_zona(malha):
    gerente, valores, _, _ = malha
    zonas = [cadastrar(nome) for nome in ("Sensor indisponível", "Atuador indisponível", "Saudável")]
    for z, equipamentos in zonas:
        valores.update({equipamentos[0]["id"]: 35, equipamentos[1]["id"]: 25})
        gerente.alterar_controle(z["id"], {"modo": "automatico", "acionamento_habilitado": True})
    valores[zonas[0][1][0]["id"]] = None
    escrever = gerente.zona_service._escrever_modbus_real
    ventilador_falho = zonas[1][1][2]["id"]
    gerente.zona_service._escrever_modbus_real = lambda e, ligar: False if e["id"] == ventilador_falho else escrever(e, ligar)
    respostas = gerente.executar_ciclo_automatico()
    assert len(respostas) == 3
    estado = {e["zona_id"]: e for e in db.obter_estado_operacional_zonas()}
    assert [estado[z["id"]]["qualidade"] for z, _ in zonas] == ["falha", "degradada", "boa"]
    assert db.obter_leituras_recentes_zona(zonas[2][0]["id"])
    valores[zonas[0][1][0]["id"]] = 35
    gerente.zona_service._escrever_modbus_real = escrever
    assert all("erro" not in r for r in gerente.executar_ciclo_automatico())
    assert all(e["qualidade"] == "boa" for e in db.obter_estado_operacional_zonas())
