# -*- coding: utf-8 -*-
"""
test_zona_service.py
=====================
Testa ZonaService (leitura de sensores Modbus com MEDIA quando ha mais de
um sensor por campo, calculo do indice, gravacao no historico com zona_id,
e acionamento dos atuadores) usando funcoes de leitura/escrita Modbus
falsas -- sem depender de hardware real.
"""

import os
import tempfile
import unittest

from conforto_termico import database as db
from conforto_termico.zona_service import ZonaCalculoError, ZonaService


class TestZonaService(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path_original = db.DB_PATH
        db.DB_PATH = os.path.join(self.tempdir.name, "historico.db")
        db.iniciar_banco()

        self.leituras_simuladas: dict[str, float | None] = {}
        self.escritas: list[tuple[str, bool]] = []

        def ler_mock(equipamento):
            return self.leituras_simuladas.get(equipamento["nome"])

        def escrever_mock(equipamento, ligar):
            self.escritas.append((equipamento["nome"], ligar))
            return True

        self.servico = ZonaService(
            obter_zona=db.obter_zona,
            salvar_leitura=db.salvar_leitura,
            obter_configuracoes=db.obter_configuracoes,
            ler_modbus=ler_mock,
            escrever_modbus=escrever_mock,
        )

    def tearDown(self):
        db.DB_PATH = self.db_path_original
        self.tempdir.cleanup()

    def _criar_zona_com_sensores(self, especie="frangos", indice="ITU"):
        zona = db.criar_zona({"nome": "Zona Teste", "especie": especie, "indice": indice})
        return zona

    def _equipamento_sensor(self, zona_id, nome, campo, **sobrescritas):
        base = {
            "tipo": "sensor",
            "nome": nome,
            "modo_conexao": "tcp",
            "host": "10.0.0.1",
            "tipo_registrador": "input",
            "endereco_registrador": 1,
            "campo_medido": campo,
        }
        base.update(sobrescritas)
        return db.criar_equipamento(zona_id, base)

    def test_media_de_dois_sensores_do_mesmo_campo(self):
        zona = self._criar_zona_com_sensores()
        self._equipamento_sensor(zona["id"], "TBS-A", "tbs")
        self._equipamento_sensor(zona["id"], "TBS-B", "tbs")
        self._equipamento_sensor(zona["id"], "TBU-A", "tbu")
        self.leituras_simuladas = {"TBS-A": 30.0, "TBS-B": 34.0, "TBU-A": 22.0}

        resultado = self.servico.calcular(zona["id"])

        self.assertEqual(32.0, resultado["entradas"]["tbs"])
        self.assertEqual([], resultado["sensores_com_falha"])

    def test_sensor_unico_usa_o_proprio_valor(self):
        zona = self._criar_zona_com_sensores()
        self._equipamento_sensor(zona["id"], "TBS-A", "tbs")
        self._equipamento_sensor(zona["id"], "TBU-A", "tbu")
        self.leituras_simuladas = {"TBS-A": 28.0, "TBU-A": 20.0}

        resultado = self.servico.calcular(zona["id"])
        self.assertEqual(28.0, resultado["entradas"]["tbs"])

    def test_sensor_com_falha_e_ignorado_na_media_mas_reportado(self):
        zona = self._criar_zona_com_sensores()
        self._equipamento_sensor(zona["id"], "TBS-OK", "tbs")
        self._equipamento_sensor(zona["id"], "TBS-COM-DEFEITO", "tbs")
        self._equipamento_sensor(zona["id"], "TBU-A", "tbu")
        self.leituras_simuladas = {"TBS-OK": 28.0, "TBU-A": 20.0}  # TBS-COM-DEFEITO ausente -> None

        resultado = self.servico.calcular(zona["id"])

        self.assertEqual(28.0, resultado["entradas"]["tbs"])
        self.assertIn("TBS-COM-DEFEITO", resultado["sensores_com_falha"])

    def test_nenhum_sensor_responde_leva_a_erro_claro(self):
        zona = self._criar_zona_com_sensores()
        self._equipamento_sensor(zona["id"], "TBS-A", "tbs")
        self._equipamento_sensor(zona["id"], "TBU-A", "tbu")
        self.leituras_simuladas = {}  # nada responde

        with self.assertRaises(ZonaCalculoError):
            self.servico.calcular(zona["id"])

    def test_zona_inexistente_leva_a_erro_claro(self):
        with self.assertRaises(ZonaCalculoError):
            self.servico.calcular(99999)

    def test_zona_desativada_leva_a_erro_claro(self):
        zona = self._criar_zona_com_sensores()
        db.atualizar_zona(zona["id"], {**zona, "ativa": False})
        with self.assertRaises(ZonaCalculoError):
            self.servico.calcular(zona["id"])

    def test_grava_historico_com_zona_id(self):
        zona = self._criar_zona_com_sensores()
        self._equipamento_sensor(zona["id"], "TBS-A", "tbs")
        self._equipamento_sensor(zona["id"], "TBU-A", "tbu")
        self.leituras_simuladas = {"TBS-A": 25.0, "TBU-A": 20.0}

        self.servico.calcular(zona["id"])

        historico = db.obter_historico_por_zona(zona["id"])
        self.assertEqual(1, len(historico))
        self.assertEqual(zona["id"], historico[0]["zona_id"])

    def test_duas_zonas_tem_estado_de_resfriamento_independente(self):
        zona_quente = self._criar_zona_com_sensores()
        zona_fria = self._criar_zona_com_sensores()
        self._equipamento_sensor(zona_quente["id"], "TBS-QUENTE", "tbs")
        self._equipamento_sensor(zona_quente["id"], "TBU-QUENTE", "tbu")
        self._equipamento_sensor(zona_fria["id"], "TBS-FRIA", "tbs")
        self._equipamento_sensor(zona_fria["id"], "TBU-FRIA", "tbu")

        self.leituras_simuladas = {
            "TBS-QUENTE": 38.0, "TBU-QUENTE": 30.0,  # deve dar Perigo/Emergencia
            "TBS-FRIA": 20.0, "TBU-FRIA": 18.0,  # deve dar Conforto
        }

        quente = self.servico.calcular(zona_quente["id"])
        fria = self.servico.calcular(zona_fria["id"])

        self.assertNotEqual(quente["status"], "Conforto")
        self.assertEqual("Conforto", fria["status"])
        self.assertTrue(quente["equipamento"]["ativo"])
        self.assertFalse(fria["equipamento"]["ativo"])

    def test_atuadores_sao_acionados_conforme_status(self):
        zona = self._criar_zona_com_sensores()
        self._equipamento_sensor(zona["id"], "TBS-A", "tbs")
        self._equipamento_sensor(zona["id"], "TBU-A", "tbu")
        db.criar_equipamento(zona["id"], {
            "tipo": "ventilador", "nome": "VENT-1", "modo_conexao": "tcp", "host": "10.0.0.2",
            "tipo_registrador": "coil", "endereco_registrador": 0,
        })
        db.criar_equipamento(zona["id"], {
            "tipo": "nebulizador", "nome": "NEB-1", "modo_conexao": "tcp", "host": "10.0.0.3",
            "tipo_registrador": "coil", "endereco_registrador": 0,
        })
        self.leituras_simuladas = {"TBS-A": 38.0, "TBU-A": 30.0}

        self.servico.calcular(zona["id"])

        nomes_acionados = {nome for nome, ligar in self.escritas if ligar}
        self.assertIn("VENT-1", nomes_acionados)
        self.assertIn("NEB-1", nomes_acionados)

    def test_deriva_umidade_relativa_de_tbs_tbu_para_indice_ignu(self):
        zona = self._criar_zona_com_sensores(especie="suinos", indice="IGNU")
        self._equipamento_sensor(zona["id"], "TBS-A", "tbs")
        self._equipamento_sensor(zona["id"], "TBU-A", "tbu")
        self._equipamento_sensor(zona["id"], "TGN-A", "tgn")
        self.leituras_simuladas = {"TBS-A": 28.0, "TBU-A": 22.0, "TGN-A": 30.0}

        resultado = self.servico.calcular(zona["id"])

        # tpo deve ter sido derivado (nao ha sensor de tpo cadastrado)
        self.assertIn("tpo", resultado["entradas"])
        self.assertEqual("IGNU", resultado["indice"])

    def test_falha_ao_acionar_atuador_nao_impede_o_calculo(self):
        zona = self._criar_zona_com_sensores()
        self._equipamento_sensor(zona["id"], "TBS-A", "tbs")
        self._equipamento_sensor(zona["id"], "TBU-A", "tbu")
        db.criar_equipamento(zona["id"], {
            "tipo": "ventilador", "nome": "VENT-QUEBRADO", "modo_conexao": "tcp", "host": "10.0.0.9",
            "tipo_registrador": "coil", "endereco_registrador": 0,
        })
        self.leituras_simuladas = {"TBS-A": 38.0, "TBU-A": 30.0}

        def escrever_falho(equipamento, ligar):
            return False

        self.servico._escrever_modbus = escrever_falho
        resultado = self.servico.calcular(zona["id"])

        self.assertIn("VENT-QUEBRADO", resultado["atuadores_com_falha"])
        self.assertIsNotNone(resultado["valor"])  # o calculo em si nao falhou


if __name__ == "__main__":
    unittest.main()
