"""Amostras simuladas atravessam a mesma validação usada no ciclo real."""

import random

import pytest

from app.modbus.estrategias import EstadoSensor, EstrategiaResfriamento, GeradorLeituraAleatoria
from app.modbus.modbus_simulador import SimuladorModbusZonas
from app.termico import thermal_indices as ti
from app.termico.zona_service import _derivar_campos_calculaveis


@pytest.mark.parametrize("indice", ["ITU", "ITUV", "IGNU"])
def test_gerador_e_repetivel_e_suas_entradas_sao_validas(indice):
    primeiro = GeradorLeituraAleatoria(random.Random(20261018))
    segundo = GeradorLeituraAleatoria(random.Random(20261018))
    valores = set()
    for _ in range(1000):
        entradas = primeiro.gerar(indice)
        assert entradas == segundo.gerar(indice)
        preparadas = _derivar_campos_calculaveis(entradas, -500)
        valor, _ = ti.calcular_e_classificar("frangos", indice, preparadas)
        valores.add(valor)
    assert len(valores) > 20  # não resolveu falhas tornando o simulador constante


@pytest.mark.parametrize("indice", ["ITU", "ITUV", "IGNU"])
@pytest.mark.parametrize("semente", [0, 1, 42, 20261018])
def test_jitter_e_resfriamento_preservam_o_contrato_final(indice, semente):
    zona = {"id": 1, "especie": "frangos", "indice": indice}
    simulador = SimuladorModbusZonas(
        lambda _: zona,
        lambda _: True,
        rng_por_zona=lambda zona_id: random.Random(semente + zona_id),
    )
    campos = ti.CAMPOS_POR_INDICE[indice]
    for _ in range(500):
        entradas = {
            campo: simulador.ler_valor({"zona_id": 1, "campo_medido": campo}) for campo in campos
        }
        preparadas = _derivar_campos_calculaveis(entradas, 0)
        valor, status = ti.calcular_e_classificar("frangos", indice, preparadas)
        simulador.registrar_calculo(1, "frangos", indice, preparadas, valor, status)


def test_fluxo_aleatorio_de_uma_zona_nao_muda_a_semente_da_outra():
    zonas = {i: {"id": i, "especie": "frangos", "indice": "ITU"} for i in (1, 2)}

    def criar():
        return SimuladorModbusZonas(
            zonas.get,
            lambda _: False,
            ttl_cache_segundos=0,
            rng_por_zona=lambda zona_id: random.Random(zona_id),
        )

    primeiro, segundo = criar(), criar()
    sensor_a = {"zona_id": 1, "campo_medido": "tbs"}
    sensor_b = {"zona_id": 2, "campo_medido": "tbs"}
    for _ in range(50):
        primeiro.ler_valor(sensor_a)
    assert [primeiro.ler_valor(sensor_b) for _ in range(20)] == [
        segundo.ler_valor(sensor_b) for _ in range(20)
    ]


def test_resfriamento_e_gradual_sem_alterar_formulas():
    entradas = {"tbs": 36.0, "tbu": 32.0}
    valor, status = ti.calcular_e_classificar("frangos", "ITU", entradas)
    estado = EstadoSensor(entradas, valor, status)
    novo = EstrategiaResfriamento().aplicar("frangos", "ITU", estado)
    assert novo.valor < estado.valor
    assert novo.entradas["tbs"] < entradas["tbs"]
    assert novo.entradas["tbu"] < entradas["tbu"]
