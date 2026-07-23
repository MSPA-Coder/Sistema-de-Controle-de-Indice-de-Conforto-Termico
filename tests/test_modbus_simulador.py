# -*- coding: utf-8 -*-
"""
test_modbus_simulador.py
==========================
Testa SimuladorModbusZonas: leituras simuladas plausiveis (com media
significativa entre sensores por causa do jitter), escrita/teste de
conexao sempre "bem-sucedidos", e reaproveitamento do resfriamento
gradual de SensorSimuladoService.
"""

import unittest
from unittest.mock import patch

from app import thermal_indices as ti
from app.modbus_simulador import SimuladorModbusZonas


class TestSimuladorModbusZonas(unittest.TestCase):
    def setUp(self):
        self.zona = {
            "id": 1,
            "nome": "Zona Teste",
            "especie": "frangos",
            "indice": "ITU",
            "ativa": True,
        }
        self.resfriamento_ativo = False
        self.simulador = SimuladorModbusZonas(
            obter_zona=lambda zona_id: self.zona if zona_id == self.zona["id"] else None,
            obter_resfriamento_ativo=lambda zona_id: self.resfriamento_ativo,
        )

    def _sensor(self, campo, zona_id=1):
        return {"tipo": "sensor", "nome": "Sensor " + campo, "campo_medido": campo, "zona_id": zona_id}

    def test_leitura_fica_dentro_da_faixa_plausivel_do_campo(self):
        equipamento = self._sensor("tbs")
        valor = self.simulador.ler_valor(equipamento)
        self.assertIsNotNone(valor)
        minimo, maximo = ti.RANGE_VALIDACAO["tbs"]
        # folga pequena por causa do jitter proposital (+-0.4)
        self.assertGreaterEqual(valor, minimo - 1)
        self.assertLessEqual(valor, maximo + 1)

    def test_velocidade_simulada_nunca_fica_negativa_com_jitter(self):
        self.zona = {
            "id": 1,
            "nome": "Zona Teste",
            "especie": "frangos",
            "indice": "ITUV",
            "ativa": True,
        }
        minimo, maximo = ti.RANGE_VALIDACAO["v"]

        valores = [self.simulador.ler_valor(self._sensor("v")) for _ in range(200)]

        self.assertTrue(all(minimo <= valor <= maximo for valor in valores))

    def test_dois_sensores_do_mesmo_campo_tem_jitter_mas_ficam_proximos(self):
        valores = [self.simulador.ler_valor(self._sensor("tbs")) for _ in range(10)]
        # todos vieram do mesmo "valor verdadeiro" em cache (mesma zona,
        # chamadas dentro da janela de cache) +- jitter de ate 0.4
        self.assertLessEqual(max(valores) - min(valores), 1.0)

    def test_zona_inexistente_devolve_none(self):
        equipamento = self._sensor("tbs", zona_id=999)
        self.assertIsNone(self.simulador.ler_valor(equipamento))

    def test_equipamento_sem_campo_medido_devolve_none(self):
        equipamento = {"tipo": "sensor", "nome": "x", "campo_medido": None, "zona_id": 1}
        self.assertIsNone(self.simulador.ler_valor(equipamento))

    def test_escrever_valor_sempre_sucede(self):
        equipamento = {"tipo": "ventilador", "nome": "VENT-1"}
        self.assertTrue(self.simulador.escrever_valor(equipamento, True))
        self.assertTrue(self.simulador.escrever_valor(equipamento, False))

    def test_testar_conexao_sempre_sucede(self):
        equipamento = {"tipo": "sensor", "nome": "x"}
        self.assertTrue(self.simulador.testar_conexao(equipamento))

    def test_resfriamento_ativo_reduz_temperaturas_da_proxima_leitura(self):
        self.simulador.registrar_calculo(
            1, "frangos", "ITU", {"tbs": 30.0, "tbu": 22.0}, 75.0, "Alerta"
        )
        self.resfriamento_ativo = True

        with patch("app.modbus_simulador.random.uniform", return_value=0):
            tbs = self.simulador.ler_valor(self._sensor("tbs"))
            tbu = self.simulador.ler_valor(self._sensor("tbu"))

        self.assertEqual(28.5, tbs)
        self.assertEqual(20.9, tbu)

    def test_indices_diferentes_geram_campos_diferentes(self):
        zona_ignu = {"id": 2, "nome": "Zona IGNU", "especie": "suinos", "indice": "IGNU", "ativa": True}
        simulador = SimuladorModbusZonas(
            obter_zona=lambda zid: zona_ignu if zid == 2 else None,
            obter_resfriamento_ativo=lambda zid: False,
        )
        valor_tgn = simulador.ler_valor(
            {"tipo": "sensor", "nome": "TGN", "campo_medido": "tgn", "zona_id": 2}
        )
        self.assertIsNotNone(valor_tgn)


if __name__ == "__main__":
    unittest.main()
