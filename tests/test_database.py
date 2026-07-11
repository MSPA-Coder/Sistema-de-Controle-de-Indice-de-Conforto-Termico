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


class TestSanitizacaoDeConfiguracoes(unittest.TestCase):
    """`salvar_configuracoes`/`obter_configuracoes` nunca devem persistir ou
    devolver um valor de tipo errado, fora de faixa ou (no caso do
    e-mail) potencialmente perigoso -- sempre caem de volta ao padrao
    seguro daquele campo especifico, sem lancar excecao."""

    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path_original = db.DB_PATH
        db.DB_PATH = os.path.join(self.tempdir.name, "historico.db")
        db.iniciar_banco()

    def tearDown(self):
        db.DB_PATH = self.db_path_original
        self.tempdir.cleanup()

    def test_email_com_quebra_de_linha_cai_para_padrao(self):
        # Tentativa de injecao de cabecalho SMTP (ex.: "Bcc: atacante@...")
        # via quebra de linha no valor do e-mail.
        salvas = db.salvar_configuracoes(
            {"emailDestino": "vitima@fazenda.com.br\r\nBcc: atacante@evil.com"}
        )
        self.assertEqual(db.CONFIGURACOES_PADRAO["emailDestino"], salvas["emailDestino"])

    def test_email_sem_formato_valido_cai_para_padrao(self):
        salvas = db.salvar_configuracoes({"emailDestino": "isso nao e um email"})
        self.assertEqual(db.CONFIGURACOES_PADRAO["emailDestino"], salvas["emailDestino"])

    def test_email_valido_e_preservado(self):
        salvas = db.salvar_configuracoes({"emailDestino": "produtor.silva@exemplo.com.br"})
        self.assertEqual("produtor.silva@exemplo.com.br", salvas["emailDestino"])

    def test_altitude_fora_da_faixa_e_limitada(self):
        salvas = db.salvar_configuracoes({"altitudeMetros": 999999})
        self.assertEqual(9000, salvas["altitudeMetros"])

        salvas = db.salvar_configuracoes({"altitudeMetros": -999999})
        self.assertEqual(-500, salvas["altitudeMetros"])

    def test_limite_umidade_fora_da_faixa_e_limitado(self):
        salvas = db.salvar_configuracoes({"limiteUmidadeNebulizador": 150})
        self.assertEqual(100, salvas["limiteUmidadeNebulizador"])

    def test_enum_invalido_cai_para_padrao(self):
        salvas = db.salvar_configuracoes({"modoPontoOrvalho": "chute"})
        self.assertEqual(db.CONFIGURACOES_PADRAO["modoPontoOrvalho"], salvas["modoPontoOrvalho"])

    def test_booleano_com_tipo_errado_cai_para_padrao(self):
        salvas = db.salvar_configuracoes({"coletarDados": {"nao": "e bool"}})
        self.assertEqual(db.CONFIGURACOES_PADRAO["coletarDados"], salvas["coletarDados"])

    def test_numero_nao_numerico_cai_para_padrao(self):
        salvas = db.salvar_configuracoes({"intervaloLeituraSegundos": "abc"})
        self.assertEqual(
            db.CONFIGURACOES_PADRAO["intervaloLeituraSegundos"], salvas["intervaloLeituraSegundos"]
        )


if __name__ == "__main__":
    unittest.main()
