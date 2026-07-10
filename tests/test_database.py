# -*- coding: utf-8 -*-

import datetime
import os
import tempfile
import unittest

from conforto_termico import database as db


class TestIntervaloMinimoLeituras(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path_original = db.DB_PATH
        db.DB_PATH = os.path.join(self.tempdir.name, "historico.db")
        db.iniciar_banco()

    def tearDown(self):
        db.DB_PATH = self.db_path_original
        self.tempdir.cleanup()

    def test_nao_salva_mesmo_indice_antes_de_um_minuto(self):
        entradas = {"tbs": 25, "tbu": 20}

        self.assertTrue(db.salvar_leitura("frangos", "ITU", 70.0, "Conforto", entradas))
        self.assertFalse(db.salvar_leitura("frangos", "ITU", 71.0, "Conforto", entradas))

        historico = db.obter_historico("frangos", "ITU")
        self.assertEqual(1, len(historico))
        self.assertEqual(70.0, historico[0]["valor"])

    def test_salva_mesmo_indice_depois_de_um_minuto(self):
        entradas = {"tbs": 25, "tbu": 20}

        self.assertTrue(db.salvar_leitura("frangos", "ITU", 70.0, "Conforto", entradas))
        criado_em_antigo = (
            datetime.datetime.now() - datetime.timedelta(seconds=61)
        ).isoformat(timespec="seconds")

        with db._conexao() as conn:
            conn.execute(
                "UPDATE leituras SET criado_em = ? WHERE especie = ? AND indice = ?",
                (criado_em_antigo, "frangos", "ITU"),
            )

        self.assertTrue(db.salvar_leitura("frangos", "ITU", 71.0, "Conforto", entradas))
        self.assertEqual(2, len(db.obter_historico("frangos", "ITU")))

    def test_intervalo_e_independente_por_especie_e_indice(self):
        entradas = {"tbs": 25, "tbu": 20}

        self.assertTrue(db.salvar_leitura("frangos", "ITU", 70.0, "Conforto", entradas))
        self.assertTrue(db.salvar_leitura("bovinos", "ITU", 70.0, "Conforto", entradas))
        self.assertTrue(db.salvar_leitura("frangos", "IGNU", 70.0, "Conforto", entradas))

    def test_intervalo_zero_salva_todas_as_leituras(self):
        entradas = {"tbs": 25, "tbu": 20}

        self.assertTrue(
            db.salvar_leitura(
                "frangos", "ITU", 70.0, "Conforto", entradas, intervalo_minutos=0
            )
        )
        self.assertTrue(
            db.salvar_leitura(
                "frangos", "ITU", 71.0, "Conforto", entradas, intervalo_minutos=0
            )
        )

        self.assertEqual(2, len(db.obter_historico("frangos", "ITU")))

    def test_limpa_historico_por_especie(self):
        entradas = {"tbs": 25, "tbu": 20}

        db.salvar_leitura("frangos", "ITU", 70.0, "Conforto", entradas)
        db.salvar_leitura("frangos", "IGNU", 70.0, "Conforto", entradas)
        db.salvar_leitura("bovinos", "ITU", 70.0, "Conforto", entradas)

        db.limpar_historico("frangos")

        self.assertEqual([], db.obter_historico("frangos", "ITU"))
        self.assertEqual([], db.obter_historico("frangos", "IGNU"))
        self.assertEqual(1, len(db.obter_historico("bovinos", "ITU")))

    def test_configuracoes_retornam_padroes(self):
        configuracoes = db.obter_configuracoes()

        self.assertFalse(configuracoes["coletarDados"])
        self.assertEqual(1, configuracoes["intervaloLeituraSegundos"])
        self.assertEqual("medido", configuracoes["modoPontoOrvalho"])
        self.assertEqual("calculado", configuracoes["modoUmidadeRelativa"])
        self.assertEqual(70, configuracoes["limiteUmidadeNebulizador"])

    def test_salva_e_recupera_configuracoes(self):
        db.salvar_configuracoes(
            {
                "coletarDados": True,
                "habilitarSons": True,
                "intervaloLeituraSegundos": 5,
                "modoPontoOrvalho": "calculado",
                "modoUmidadeRelativa": "medido",
                "altitudeMetros": 760,
                "limiteUmidadeNebulizador": 65,
                "campoIgnorado": "nao deve persistir",
            }
        )

        configuracoes = db.obter_configuracoes()
        self.assertTrue(configuracoes["coletarDados"])
        self.assertTrue(configuracoes["habilitarSons"])
        self.assertEqual(5, configuracoes["intervaloLeituraSegundos"])
        self.assertEqual("calculado", configuracoes["modoPontoOrvalho"])
        self.assertEqual("medido", configuracoes["modoUmidadeRelativa"])
        self.assertEqual(760, configuracoes["altitudeMetros"])
        self.assertEqual(65, configuracoes["limiteUmidadeNebulizador"])
        self.assertNotIn("campoIgnorado", configuracoes)


if __name__ == "__main__":
    unittest.main()
