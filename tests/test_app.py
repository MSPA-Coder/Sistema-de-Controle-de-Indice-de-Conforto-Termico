# -*- coding: utf-8 -*-

import os
import tempfile
import unittest
from unittest.mock import patch

from conforto_termico import database as db
from conforto_termico import web as flask_app


class TestHistoricoGraficoApi(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path_original = db.DB_PATH
        db.DB_PATH = os.path.join(self.tempdir.name, "historico.db")
        db.iniciar_banco()
        flask_app.historico_grafico_service.limpar()
        flask_app.sensor_simulado_service.limpar()
        flask_app._resfriador.desativar()
        self.client = flask_app.app.test_client()

    def tearDown(self):
        flask_app.historico_grafico_service.limpar()
        flask_app.sensor_simulado_service.limpar()
        flask_app._resfriador.desativar()
        db.DB_PATH = self.db_path_original
        self.tempdir.cleanup()

    def test_grafico_atualiza_toda_leitura_e_banco_respeita_um_minuto(self):
        payload = {
            "especie": "frangos",
            "indice": "ITU",
            "entradas": {"tbs": 25, "tbu": 20, "v": 1, "tgn": 25, "tpo": 12},
            "config": {},
        }

        primeira = self.client.post("/api/calcular", json=payload)
        segunda = self.client.post("/api/calcular", json=payload)

        self.assertEqual(200, primeira.status_code)
        self.assertEqual(200, segunda.status_code)
        self.assertTrue(primeira.json["leitura_gravada"])
        self.assertFalse(segunda.json["leitura_gravada"])
        self.assertEqual(1, len(segunda.json["historico"]))
        self.assertEqual(2, len(segunda.json["historico_grafico"]))
        self.assertEqual({"ITU", "ITUV", "IGNU"}, set(segunda.json["indices"]))
        self.assertFalse(segunda.json["indices"]["ITUV"]["leitura_gravada"])
        self.assertFalse(segunda.json["indices"]["IGNU"]["leitura_gravada"])

        resposta_grafico = self.client.get("/api/historico-grafico?especie=frangos&indice=ITU")
        resposta_banco = self.client.get("/api/historico?especie=frangos&indice=ITU")
        resposta_grafico_todos = self.client.get("/api/historico-grafico-todos?especie=frangos")
        resposta_banco_todos = self.client.get("/api/historico-todos?especie=frangos")

        self.assertEqual(2, len(resposta_grafico.json))
        self.assertEqual(1, len(resposta_banco.json))
        self.assertEqual(2, len(resposta_grafico_todos.json["ITU"]))
        self.assertEqual(2, len(resposta_grafico_todos.json["ITUV"]))
        self.assertEqual(2, len(resposta_grafico_todos.json["IGNU"]))
        self.assertEqual(1, len(resposta_banco_todos.json["ITU"]))
        self.assertEqual(1, len(resposta_banco_todos.json["ITUV"]))
        self.assertEqual(1, len(resposta_banco_todos.json["IGNU"]))

    def test_api_respeita_intervalo_de_gravacao_configurado(self):
        payload = {
            "especie": "frangos",
            "indice": "ITU",
            "entradas": {"tbs": 25, "tbu": 20, "v": 1, "tgn": 25, "tpo": 12},
            "config": {"intervaloGravacaoMinutos": 0},
        }

        primeira = self.client.post("/api/calcular", json=payload)
        segunda = self.client.post("/api/calcular", json=payload)

        self.assertEqual(200, primeira.status_code)
        self.assertEqual(200, segunda.status_code)
        self.assertTrue(primeira.json["leitura_gravada"])
        self.assertTrue(segunda.json["leitura_gravada"])
        self.assertEqual(2, len(segunda.json["historico"]))
        self.assertEqual(2, len(segunda.json["indices"]["ITUV"]["historico"]))
        self.assertEqual(2, len(segunda.json["indices"]["IGNU"]["historico"]))

    def test_nao_toca_som_quando_indice_selecionado_esta_em_conforto(self):
        resposta = self.client.post(
            "/api/calcular",
            json={
                "especie": "frangos",
                "indice": "ITU",
                "entradas": {"tbs": 25, "tbu": 20, "v": 1, "tgn": 25, "tpo": 12},
                "config": {"habilitarSons": True},
            },
        )

        self.assertEqual(200, resposta.status_code)
        self.assertEqual("Conforto", resposta.json["status"])
        self.assertFalse(resposta.json["tocarSom"])

    def test_sensor_resfria_leituras_ate_voltar_ao_conforto(self):
        payload = {
            "especie": "frangos",
            "indice": "ITU",
            "entradas": {"tbs": 40, "tbu": 30, "v": 1, "tgn": 25, "tpo": 12},
            "config": {"habilitarEquipamentos": True},
        }

        primeira = self.client.post("/api/calcular", json=payload)
        self.assertEqual("Emergência", primeira.json["status"])
        self.assertTrue(primeira.json["equipamento"]["ativo"])

        base_entradas = {"v": 1, "tgn": 25, "tpo": 12}
        leitura = self.client.get("/api/sensor?especie=frangos&indice=ITU").json
        self.assertAlmostEqual(38.0, leitura["tbs"])
        self.assertAlmostEqual(28.5, leitura["tbu"])

        status = None
        for _ in range(20):
            resposta = self.client.post(
                "/api/calcular",
                json={
                    "especie": "frangos",
                    "indice": "ITU",
                    "entradas": {**base_entradas, **leitura},
                    "config": {"habilitarEquipamentos": True},
                },
            )
            status = resposta.json["status"]
            if status == "Conforto":
                break
            leitura = self.client.get("/api/sensor?especie=frangos&indice=ITU").json

        self.assertEqual("Conforto", status)
        self.assertFalse(resposta.json["equipamento"]["ativo"])

        with patch("conforto_termico.services.random.uniform", side_effect=[22.0, 18.0]):
            leitura_aleatoria = self.client.get("/api/sensor?especie=frangos&indice=ITU").json
        self.assertEqual({"tbs": 22.0, "tbu": 18.0}, leitura_aleatoria)

    def test_sensor_aumenta_velocidade_do_ar_no_ituv(self):
        payload = {
            "especie": "frangos",
            "indice": "ITUV",
            "entradas": {"tbs": 35, "tbu": 30, "v": 1, "tgn": 25, "tpo": 12},
            "config": {"habilitarEquipamentos": True},
        }

        resposta = self.client.post("/api/calcular", json=payload)
        self.assertNotEqual("Conforto", resposta.json["status"])
        self.assertTrue(resposta.json["equipamento"]["ativo"])

        leitura = self.client.get("/api/sensor?especie=frangos&indice=ITUV").json
        self.assertLess(leitura["tbs"], 35)
        self.assertLess(leitura["tbu"], 30)
        self.assertGreater(leitura["v"], 1)


if __name__ == "__main__":
    unittest.main()
