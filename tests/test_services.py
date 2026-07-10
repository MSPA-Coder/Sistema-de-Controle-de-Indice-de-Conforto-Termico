# -*- coding: utf-8 -*-

import unittest

from conforto_termico import thermal_indices as ti
from conforto_termico.models import Resfriamento
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

    def test_conforto_ainda_aplica_resfriamento_enquanto_equipamento_ativo(self):
        estrategia = EstrategiaResfriamento()
        estado = EstadoSensor(
            entradas={"tbs": 25.0, "tbu": 20.0},
            valor=73.0,
            status="Conforto",
        )

        novo_estado = estrategia.aplicar("frangos", "ITU", estado)

        self.assertEqual(23.8, novo_estado.entradas["tbs"])
        self.assertEqual(19.0, novo_estado.entradas["tbu"])
        self.assertEqual("Conforto", novo_estado.status)


class TestResfriamento(unittest.TestCase):
    def test_aumenta_intensidade_imediatamente(self):
        resfriamento = Resfriamento()

        resfriamento.registrar_leitura("Alerta")
        self.assertEqual(ti.intensidade_do_status("Alerta"), resfriamento.estado()["intensidade"])

        resfriamento.registrar_leitura("Emergencia")
        self.assertEqual(ti.intensidade_do_status("Emergencia"), resfriamento.estado()["intensidade"])

    def test_reduz_intensidade_apos_tres_leituras_consecutivas(self):
        resfriamento = Resfriamento()
        resfriamento.registrar_leitura("Emergencia")

        resfriamento.registrar_leitura("Perigo")
        self.assertEqual(ti.intensidade_do_status("Emergencia"), resfriamento.estado()["intensidade"])
        self.assertEqual(ti.intensidade_do_status("Perigo"), resfriamento.estado()["intensidade_reducao_pendente"])
        self.assertEqual(1, resfriamento.estado()["leituras_reducao_consecutivas"])

        resfriamento.registrar_leitura("Perigo")
        self.assertEqual(ti.intensidade_do_status("Emergencia"), resfriamento.estado()["intensidade"])
        self.assertEqual(2, resfriamento.estado()["leituras_reducao_consecutivas"])

        resfriamento.registrar_leitura("Perigo")
        self.assertEqual(ti.intensidade_do_status("Perigo"), resfriamento.estado()["intensidade"])
        self.assertEqual(0, resfriamento.estado()["leituras_reducao_consecutivas"])

    def test_mudanca_para_estado_mais_baixo_conta_para_proximo_degrau(self):
        resfriamento = Resfriamento()
        resfriamento.registrar_leitura("Emergencia")
        resfriamento.registrar_leitura("Perigo")

        resfriamento.registrar_leitura("Alerta")
        self.assertEqual(ti.intensidade_do_status("Emergencia"), resfriamento.estado()["intensidade"])
        self.assertEqual(ti.intensidade_do_status("Perigo"), resfriamento.estado()["intensidade_reducao_pendente"])
        self.assertEqual(2, resfriamento.estado()["leituras_reducao_consecutivas"])

    def test_reducao_nao_pula_degraus_mesmo_com_conforto(self):
        resfriamento = Resfriamento()
        resfriamento.registrar_leitura("Emergencia")

        for _ in range(3):
            resfriamento.registrar_leitura("Conforto")

        self.assertTrue(resfriamento.estado()["ativo"])
        self.assertEqual(ti.intensidade_do_status("Perigo"), resfriamento.estado()["intensidade"])

        for _ in range(3):
            resfriamento.registrar_leitura("Conforto")

        self.assertTrue(resfriamento.estado()["ativo"])
        self.assertEqual(ti.intensidade_do_status("Alerta"), resfriamento.estado()["intensidade"])

        for _ in range(3):
            resfriamento.registrar_leitura("Conforto")

        self.assertFalse(resfriamento.estado()["ativo"])

    def test_desliga_apos_tres_leituras_em_conforto(self):
        resfriamento = Resfriamento()
        resfriamento.registrar_leitura("Alerta")

        resfriamento.registrar_leitura("Conforto")
        self.assertTrue(resfriamento.estado()["ativo"])
        self.assertEqual(1, resfriamento.estado()["leituras_conforto_consecutivas"])

        resfriamento.registrar_leitura("Conforto")
        self.assertTrue(resfriamento.estado()["ativo"])
        self.assertEqual(2, resfriamento.estado()["leituras_conforto_consecutivas"])

        resfriamento.registrar_leitura("Conforto")
        self.assertFalse(resfriamento.estado()["ativo"])

    def test_nebulizador_respeita_limite_de_umidade(self):
        resfriamento = Resfriamento()
        resfriamento.registrar_leitura("Emergencia")

        resfriamento.aplicar_limite_umidade_nebulizador(80.0, 70.0)
        self.assertTrue(resfriamento.estado()["ventilador"])
        self.assertFalse(resfriamento.estado()["nebulizador"])
        self.assertEqual(1, resfriamento.tipo_de_resfriador)

        resfriamento.aplicar_limite_umidade_nebulizador(70.0, 70.0)
        self.assertTrue(resfriamento.estado()["ventilador"])
        self.assertTrue(resfriamento.estado()["nebulizador"])
        self.assertEqual(3, resfriamento.tipo_de_resfriador)


if __name__ == "__main__":
    unittest.main()
