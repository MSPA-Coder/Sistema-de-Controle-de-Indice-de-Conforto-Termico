"""Recusas da persistência conservam suas exceções e não gravam leitura."""

import random

import pytest

from app import database as db
from app.modbus.modbus_simulador import SimuladorModbusZonas
from app.termico import thermal_indices as ti
from app.termico.zona_service import ZonaService

pytestmark = pytest.mark.usefixtures("banco")


def test_zona_ausente_recebe_erro_de_dominio():
    with pytest.raises(db.ZonaNaoEncontradaError):
        db.salvar_leitura("frangos", "ITU", 70, "Conforto", {}, zona_id=99999999)
    assert db.contar_leituras() == 0


def test_leitura_incompativel_nao_grava_e_caso_valido_continua_funcionando():
    zona = db.criar_zona({"nome": "Zona sintética", "especie": "frangos", "indice": "ITU"})
    with pytest.raises(db.ZonaInvalidaError):
        db.salvar_leitura("bovinos", "ITU", 70, "Conforto", {}, zona_id=zona["id"])
    assert db.contar_leituras() == 0
    assert db.salvar_leitura("frangos", "ITU", 70, "Conforto", {}, zona_id=zona["id"])
    assert db.contar_leituras() == 1


@pytest.mark.parametrize("indice", ["ITU", "ITUV", "IGNU"])
def test_ciclo_simulado_persiste_sem_acessar_hardware(indice):
    zona = db.criar_zona({"nome": "Ciclo sintético", "especie": "frangos", "indice": indice})
    for endereco, campo in enumerate(ti.CAMPOS_POR_INDICE[indice]):
        db.criar_equipamento(
            zona["id"],
            {
                "tipo": "sensor",
                "nome": campo,
                "modo_conexao": "tcp",
                "host": "hardware-nao-deve-ser-acessado.invalid",
                "tipo_registrador": "input",
                "endereco_registrador": endereco,
                "campo_medido": campo,
            },
        )
    anterior = db.obter_configuracoes(usar_cache=False)
    db.salvar_configuracoes({"modoSimuladoZonas": True, "altitudeMetros": 0})
    try:
        service = ZonaService(
            obter_zona=db.obter_zona,
            salvar_leitura=db.salvar_leitura,
            obter_configuracoes=db.obter_configuracoes,
            obter_historico=db.obter_historico_por_zona,
            salvar_estado_equipamentos=db.salvar_estado_equipamentos,
            obter_controle_zona=db.obter_controle_zona,
            salvar_leitura_recente=db.salvar_leitura_recente_zona,
        )
        simulador = SimuladorModbusZonas(
            db.obter_zona,
            lambda zona_id: service.resfriador_da_zona(zona_id).estado()["ativo"],
            rng_por_zona=lambda zona_id: random.Random(20261018 + zona_id),
        )
        service.definir_simulador(simulador)
        respostas = [service.calcular(zona["id"]) for _ in range(5)]
        assert all(r["modo_simulado"] and not r["sensores_com_falha"] for r in respostas)
        assert respostas[0]["leitura_gravada"]
        assert db.obter_historico_por_zona(zona["id"])
        assert len(db.obter_leituras_recentes_zona(zona["id"])) == 5
    finally:
        db.salvar_configuracoes(anterior)
