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

    def test_especie_desconhecida_cai_para_padrao(self):
        salvas = db.salvar_configuracoes({"especie": "marciano"})
        self.assertEqual(db.CONFIGURACOES_PADRAO["especie"], salvas["especie"])

    def test_indice_incompativel_com_especie_cai_para_indice_valido(self):
        # ITUV so existe para frangos; ao salvar bovinos+ITUV, o indice deve
        # ser corrigido para um indice que bovinos realmente tem.
        salvas = db.salvar_configuracoes({"especie": "bovinos", "indice": "ITUV"})
        self.assertEqual("bovinos", salvas["especie"])
        self.assertIn(salvas["indice"], ("ITU", "IGNU"))

    def test_indice_compativel_e_preservado(self):
        salvas = db.salvar_configuracoes({"especie": "suinos", "indice": "IGNU"})
        self.assertEqual("suinos", salvas["especie"])
        self.assertEqual("IGNU", salvas["indice"])

    def test_smtp_porta_fora_da_faixa_e_limitada(self):
        salvas = db.salvar_configuracoes({"smtpPorta": 999999})
        self.assertEqual(65535, salvas["smtpPorta"])

    def test_smtp_host_com_quebra_de_linha_e_sanitizado(self):
        salvas = db.salvar_configuracoes({"smtpHost": "smtp.fazenda.com.br\r\nX-Injetado: 1"})
        self.assertNotIn("\r", salvas["smtpHost"])
        self.assertNotIn("\n", salvas["smtpHost"])

    def test_smtp_senha_em_branco_preserva_senha_ja_salva(self):
        db.salvar_configuracoes({"smtpSenha": "senha-original"})
        salvas = db.salvar_configuracoes({"smtpSenha": "", "habilitarSons": True})
        self.assertEqual("senha-original", salvas["smtpSenha"])

    def test_smtp_senha_nao_vazia_substitui_a_anterior(self):
        db.salvar_configuracoes({"smtpSenha": "senha-antiga"})
        salvas = db.salvar_configuracoes({"smtpSenha": "senha-nova"})
        self.assertEqual("senha-nova", salvas["smtpSenha"])


