# -*- coding: utf-8 -*-

import os
import tempfile
import threading
import unittest

from conforto_termico import database as db
from conforto_termico.coletor.controle import (
    GerenciadorControleZonas,
    ZonaOcupadaError,
)


class _ZonaServiceFalso:
    def __init__(self):
        self.calculadas = []

    def calcular(self, zona_id, logger=None):
        self.calculadas.append(zona_id)
        return {
            "zona_id": zona_id,
            "zona_nome": f"Zona {zona_id}",
            "status": "Conforto",
            "valor": 70.0,
            "qualidade": "boa",
        }

    def calcular_manual(self, zona_id, entradas, logger=None):
        return self.calcular(zona_id, logger)


class TestGerenciadorControleZonas(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path_original = db.DB_PATH
        db.DB_PATH = os.path.join(self.tempdir.name, "historico.db")
        db.iniciar_banco()
        self.servico = _ZonaServiceFalso()
        self.gerenciador = GerenciadorControleZonas(self.servico)

    def tearDown(self):
        db.DB_PATH = self.db_path_original
        self.tempdir.cleanup()

    @staticmethod
    def _criar_zona(nome):
        return db.criar_zona(
            {"nome": nome, "especie": "frangos", "indice": "ITU"}
        )["id"]

    def test_ciclo_automatico_processa_somente_modo_automatico(self):
        zona_manual = self._criar_zona("Manual")
        zona_automatica = self._criar_zona("Automatica")
        db.salvar_controle_zona(zona_automatica, {"modo": "automatico"})

        resultados = self.gerenciador.executar_ciclo_automatico()

        self.assertEqual([zona_automatica], self.servico.calculadas)
        self.assertEqual([zona_automatica], [item["zona_id"] for item in resultados])
        self.assertNotIn(zona_manual, self.servico.calculadas)
        self.assertIsNotNone(db.obter_status_coletor()["ultimo_ciclo_em"])
        self.assertTrue(db.listar_eventos_operacao(zona_automatica))

    def test_lock_impede_dois_ciclos_simultaneos_na_mesma_zona(self):
        zona_id = self._criar_zona("Concorrente")
        entrou = threading.Event()
        liberar = threading.Event()

        def calculo_bloqueado(zona, entradas, logger=None):
            entrou.set()
            liberar.wait(timeout=2)
            return {
                "zona_id": zona,
                "zona_nome": "Concorrente",
                "status": "Conforto",
                "valor": 70.0,
                "qualidade": "boa",
            }

        self.servico.calcular_manual = calculo_bloqueado
        thread = threading.Thread(
            target=lambda: self.gerenciador.calcular_manual(zona_id, {"tbs": 25})
        )
        thread.start()
        self.assertTrue(entrou.wait(timeout=2))
        try:
            with self.assertRaises(ZonaOcupadaError):
                self.gerenciador.calcular_manual(zona_id, {"tbs": 25})
            with self.assertRaises(ZonaOcupadaError):
                self.gerenciador.alterar_controle(
                    zona_id, {"modo": "automatico"}
                )
            self.assertEqual("manual", db.obter_controle_zona(zona_id)["modo"])
        finally:
            liberar.set()
            thread.join(timeout=2)
        self.assertFalse(thread.is_alive())


if __name__ == "__main__":
    unittest.main()
