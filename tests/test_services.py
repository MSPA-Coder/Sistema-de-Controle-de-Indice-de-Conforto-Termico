# -*- coding: utf-8 -*-

import unittest

from conforto_termico.services import EstadoSensor, EstrategiaResfriamento, HistoricoGraficoService


class TestHistoricoGraficoService(unittest.TestCase):
    def test_registra_e_limita_historico_visual(self):
        service = HistoricoGraficoService(lambda especie, indice, limite: [], limite=2)

        service.registrar("frangos", "ITU", 70.0, "Conforto", {"tbs": 25, "tbu": 20})
        service.registrar("frangos", "ITU", 71.0, "Conforto", {"tbs": 26, "tbu": 21})
        historico = service.registrar("frangos", "ITU", 72.0, "Conforto", {"tbs": 27, "tbu": 22})

        self.assertEqual([71.0, 72.0], [item["valor"] for item in historico])

    def test_retorna_copia_defensiva(self):
        service = HistoricoGraficoService(lambda especie, indice, limite: [], limite=20)
        service.registrar("frangos", "ITU", 70.0, "Conforto", {"tbs": 25, "tbu": 20})

        historico = service.obter("frangos", "ITU")
        historico[0]["entradas"]["tbs"] = 99

        self.assertEqual(25, service.obter("frangos", "ITU")[0]["entradas"]["tbs"])


class TestEstrategiaResfriamento(unittest.TestCase):
    def test_reduz_temperaturas_e_aumenta_ventilacao_no_ituv(self):
        estrategia = EstrategiaResfriamento()
        estado = EstadoSensor(
            entradas={"tbs": 35.0, "tbu": 30.0, "v": 1.0},
            valor=34.0,
            status="Alerta",
        )

        novo_estado = estrategia.aplicar("frangos", "ITUV", estado)

        self.assertEqual(33.2, novo_estado.entradas["tbs"])
        self.assertEqual(28.5, novo_estado.entradas["tbu"])
        self.assertEqual(1.05, novo_estado.entradas["v"])

    def test_conforto_nao_aplica_resfriamento(self):
        estrategia = EstrategiaResfriamento()
        estado = EstadoSensor(
            entradas={"tbs": 25.0, "tbu": 20.0},
            valor=73.0,
            status="Conforto",
        )

        self.assertIsNone(estrategia.aplicar("frangos", "ITU", estado))


if __name__ == "__main__":
    unittest.main()