class TestZonasCRUD(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path_original = db.DB_PATH
        db.DB_PATH = os.path.join(self.tempdir.name, "historico.db")
        db.iniciar_banco()

    def tearDown(self):
        db.DB_PATH = self.db_path_original
        self.tempdir.cleanup()

    def test_cria_e_busca_zona(self):
        zona = db.criar_zona({"nome": "Aviário 1", "especie": "frangos", "indice": "ITU"})
        self.assertEqual("Aviário 1", zona["nome"])
        self.assertTrue(zona["ativa"])
        self.assertEqual([], zona["equipamentos"])

        buscada = db.obter_zona(zona["id"])
        self.assertEqual(zona, buscada)

    def test_nome_vazio_e_rejeitado(self):
        with self.assertRaises(db.ZonaInvalidaError):
            db.criar_zona({"nome": "  ", "especie": "frangos", "indice": "ITU"})

    def test_especie_invalida_e_rejeitada(self):
        with self.assertRaises(db.ZonaInvalidaError):
            db.criar_zona({"nome": "Zona X", "especie": "marciano", "indice": "ITU"})

    def test_indice_incompativel_com_especie_e_rejeitado(self):
        # ITUV so existe para frangos.
        with self.assertRaises(db.ZonaInvalidaError):
            db.criar_zona({"nome": "Zona X", "especie": "bovinos", "indice": "ITUV"})

    def test_atualizar_zona_inexistente_devolve_none(self):
        resultado = db.atualizar_zona(9999, {"nome": "x", "especie": "frangos", "indice": "ITU"})
        self.assertIsNone(resultado)

    def test_atualizar_zona_existente(self):
        zona = db.criar_zona({"nome": "Original", "especie": "frangos", "indice": "ITU"})
        atualizada = db.atualizar_zona(
            zona["id"], {"nome": "Renomeada", "especie": "suinos", "indice": "IGNU", "ativa": False}
        )
        self.assertEqual("Renomeada", atualizada["nome"])
        self.assertEqual("suinos", atualizada["especie"])
        self.assertFalse(atualizada["ativa"])

    def test_listar_zonas_inclui_equipamentos(self):
        zona = db.criar_zona({"nome": "Zona 1", "especie": "frangos", "indice": "ITU"})
        db.criar_equipamento(
            zona["id"],
            {
                "tipo": "sensor",
                "nome": "Sensor 1",
                "modo_conexao": "tcp",
                "host": "10.0.0.5",
                "tipo_registrador": "input",
                "endereco_registrador": 1,
                "campo_medido": "tbs",
            },
        )
        zonas = db.listar_zonas()
        self.assertEqual(1, len(zonas[0]["equipamentos"]))

    def test_excluir_zona_remove_equipamentos_em_cascata(self):
        zona = db.criar_zona({"nome": "Zona 1", "especie": "frangos", "indice": "ITU"})
        equipamento = db.criar_equipamento(
            zona["id"],
            {
                "tipo": "sensor",
                "nome": "Sensor 1",
                "modo_conexao": "tcp",
                "host": "10.0.0.5",
                "tipo_registrador": "input",
                "endereco_registrador": 1,
                "campo_medido": "tbs",
            },
        )
        self.assertTrue(db.excluir_zona(zona["id"]))
        self.assertIsNone(db.obter_equipamento(equipamento["id"]))

    def test_excluir_zona_preserva_historico_ja_gravado(self):
        zona = db.criar_zona({"nome": "Zona 1", "especie": "frangos", "indice": "ITU"})
        db.salvar_leitura("frangos", "ITU", 75.0, "Conforto", {"tbs": 25, "tbu": 20}, zona_id=zona["id"])
        total_antes = db.contar_leituras()
        db.excluir_zona(zona["id"])
        # A linha em si nao e apagada (ON DELETE SET NULL, nao CASCADE) --
        # so deixa de referenciar uma zona que nao existe mais, entao uma
        # busca pelo zona_id antigo naturalmente nao encontra mais nada.
        self.assertEqual(total_antes, db.contar_leituras())
        self.assertEqual([], db.obter_historico_por_zona(zona["id"]))

    def test_excluir_zona_inexistente_devolve_false(self):
        self.assertFalse(db.excluir_zona(9999))


class TestEquipamentosCRUD(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path_original = db.DB_PATH
        db.DB_PATH = os.path.join(self.tempdir.name, "historico.db")
        db.iniciar_banco()
        self.zona = db.criar_zona({"nome": "Zona teste", "especie": "frangos", "indice": "ITU"})

    def tearDown(self):
        db.DB_PATH = self.db_path_original
        self.tempdir.cleanup()

    def _equipamento_base(self, **sobrescritas):
        base = {
            "tipo": "sensor",
            "nome": "Sensor TBS",
            "modo_conexao": "tcp",
            "host": "192.168.0.10",
            "porta": 502,
            "unidade_id": 1,
            "tipo_registrador": "input",
            "endereco_registrador": 100,
            "tipo_dado": "int16",
            "fator_escala": 0.1,
            "campo_medido": "tbs",
        }
        base.update(sobrescritas)
        return base

    def test_cria_equipamento_tcp(self):
        equipamento = db.criar_equipamento(self.zona["id"], self._equipamento_base())
        self.assertEqual("192.168.0.10", equipamento["host"])
        self.assertEqual(502, equipamento["porta"])
        self.assertIsNone(equipamento["porta_serial"])

    def test_cria_equipamento_rtu(self):
        equipamento = db.criar_equipamento(
            self.zona["id"],
            self._equipamento_base(
                modo_conexao="rtu", host=None, porta_serial="/dev/ttyUSB0", baud_rate=9600
            ),
        )
        self.assertEqual("/dev/ttyUSB0", equipamento["porta_serial"])
        self.assertEqual(9600, equipamento["baud_rate"])
        self.assertIsNone(equipamento["host"])

    def test_tcp_sem_host_e_rejeitado(self):
        with self.assertRaises(db.ZonaInvalidaError):
            db.criar_equipamento(self.zona["id"], self._equipamento_base(host=""))

    def test_rtu_sem_porta_serial_e_rejeitado(self):
        with self.assertRaises(db.ZonaInvalidaError):
            db.criar_equipamento(
                self.zona["id"], self._equipamento_base(modo_conexao="rtu", host=None)
            )

    def test_tipo_invalido_e_rejeitado(self):
        with self.assertRaises(db.ZonaInvalidaError):
            db.criar_equipamento(self.zona["id"], self._equipamento_base(tipo="aspirador"))

    def test_sensor_sem_campo_medido_e_rejeitado(self):
        with self.assertRaises(db.ZonaInvalidaError):
            db.criar_equipamento(self.zona["id"], self._equipamento_base(campo_medido=None))

    def test_sensor_com_campo_medido_invalido_e_rejeitado(self):
        with self.assertRaises(db.ZonaInvalidaError):
            db.criar_equipamento(self.zona["id"], self._equipamento_base(campo_medido="pressao"))

    def test_ventilador_nao_exige_campo_medido(self):
        equipamento = db.criar_equipamento(
            self.zona["id"],
            self._equipamento_base(
                tipo="ventilador", nome="Ventilador 1", tipo_registrador="coil",
                endereco_registrador=1, campo_medido=None,
            ),
        )
        self.assertIsNone(equipamento["campo_medido"])

    def test_endereco_registrador_fora_da_faixa_e_rejeitado(self):
        with self.assertRaises(db.ZonaInvalidaError):
            db.criar_equipamento(self.zona["id"], self._equipamento_base(endereco_registrador=999999))

    def test_unidade_id_fora_da_faixa_e_rejeitada(self):
        with self.assertRaises(db.ZonaInvalidaError):
            db.criar_equipamento(self.zona["id"], self._equipamento_base(unidade_id=999))

    def test_fator_escala_zero_e_rejeitado(self):
        with self.assertRaises(db.ZonaInvalidaError):
            db.criar_equipamento(self.zona["id"], self._equipamento_base(fator_escala=0))

    def test_registrador_invalido_para_sensor(self):
        # 'coil' nao e valido para sensor (so holding/input)
        with self.assertRaises(db.ZonaInvalidaError):
            db.criar_equipamento(self.zona["id"], self._equipamento_base(tipo_registrador="coil"))

    def test_criar_equipamento_em_zona_inexistente(self):
        with self.assertRaises(db.ZonaInvalidaError):
            db.criar_equipamento(9999, self._equipamento_base())

    def test_atualizar_equipamento(self):
        equipamento = db.criar_equipamento(self.zona["id"], self._equipamento_base())
        atualizado = db.atualizar_equipamento(
            equipamento["id"], self._equipamento_base(nome="Sensor Renomeado", fator_escala=1.0)
        )
        self.assertEqual("Sensor Renomeado", atualizado["nome"])
        self.assertEqual(1.0, atualizado["fator_escala"])

    def test_atualizar_equipamento_inexistente_devolve_none(self):
        resultado = db.atualizar_equipamento(9999, self._equipamento_base())
        self.assertIsNone(resultado)

    def test_excluir_equipamento(self):
        equipamento = db.criar_equipamento(self.zona["id"], self._equipamento_base())
        self.assertTrue(db.excluir_equipamento(equipamento["id"]))
        self.assertIsNone(db.obter_equipamento(equipamento["id"]))

    def test_listar_equipamentos_da_zona(self):
        db.criar_equipamento(self.zona["id"], self._equipamento_base(nome="S1"))
        db.criar_equipamento(self.zona["id"], self._equipamento_base(nome="S2"))
        equipamentos = db.listar_equipamentos_da_zona(self.zona["id"])
        self.assertEqual(2, len(equipamentos))


if __name__ == "__main__":
    unittest.main()
