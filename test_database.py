# -*- coding: utf-8 -*-

import datetime
import os
import tempfile
import unittest

import database as db


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


if __name__ == "__main__":
    unittest.main()
