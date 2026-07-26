# -*- coding: utf-8 -*-

import datetime
import os
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from app import database as db


class TestBackupPostgres(unittest.TestCase):
    @patch("app.database.os.path.getsize", return_value=1234)
    @patch("app.database.subprocess.run")
    @patch("app.database.db_backend.database_url")
    @patch("app.database.db_backend.postgres_ativo", return_value=True)
    def test_dump_inclui_banco_inteiro_sem_donos(
        self, _postgres_ativo, database_url, executar, _getsize
    ):
        database_url.return_value = (
            "postgresql+psycopg://conforto:segredo@postgres/conforto_termico"
        )
        with tempfile.TemporaryDirectory() as diretorio:
            db_path_original = db.DB_PATH
            db.DB_PATH = os.path.join(diretorio, "historico.db")
            try:
                backup = db.criar_backup_banco()
            finally:
                db.DB_PATH = db_path_original

        comando = executar.call_args.args[0]
        self.assertIn("--format=custom", comando)
        self.assertIn("--no-owner", comando)
        self.assertIn("--no-privileges", comando)
        self.assertFalse(any(item.startswith("--schema=") for item in comando))
        self.assertFalse(any("segredo" in item for item in comando))
        self.assertEqual("segredo", executar.call_args.kwargs["env"]["PGPASSWORD"])
        self.assertTrue(backup["arquivo"].endswith(".dump"))


class TestIntervaloMinimoLeituras(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path_original = db.DB_PATH
        db.DB_PATH = os.path.join(self.tempdir.name, "historico.db")
        db.iniciar_banco()
        self.zona_frangos = db.criar_zona(
            {"nome": "Aviário", "especie": "frangos", "indice": "ITU"}
        )

    def tearDown(self):
        db.DB_PATH = self.db_path_original
        self.tempdir.cleanup()

    def test_nao_salva_mesmo_indice_antes_de_um_minuto(self):
        entradas = {"tbs": 25, "tbu": 20}

        self.assertTrue(
            db.salvar_leitura(
                "frangos",
                "ITU",
                70.0,
                "Conforto",
                entradas,
                zona_id=self.zona_frangos["id"],
            )
        )
        self.assertFalse(
            db.salvar_leitura(
                "frangos",
                "ITU",
                71.0,
                "Conforto",
                entradas,
                zona_id=self.zona_frangos["id"],
            )
        )

        historico = db.obter_historico_por_zona(self.zona_frangos["id"])
        self.assertEqual(1, len(historico))
        self.assertEqual(70.0, historico[0]["valor"])

    def test_salva_mesmo_indice_depois_de_um_minuto(self):
        entradas = {"tbs": 25, "tbu": 20}

        self.assertTrue(
            db.salvar_leitura(
                "frangos",
                "ITU",
                70.0,
                "Conforto",
                entradas,
                zona_id=self.zona_frangos["id"],
            )
        )
        criado_em_antigo = (
            datetime.datetime.now() - datetime.timedelta(seconds=61)
        ).isoformat(timespec="seconds")

        with db._conexao() as conn:
            conn.execute(
                "UPDATE leituras SET criado_em = ? WHERE zona_id = ?",
                (criado_em_antigo, self.zona_frangos["id"]),
            )

        self.assertTrue(
            db.salvar_leitura(
                "frangos",
                "ITU",
                71.0,
                "Conforto",
                entradas,
                zona_id=self.zona_frangos["id"],
            )
        )
        self.assertEqual(
            2, len(db.obter_historico_por_zona(self.zona_frangos["id"]))
        )

    def test_intervalo_e_independente_por_zona(self):
        entradas = {"tbs": 25, "tbu": 20}
        outra_zona = db.criar_zona(
            {"nome": "Outro aviário", "especie": "frangos", "indice": "ITU"}
        )

        self.assertTrue(
            db.salvar_leitura(
                "frangos",
                "ITU",
                70.0,
                "Conforto",
                entradas,
                zona_id=self.zona_frangos["id"],
            )
        )
        self.assertTrue(
            db.salvar_leitura(
                "frangos",
                "ITU",
                70.0,
                "Conforto",
                entradas,
                zona_id=outra_zona["id"],
            )
        )

    def test_rejeita_leitura_incompativel_com_o_cadastro_da_zona(self):
        with self.assertRaisesRegex(db.ZonaInvalidaError, "corresponder"):
            db.salvar_leitura(
                "bovinos",
                "ITU",
                70.0,
                "Conforto",
                {"tbs": 25, "tbu": 20},
                zona_id=self.zona_frangos["id"],
            )

    def test_rejeita_leitura_para_zona_inexistente(self):
        with self.assertRaises(db.ZonaNaoEncontradaError):
            db.salvar_leitura(
                "frangos",
                "ITU",
                70.0,
                "Conforto",
                {"tbs": 25, "tbu": 20},
                zona_id=999999,
            )

    def test_intervalo_zero_salva_todas_as_leituras(self):
        entradas = {"tbs": 25, "tbu": 20}

        self.assertTrue(
            db.salvar_leitura(
                "frangos",
                "ITU",
                70.0,
                "Conforto",
                entradas,
                intervalo_minutos=0,
                zona_id=self.zona_frangos["id"],
            )
        )
        self.assertTrue(
            db.salvar_leitura(
                "frangos",
                "ITU",
                71.0,
                "Conforto",
                entradas,
                intervalo_minutos=0,
                zona_id=self.zona_frangos["id"],
            )
        )

        self.assertEqual(
            2, len(db.obter_historico_por_zona(self.zona_frangos["id"]))
        )

    def test_cria_backup_no_mesmo_diretorio_do_banco(self):
        db.salvar_leitura(
            "frangos",
            "ITU",
            70.0,
            "Conforto",
            {"tbs": 25, "tbu": 20},
            zona_id=self.zona_frangos["id"],
        )

        backup = db.criar_backup_banco()

        self.assertTrue(os.path.exists(backup["caminho"]))
        self.assertEqual(os.path.dirname(db.DB_PATH), os.path.dirname(backup["caminho"]))
        self.assertGreater(backup["tamanho_bytes"], 0)

    def test_historico_leituras_paginado_inclui_zona(self):
        zona = db.criar_zona({"nome": "Aviario 1", "especie": "frangos", "indice": "ITU"})
        db.salvar_leitura(
            "frangos",
            "ITU",
            70.0,
            "Conforto",
            {"tbs": 25, "tbu": 20},
            intervalo_minutos=0,
            zona_id=self.zona_frangos["id"],
        )
        db.salvar_leitura(
            "frangos",
            "ITU",
            71.0,
            "Alerta",
            {"tbs": 26, "tbu": 21},
            intervalo_minutos=0,
            zona_id=zona["id"],
        )

        pagina = db.obter_historico_leituras(limite=1, deslocamento=1)

        self.assertEqual(2, pagina["total"])
        self.assertEqual(1, pagina["deslocamento"])
        self.assertEqual(1, len(pagina["leituras"]))
        self.assertEqual(zona["id"], pagina["leituras"][0]["zona_id"])
        self.assertEqual("Aviario 1", pagina["leituras"][0]["zona_nome"])

    def test_historico_paginado_devolve_extremos_de_todo_o_filtro(self):
        zona = db.criar_zona({"nome": "Aviario 1", "especie": "frangos", "indice": "ITU"})
        for incremento in range(65):
            db.salvar_leitura(
                "frangos",
                "ITU",
                50.0 + incremento,
                "Conforto",
                {"tbs": 10.0 + incremento, "tbu": 20.0 + incremento},
                intervalo_minutos=0,
                zona_id=zona["id"],
            )

        pagina = db.obter_historico_leituras(
            limite=30, deslocamento=15, zona_id=zona["id"]
        )

        self.assertEqual(65, pagina["total"])
        self.assertEqual(30, len(pagina["leituras"]))
        self.assertEqual(65.0, pagina["leituras"][0]["valor"])
        self.assertEqual(94.0, pagina["leituras"][-1]["valor"])
        self.assertEqual({"ITU": 50.0}, pagina["minimos"]["indices"])
        self.assertEqual({"ITU": 114.0}, pagina["maximos"]["indices"])
        self.assertEqual(
            {"tbs": 10.0, "tbu": 20.0},
            pagina["minimos"]["entradas"],
        )
        self.assertEqual(
            {"tbs": 74.0, "tbu": 84.0},
            pagina["maximos"]["entradas"],
        )

    def test_historico_leituras_por_valor_devolve_os_dois_mais_proximos(self):
        zona = db.criar_zona({"nome": "Aviario 1", "especie": "frangos", "indice": "ITU"})
        for valor in (70.0, 72.0, 75.0, 80.0):
            db.salvar_leitura(
                "frangos",
                "ITU",
                valor,
                "Alerta",
                {"tbs": 26, "tbu": 21},
                intervalo_minutos=0,
                zona_id=zona["id"],
            )

        pagina = db.obter_historico_leituras(
            limite=30,
            zona_id=zona["id"],
            valor_referencia=73.4,
        )

        self.assertEqual(2, pagina["total"])
        self.assertEqual([72.0, 75.0], [leitura["valor"] for leitura in pagina["leituras"]])
        self.assertEqual(73.4, pagina["valor_referencia"])
        self.assertEqual([72.0, 75.0], pagina["valores_encontrados"])

    def test_historico_leituras_por_valor_exato_nao_inclui_outro_proximo(self):
        zona = db.criar_zona({"nome": "Aviario 1", "especie": "frangos", "indice": "ITU"})
        for valor in (70.0, 72.0, 75.0):
            db.salvar_leitura(
                "frangos",
                "ITU",
                valor,
                "Alerta",
                {"tbs": 26, "tbu": 21},
                intervalo_minutos=0,
                zona_id=zona["id"],
            )

        pagina = db.obter_historico_leituras(
            limite=30,
            zona_id=zona["id"],
            valor_referencia=72.0,
        )

        self.assertEqual([72.0], [leitura["valor"] for leitura in pagina["leituras"]])
        self.assertEqual([72.0], pagina["valores_encontrados"])

    def test_historico_leituras_filtra_periodo_sem_remover_paginacao(self):
        zona = db.criar_zona({"nome": "Aviario 1", "especie": "frangos", "indice": "ITU"})
        for valor in (70.0, 71.0, 72.0, 73.0):
            db.salvar_leitura(
                "frangos", "ITU", valor, "Alerta", {"tbs": valor - 45},
                intervalo_minutos=0, zona_id=zona["id"],
            )
        with db._conexao() as conn:
            ids = [linha["id"] for linha in conn.execute(
                "SELECT id FROM leituras ORDER BY id"
            ).fetchall()]
            datas = (
                "2024-01-31 12:00:00", "2024-02-01T00:00:00",
                "2024-02-29T23:59:59", "2024-03-01 00:00:00",
            )
            conn.executemany(
                "UPDATE leituras SET criado_em=? WHERE id=?", zip(datas, ids)
            )

        pagina = db.obter_historico_leituras(
            limite=30, zona_id=zona["id"],
            data_inicio="2024-02-01", data_fim="2024-02-29",
        )

        self.assertEqual(2, pagina["total"])
        self.assertEqual([71.0, 72.0], [item["valor"] for item in pagina["leituras"]])
        self.assertEqual(30, pagina["limite"])
        self.assertEqual({"ITU": 71.0}, pagina["minimos"]["indices"])
        self.assertEqual({"tbs": 26.0}, pagina["minimos"]["entradas"])
        self.assertEqual({"ITU": 72.0}, pagina["maximos"]["indices"])
        self.assertEqual({"tbs": 27.0}, pagina["maximos"]["entradas"])

    def test_configuracoes_retornam_padroes(self):
        configuracoes = db.obter_configuracoes()

        self.assertFalse(configuracoes["coletarDados"])
        self.assertEqual(1, configuracoes["intervaloLeituraSegundos"])
        self.assertEqual("medido", configuracoes["modoPontoOrvalho"])
        self.assertEqual("calculado", configuracoes["modoUmidadeRelativa"])
        self.assertEqual(70, configuracoes["limiteUmidadeNebulizador"])
        self.assertEqual("conforto", configuracoes["statusMinimoEmail"])

    def test_inicializacao_remove_configuracao_automatica_global_obsoleta(self):
        with db._conexao() as conn:
            conn.execute(
                "INSERT INTO configuracoes (chave, valor, atualizado_em) "
                "VALUES ('modoAutomatico', 'true', '2024-01-01T00:00:00')"
            )

        db.iniciar_banco()

        with db._conexao(escrita=False) as conn:
            linha = conn.execute(
                "SELECT 1 FROM configuracoes WHERE chave = 'modoAutomatico'"
            ).fetchone()
        self.assertIsNone(linha)

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

    def test_status_minimo_email_invalido_cai_para_padrao(self):
        salvas = db.salvar_configuracoes({"statusMinimoEmail": "critico"})
        self.assertEqual(
            db.CONFIGURACOES_PADRAO["statusMinimoEmail"],
            salvas["statusMinimoEmail"],
        )

    def test_status_minimo_email_valido_e_preservado(self):
        salvas = db.salvar_configuracoes({"statusMinimoEmail": "perigo"})
        self.assertEqual("perigo", salvas["statusMinimoEmail"])

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

    def test_listar_zonas_apenas_ativas_filtra_no_banco(self):
        ativa = db.criar_zona({"nome": "Ativa", "especie": "frangos", "indice": "ITU"})
        db.criar_zona({"nome": "Inativa", "especie": "frangos", "indice": "ITU", "ativa": False})

        zonas = db.listar_zonas(apenas_ativas=True)

        self.assertEqual([ativa["id"]], [zona["id"] for zona in zonas])

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


class TestEstatisticasZonas(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path_original = db.DB_PATH
        db.DB_PATH = os.path.join(self.tempdir.name, "historico.db")
        db.iniciar_banco()

    def tearDown(self):
        db.DB_PATH = self.db_path_original
        self.tempdir.cleanup()

    def test_zona_sem_leituras_devolve_percentuais_e_agregados_none(self):
        zona = db.criar_zona({"nome": "Zona 1", "especie": "frangos", "indice": "ITU"})

        [stats] = db.obter_estatisticas_zonas()

        self.assertEqual(zona["id"], stats["zona_id"])
        self.assertEqual(0, stats["total_leituras"])
        self.assertIsNone(stats["percentuais"])
        self.assertIsNone(stats["media"])
        self.assertIsNone(stats["minimo"])
        self.assertIsNone(stats["maximo"])

    def test_calcula_percentuais_e_agregados_da_zona(self):
        zona = db.criar_zona({"nome": "Zona 1", "especie": "frangos", "indice": "ITU"})
        leituras = [
            (70.0, "Conforto"),
            (72.0, "Conforto"),
            (80.0, "Alerta"),
            (90.0, "Perigo"),
        ]
        for valor, status in leituras:
            db.salvar_leitura(
                "frangos", "ITU", valor, status, {"tbs": 25, "tbu": 20},
                intervalo_minutos=0, zona_id=zona["id"],
            )

        [stats] = db.obter_estatisticas_zonas()

        self.assertEqual(4, stats["total_leituras"])
        self.assertEqual(
            {"Conforto": 50.0, "Alerta": 25.0, "Perigo": 25.0, "Emergência": 0.0},
            stats["percentuais"],
        )
        self.assertAlmostEqual(78.0, stats["media"])
        self.assertEqual(70.0, stats["minimo"])
        self.assertEqual(90.0, stats["maximo"])

    def test_ignora_leituras_de_um_indice_anterior_ao_atual_da_zona(self):
        zona = db.criar_zona({"nome": "Zona 1", "especie": "frangos", "indice": "ITU"})
        db.salvar_leitura(
            "frangos", "ITU", 70.0, "Conforto", {"tbs": 25, "tbu": 20},
            intervalo_minutos=0, zona_id=zona["id"],
        )
        db.atualizar_zona(zona["id"], {"nome": "Zona 1", "especie": "frangos", "indice": "ITUV", "ativa": True})
        db.salvar_leitura(
            "frangos", "ITUV", 20.0, "Conforto", {"tbs": 25, "tbu": 20, "vv": 1.5},
            intervalo_minutos=0, zona_id=zona["id"],
        )

        [stats] = db.obter_estatisticas_zonas()

        # So a leitura de ITUV (o indice atual da zona) entra nas contas --
        # misturar valores de ITU e ITUV na mesma media nao faria sentido
        # (escalas diferentes).
        self.assertEqual("ITUV", stats["indice"])
        self.assertEqual(1, stats["total_leituras"])
        self.assertEqual(20.0, stats["media"])

    def test_uma_entrada_por_zona_na_ordem_de_id(self):
        zona_b = db.criar_zona({"nome": "Zona B", "especie": "frangos", "indice": "ITU"})
        zona_a = db.criar_zona({"nome": "Zona A", "especie": "suinos", "indice": "IGNU"})

        stats = db.obter_estatisticas_zonas()

        self.assertEqual([zona_b["id"], zona_a["id"]], [s["zona_id"] for s in stats])


class TestPainelExecutivoZonas(unittest.TestCase):
    """Testa `obter_painel_zonas`, usada pelo card "Painel executivo por
    zona" da aba Analises. Como a funcao depende de `datetime.datetime.
    now()` internamente (mesmo padrao ja usado por `salvar_leitura`), os
    testes gravam a leitura normalmente e depois "voltam no tempo" o
    `criado_em` da linha via SQL direto -- igual ao teste de
    TestEstatisticasZonas la em cima que ignora leituras de indice
    anterior."""

    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path_original = db.DB_PATH
        db.DB_PATH = os.path.join(self.tempdir.name, "historico.db")
        db.iniciar_banco()

    def tearDown(self):
        db.DB_PATH = self.db_path_original
        self.tempdir.cleanup()

    def _inserir_leitura(
        self, zona_id, valor, status, quando, indice="ITU", especie="frangos", entradas=None
    ):
        self.assertTrue(
            db.salvar_leitura(
                especie,
                indice,
                valor,
                status,
                entradas if entradas is not None else {"tbs": 25, "tbu": 20},
                intervalo_minutos=0,
                zona_id=zona_id,
            )
        )
        with db._conexao() as conn:
            ultimo_id = conn.execute(
                "SELECT id FROM leituras WHERE zona_id = ? ORDER BY id DESC LIMIT 1", (zona_id,)
            ).fetchone()["id"]
            conn.execute(
                "UPDATE leituras SET criado_em = ? WHERE id = ?",
                (quando.replace(microsecond=0).isoformat(timespec="seconds"), ultimo_id),
            )

    def test_zona_sem_leituras_devolve_campos_none(self):
        zona = db.criar_zona({"nome": "Zona 1", "especie": "frangos", "indice": "ITU"})

        [painel] = db.obter_painel_zonas()

        self.assertEqual(zona["id"], painel["zona_id"])
        self.assertIsNone(painel["status_atual"])
        self.assertIsNone(painel["valor_atual"])
        self.assertIsNone(painel["ultima_leitura_em"])
        self.assertEqual({"15min": None, "30min": None, "60min": None}, painel["tendencias"])
        self.assertIsNone(painel["percentual_conforto_24h"])
        self.assertIsNone(painel["tempo_continuo_status_minutos"])
        self.assertIsNone(painel["nivel_maximo_dia"])
        self.assertEqual(0.0, painel["minutos_perigo_dia"])
        self.assertEqual(0.0, painel["minutos_emergencia_dia"])
        self.assertEqual(
            {"horario": None, "ja_ocorreu": False, "dias_amostrados": 0}, painel["pico_previsto"]
        )
        self.assertIsNone(painel["sensores_indisponiveis"])
        self.assertEqual(
            {
                "ventiladores_ligados": 0,
                "ventiladores_total": 0,
                "nebulizadores_ligados": 0,
                "nebulizadores_total": 0,
                "intensidade": None,
            },
            painel["equipamentos_ligados"],
        )
        self.assertEqual(
            "Ainda não há leitura registrada para esta zona.", painel["recomendacao"]
        )

    def test_status_e_valor_atuais_vem_da_leitura_mais_recente(self):
        zona = db.criar_zona({"nome": "Zona 1", "especie": "frangos", "indice": "ITU"})
        agora = datetime.datetime.now()
        self._inserir_leitura(zona["id"], 70.0, "Conforto", agora - datetime.timedelta(minutes=5))
        self._inserir_leitura(zona["id"], 82.0, "Perigo", agora)

        [painel] = db.obter_painel_zonas()

        self.assertEqual("Perigo", painel["status_atual"])
        self.assertEqual(82.0, painel["valor_atual"])

    def test_tendencia_classifica_subindo(self):
        zona = db.criar_zona({"nome": "Zona 1", "especie": "frangos", "indice": "ITU"})
        agora = datetime.datetime.now()
        self._inserir_leitura(zona["id"], 70.0, "Conforto", agora - datetime.timedelta(minutes=20))
        self._inserir_leitura(zona["id"], 75.0, "Alerta", agora)

        [painel] = db.obter_painel_zonas()

        self.assertEqual("subindo", painel["tendencias"]["15min"])

    def test_tendencia_classifica_descendo(self):
        zona = db.criar_zona({"nome": "Zona 1", "especie": "frangos", "indice": "ITU"})
        agora = datetime.datetime.now()
        self._inserir_leitura(zona["id"], 80.0, "Perigo", agora - datetime.timedelta(minutes=20))
        self._inserir_leitura(zona["id"], 74.0, "Alerta", agora)

        [painel] = db.obter_painel_zonas()

        self.assertEqual("descendo", painel["tendencias"]["15min"])

    def test_tendencia_classifica_estavel_dentro_do_epsilon(self):
        zona = db.criar_zona({"nome": "Zona 1", "especie": "frangos", "indice": "ITU"})
        agora = datetime.datetime.now()
        self._inserir_leitura(zona["id"], 75.2, "Alerta", agora - datetime.timedelta(minutes=20))
        self._inserir_leitura(zona["id"], 75.0, "Alerta", agora)

        [painel] = db.obter_painel_zonas()

        self.assertEqual("estavel", painel["tendencias"]["15min"])

    def test_tendencia_none_sem_leitura_na_janela(self):
        zona = db.criar_zona({"nome": "Zona 1", "especie": "frangos", "indice": "ITU"})
        self._inserir_leitura(zona["id"], 75.0, "Alerta", datetime.datetime.now())

        [painel] = db.obter_painel_zonas()

        self.assertEqual({"15min": None, "30min": None, "60min": None}, painel["tendencias"])

    def test_percentual_conforto_24h_ignora_leituras_mais_antigas(self):
        zona = db.criar_zona({"nome": "Zona 1", "especie": "frangos", "indice": "ITU"})
        agora = datetime.datetime.now()
        # Fora da janela de 24h -- nao deve entrar na conta.
        self._inserir_leitura(
            zona["id"], 90.0, "Emergência", agora - datetime.timedelta(hours=25)
        )
        self._inserir_leitura(zona["id"], 70.0, "Conforto", agora - datetime.timedelta(hours=2))
        self._inserir_leitura(zona["id"], 71.0, "Conforto", agora - datetime.timedelta(hours=1))
        self._inserir_leitura(zona["id"], 78.0, "Alerta", agora)

        [painel] = db.obter_painel_zonas()

        self.assertAlmostEqual(66.7, painel["percentual_conforto_24h"], places=1)

    def test_tempo_continuo_status_atual_conta_desde_inicio_da_sequencia(self):
        zona = db.criar_zona({"nome": "Zona 1", "especie": "frangos", "indice": "ITU"})
        agora = datetime.datetime.now()
        self._inserir_leitura(zona["id"], 78.0, "Alerta", agora - datetime.timedelta(minutes=50))
        self._inserir_leitura(zona["id"], 82.0, "Perigo", agora - datetime.timedelta(minutes=40))
        self._inserir_leitura(zona["id"], 83.0, "Perigo", agora - datetime.timedelta(minutes=10))

        [painel] = db.obter_painel_zonas()

        self.assertAlmostEqual(40.0, painel["tempo_continuo_status_minutos"], delta=0.5)

    def test_nivel_maximo_e_minutos_perigo_emergencia_hoje(self):
        zona = db.criar_zona({"nome": "Zona 1", "especie": "frangos", "indice": "ITU"})
        agora = datetime.datetime.now()
        self._inserir_leitura(zona["id"], 70.0, "Conforto", agora - datetime.timedelta(minutes=40))
        self._inserir_leitura(zona["id"], 82.0, "Perigo", agora - datetime.timedelta(minutes=30))
        self._inserir_leitura(
            zona["id"], 90.0, "Emergência", agora - datetime.timedelta(minutes=20)
        )
        self._inserir_leitura(zona["id"], 72.0, "Conforto", agora - datetime.timedelta(minutes=5))

        [painel] = db.obter_painel_zonas()

        self.assertEqual("Emergência", painel["nivel_maximo_dia"])
        self.assertAlmostEqual(10.0, painel["minutos_perigo_dia"], delta=0.2)
        self.assertAlmostEqual(15.0, painel["minutos_emergencia_dia"], delta=0.2)

    def test_pico_previsto_usa_media_dos_dias_anteriores_e_ignora_hoje(self):
        zona = db.criar_zona({"nome": "Zona 1", "especie": "frangos", "indice": "ITU"})
        hoje = datetime.date.today()

        def _quando(dia, hora, minuto):
            return datetime.datetime.combine(dia, datetime.time(hora, minuto))

        for dias_atras, hora, minuto in ((3, 13, 50), (2, 14, 0), (1, 14, 10)):
            dia = hoje - datetime.timedelta(days=dias_atras)
            # leitura mais baixa no mesmo dia, para garantir que o pico
            # encontrado e o valor MAXIMO do dia, e nao qualquer leitura.
            self._inserir_leitura(zona["id"], 70.0, "Conforto", _quando(dia, hora - 2, 0))
            self._inserir_leitura(zona["id"], 88.0, "Perigo", _quando(dia, hora, minuto))

        # Leitura de hoje: deve ficar de fora da media do padrao historico.
        self._inserir_leitura(zona["id"], 92.0, "Emergência", datetime.datetime.now())

        [painel] = db.obter_painel_zonas()
        pico = painel["pico_previsto"]

        self.assertEqual(3, pico["dias_amostrados"])
        self.assertEqual("14:00", pico["horario"])

    def test_pico_previsto_none_com_menos_de_dois_dias_anteriores(self):
        zona = db.criar_zona({"nome": "Zona 1", "especie": "frangos", "indice": "ITU"})
        ontem = datetime.datetime.combine(
            datetime.date.today() - datetime.timedelta(days=1), datetime.time(14, 0)
        )
        self._inserir_leitura(zona["id"], 88.0, "Perigo", ontem)
        self._inserir_leitura(zona["id"], 75.0, "Alerta", datetime.datetime.now())

        [painel] = db.obter_painel_zonas()

        self.assertEqual(
            {"horario": None, "ja_ocorreu": False, "dias_amostrados": 1}, painel["pico_previsto"]
        )

    def test_sensores_indisponiveis_detecta_campo_ausente_na_ultima_leitura(self):
        zona = db.criar_zona({"nome": "Zona 1", "especie": "frangos", "indice": "ITU"})
        db.criar_equipamento(
            zona["id"],
            {
                "tipo": "sensor",
                "nome": "Sensor TBS",
                "modo_conexao": "tcp",
                "host": "10.0.0.5",
                "tipo_registrador": "input",
                "endereco_registrador": 1,
                "campo_medido": "tbs",
            },
        )
        db.criar_equipamento(
            zona["id"],
            {
                "tipo": "sensor",
                "nome": "Sensor TBU",
                "modo_conexao": "tcp",
                "host": "10.0.0.6",
                "tipo_registrador": "input",
                "endereco_registrador": 2,
                "campo_medido": "tbu",
            },
        )
        # `tbu` ausente nas entradas simula o sensor correspondente sem
        # resposta na ultima leitura.
        self._inserir_leitura(
            zona["id"], 70.0, "Conforto", datetime.datetime.now(), entradas={"tbs": 25}
        )

        [painel] = db.obter_painel_zonas()

        self.assertEqual(["Sensor TBU"], painel["sensores_indisponiveis"])

    def test_sensores_indisponiveis_vazio_quando_todos_respondem(self):
        zona = db.criar_zona({"nome": "Zona 1", "especie": "frangos", "indice": "ITU"})
        db.criar_equipamento(
            zona["id"],
            {
                "tipo": "sensor",
                "nome": "Sensor TBS",
                "modo_conexao": "tcp",
                "host": "10.0.0.5",
                "tipo_registrador": "input",
                "endereco_registrador": 1,
                "campo_medido": "tbs",
            },
        )
        self._inserir_leitura(
            zona["id"], 70.0, "Conforto", datetime.datetime.now(), entradas={"tbs": 25, "tbu": 20}
        )

        [painel] = db.obter_painel_zonas()

        self.assertEqual([], painel["sensores_indisponiveis"])

    def test_recomendacao_sem_leitura(self):
        db.criar_zona({"nome": "Zona 1", "especie": "frangos", "indice": "ITU"})

        [painel] = db.obter_painel_zonas()

        self.assertEqual(
            "Ainda não há leitura registrada para esta zona.", painel["recomendacao"]
        )

    def test_recomendacao_menciona_tendencia_de_subida_em_perigo(self):
        zona = db.criar_zona({"nome": "Zona 1", "especie": "frangos", "indice": "ITU"})
        agora = datetime.datetime.now()
        self._inserir_leitura(zona["id"], 78.0, "Perigo", agora - datetime.timedelta(minutes=20))
        self._inserir_leitura(zona["id"], 82.0, "Perigo", agora)

        [painel] = db.obter_painel_zonas()

        self.assertEqual("subindo", painel["tendencias"]["15min"])
        self.assertIn("subindo", painel["recomendacao"])

    def test_recomendacao_menciona_sensores_indisponiveis(self):
        zona = db.criar_zona({"nome": "Zona 1", "especie": "frangos", "indice": "ITU"})
        db.criar_equipamento(
            zona["id"],
            {
                "tipo": "sensor",
                "nome": "Sensor TBU",
                "modo_conexao": "tcp",
                "host": "10.0.0.6",
                "tipo_registrador": "input",
                "endereco_registrador": 2,
                "campo_medido": "tbu",
            },
        )
        self._inserir_leitura(
            zona["id"], 70.0, "Conforto", datetime.datetime.now(), entradas={"tbs": 25}
        )

        [painel] = db.obter_painel_zonas()

        self.assertIn("1 sensor sem leitura recente", painel["recomendacao"])

    def test_equipamentos_ligados_totais_conta_ventiladores_e_nebulizadores(self):
        zona = db.criar_zona({"nome": "Zona 1", "especie": "frangos", "indice": "ITU"})
        for indice_equip in range(2):
            db.criar_equipamento(
                zona["id"],
                {
                    "tipo": "ventilador",
                    "nome": f"Ventilador {indice_equip}",
                    "modo_conexao": "tcp",
                    "host": "10.0.0.5",
                    "tipo_registrador": "coil",
                    "endereco_registrador": indice_equip,
                },
            )
        db.criar_equipamento(
            zona["id"],
            {
                "tipo": "nebulizador",
                "nome": "Nebulizador 0",
                "modo_conexao": "tcp",
                "host": "10.0.0.5",
                "tipo_registrador": "coil",
                "endereco_registrador": 10,
            },
        )

        [painel] = db.obter_painel_zonas()

        # Sem nenhuma gravacao em `estado_equipamentos` ainda, os totais
        # aparecem corretamente mas nada conta como ligado.
        self.assertEqual(
            {
                "ventiladores_ligados": 0,
                "ventiladores_total": 2,
                "nebulizadores_ligados": 0,
                "nebulizadores_total": 1,
                "intensidade": None,
            },
            painel["equipamentos_ligados"],
        )

    def test_equipamentos_ligados_reflete_estado_persistido(self):
        zona = db.criar_zona({"nome": "Zona 1", "especie": "frangos", "indice": "ITU"})
        for indice_equip in range(2):
            db.criar_equipamento(
                zona["id"],
                {
                    "tipo": "ventilador",
                    "nome": f"Ventilador {indice_equip}",
                    "modo_conexao": "tcp",
                    "host": "10.0.0.5",
                    "tipo_registrador": "coil",
                    "endereco_registrador": indice_equip,
                },
            )
        db.criar_equipamento(
            zona["id"],
            {
                "tipo": "nebulizador",
                "nome": "Nebulizador 0",
                "modo_conexao": "tcp",
                "host": "10.0.0.5",
                "tipo_registrador": "coil",
                "endereco_registrador": 10,
            },
        )

        db.salvar_estado_equipamentos(
            zona["id"],
            True,
            False,
            "media",
            True,
            False,
            True,
            False,
            [],
            "boa",
        )

        [painel] = db.obter_painel_zonas()

        self.assertEqual(
            {
                "ventiladores_ligados": 2,
                "ventiladores_total": 2,
                "nebulizadores_ligados": 0,
                "nebulizadores_total": 1,
                "intensidade": "media",
            },
            painel["equipamentos_ligados"],
        )

    def test_salvar_estado_equipamentos_faz_upsert_sem_duplicar_linha(self):
        zona = db.criar_zona({"nome": "Zona 1", "especie": "frangos", "indice": "ITU"})

        db.salvar_estado_equipamentos(
            zona["id"], True, True, "alta", True, True, True, True, [], "boa"
        )
        db.salvar_estado_equipamentos(
            zona["id"], False, False, None, False, False, False, False, [], "boa"
        )

        with db._conexao() as conn:
            linhas = conn.execute(
                "SELECT * FROM estado_equipamentos WHERE zona_id = ?", (zona["id"],)
            ).fetchall()

        self.assertEqual(1, len(linhas))
        self.assertEqual(0, linhas[0]["ventilador_ligado"])
        self.assertEqual(0, linhas[0]["nebulizador_ligado"])
        self.assertIsNone(linhas[0]["intensidade"])


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

    def test_criar_equipamento_em_zona_inexistente_levanta_subclasse_especifica(self):
        # A subclasse especifica permite que a camada HTTP devolva 404
        # sem interpretar mensagens nem reconsultar o banco.
        with self.assertRaises(db.ZonaNaoEncontradaError):
            db.criar_equipamento(9999, self._equipamento_base())

    def test_criar_equipamento_com_dados_invalidos_em_zona_inexistente_reporta_zona(self):
        # Quando ZONA e DADOS estao errados ao mesmo tempo, a checagem da
        # zona vem primeiro (ver `criar_equipamento`): o erro reportado e
        # "zona nao encontrada", nao um erro de validacao dos dados do
        # equipamento, que sequer chegou a ser conferido.
        with self.assertRaises(db.ZonaNaoEncontradaError):
            db.criar_equipamento(9999, {"tipo": "tipo-invalido"})

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

class TestConcorrenciaLeituraEscrita(unittest.TestCase):
    """`_conexao(escrita=False)` (usada por toda leitura) nao deve esperar
    por uma escrita em andamento neste processo: em modo WAL, um leitor
    trabalha com sua propria snapshot, entao serializa-lo atras do escritor
    custaria latencia sem nenhum ganho de correcao. Ja duas ESCRITAS devem
    continuar se serializando (ver `_write_lock`)."""

    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path_original = db.DB_PATH
        db.DB_PATH = os.path.join(self.tempdir.name, "historico.db")
        db.iniciar_banco()

    def tearDown(self):
        db.DB_PATH = self.db_path_original
        self.tempdir.cleanup()

    def test_leitura_nao_espera_escrita_em_andamento(self):
        escrita_em_andamento = threading.Event()
        pode_liberar_escrita = threading.Event()

        def escrita_lenta():
            with db._conexao():
                escrita_em_andamento.set()
                pode_liberar_escrita.wait(timeout=2)

        thread_escrita = threading.Thread(target=escrita_lenta)
        thread_escrita.start()
        self.assertTrue(escrita_em_andamento.wait(timeout=2), "escrita não começou a tempo")

        inicio = time.monotonic()
        db.obter_historico_leituras()
        duracao = time.monotonic() - inicio

        pode_liberar_escrita.set()
        thread_escrita.join(timeout=2)

        self.assertLess(
            duracao, 0.5,
            "uma leitura esperou por uma escrita em andamento; "
            "verifique se a consulta do histórico ainda usa escrita=False",
        )

    def test_duas_escritas_continuam_serializadas(self):
        primeira_em_andamento = threading.Event()
        pode_liberar_primeira = threading.Event()
        segunda_comecou_em = []

        def primeira_escrita():
            with db._conexao():
                primeira_em_andamento.set()
                pode_liberar_primeira.wait(timeout=2)

        def segunda_escrita():
            self.assertTrue(primeira_em_andamento.wait(timeout=2))
            with db._conexao():
                segunda_comecou_em.append(time.monotonic())

        thread1 = threading.Thread(target=primeira_escrita)
        thread2 = threading.Thread(target=segunda_escrita)
        thread1.start()
        thread1.join(timeout=0)  # so garante que a thread foi agendada
        self.assertTrue(primeira_em_andamento.wait(timeout=2))

        thread2.start()
        time.sleep(0.1)
        # A segunda escrita nao pode ter entrado em `_conexao()` enquanto a
        # primeira ainda segura o lock.
        self.assertEqual([], segunda_comecou_em)

        pode_liberar_primeira.set()
        thread1.join(timeout=2)
        thread2.join(timeout=2)
        self.assertEqual(1, len(segunda_comecou_em))


class TestUsuariosCRUD(unittest.TestCase):
    """CRUD de `usuarios` na camada de persistencia.
    Testes de sessao/login/HTTP ficam em test_auth.py; aqui so a logica de
    banco -- validacao, unicidade de login e as travas do ultimo
    administrador."""

    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path_original = db.DB_PATH
        db.DB_PATH = os.path.join(self.tempdir.name, "historico.db")
        db.iniciar_banco()

    def tearDown(self):
        db.DB_PATH = self.db_path_original
        self.tempdir.cleanup()

    @staticmethod
    def _dados(**sobrescreve):
        base = {
            "nome": "Ana Admin",
            "login": "ana",
            "perfil": "administrador",
            "senha_hash": "hash-fake-nao-importa-aqui",
        }
        base.update(sobrescreve)
        return base

    def test_criar_usuario_nao_devolve_senha_hash(self):
        usuario = db.criar_usuario(self._dados())
        self.assertNotIn("senha_hash", usuario)
        self.assertEqual("ana", usuario["login"])
        self.assertTrue(usuario["ativo"])

    def test_criar_usuario_recusa_nome_vazio(self):
        with self.assertRaises(db.UsuarioInvalidoError):
            db.criar_usuario(self._dados(nome="  "))

    def test_criar_usuario_recusa_login_vazio(self):
        with self.assertRaises(db.UsuarioInvalidoError):
            db.criar_usuario(self._dados(login=""))

    def test_criar_usuario_recusa_login_com_espaco(self):
        with self.assertRaises(db.UsuarioInvalidoError):
            db.criar_usuario(self._dados(login="ana silva"))

    def test_criar_usuario_recusa_perfil_invalido(self):
        with self.assertRaises(db.UsuarioInvalidoError):
            db.criar_usuario(self._dados(perfil="fiscal"))

    def test_criar_usuario_recusa_sem_senha(self):
        dados = self._dados()
        del dados["senha_hash"]
        with self.assertRaises(db.UsuarioInvalidoError):
            db.criar_usuario(dados)

    def test_login_duplicado_e_recusado_mesmo_com_letras_diferentes(self):
        db.criar_usuario(self._dados(login="ana"))
        with self.assertRaises(db.UsuarioInvalidoError):
            db.criar_usuario(self._dados(login="ANA", nome="Outra Ana"))

    def test_obter_usuario_por_login_e_case_insensitive(self):
        criado = db.criar_usuario(self._dados(login="ana"))
        encontrado = db.obter_usuario_por_login("ANA")
        self.assertIsNotNone(encontrado)
        self.assertEqual(criado["id"], encontrado["id"])
        # Unica funcao que devolve o hash de verdade -- ver docstring.
        self.assertIn("senha_hash", encontrado)

    def test_obter_usuario_por_login_inexistente_devolve_none(self):
        self.assertIsNone(db.obter_usuario_por_login("ninguem"))

    def test_listar_usuarios_ordena_por_nome(self):
        db.criar_usuario(self._dados(nome="Zeca", login="zeca"))
        db.criar_usuario(self._dados(nome="Ana", login="ana2"))
        nomes = [u["nome"] for u in db.listar_usuarios()]
        self.assertEqual(["Ana", "Zeca"], nomes)

    def test_atualizar_usuario_preserva_senha_quando_nao_informada(self):
        criado = db.criar_usuario(self._dados())
        db.atualizar_usuario(
            criado["id"], {"nome": "Ana A. Admin", "login": "ana", "perfil": "administrador", "ativo": True}
        )
        interno = db.obter_usuario_por_login("ana")
        self.assertEqual("hash-fake-nao-importa-aqui", interno["senha_hash"])
        self.assertEqual("Ana A. Admin", interno["nome"])

    def test_atualizar_usuario_troca_senha_quando_informada(self):
        criado = db.criar_usuario(self._dados())
        db.atualizar_usuario(
            criado["id"],
            {
                "nome": "Ana Admin", "login": "ana", "perfil": "administrador",
                "ativo": True, "senha_hash": "novo-hash",
            },
        )
        interno = db.obter_usuario_por_login("ana")
        self.assertEqual("novo-hash", interno["senha_hash"])

    def test_atualizar_usuario_inexistente_levanta_erro(self):
        with self.assertRaises(db.UsuarioNaoEncontradoError):
            db.atualizar_usuario(9999, self._dados())

    def test_atualizar_usuario_recusa_login_ja_usado_por_outro(self):
        db.criar_usuario(self._dados(login="ana"))
        outro = db.criar_usuario(self._dados(login="bruno", perfil="operador"))
        with self.assertRaises(db.UsuarioInvalidoError):
            db.atualizar_usuario(outro["id"], self._dados(login="ana", perfil="operador"))

    def test_nao_deixa_rebaixar_o_ultimo_administrador_ativo(self):
        unico_admin = db.criar_usuario(self._dados())
        with self.assertRaises(db.UltimoAdministradorError):
            db.atualizar_usuario(
                unico_admin["id"],
                {"nome": "Ana", "login": "ana", "perfil": "operador", "ativo": True},
            )

    def test_nao_deixa_desativar_o_ultimo_administrador_ativo(self):
        unico_admin = db.criar_usuario(self._dados())
        with self.assertRaises(db.UltimoAdministradorError):
            db.atualizar_usuario(
                unico_admin["id"],
                {"nome": "Ana", "login": "ana", "perfil": "administrador", "ativo": False},
            )

    def test_rebaixar_e_permitido_quando_existe_outro_administrador_ativo(self):
        primeiro = db.criar_usuario(self._dados())
        db.criar_usuario(self._dados(login="bruno", nome="Bruno"))
        resultado = db.atualizar_usuario(
            primeiro["id"],
            {"nome": "Ana", "login": "ana", "perfil": "operador", "ativo": True},
        )
        self.assertEqual("operador", resultado["perfil"])

    def test_excluir_usuario_inexistente_devolve_false(self):
        self.assertFalse(db.excluir_usuario(9999))

    def test_nao_deixa_excluir_o_ultimo_administrador_ativo(self):
        unico_admin = db.criar_usuario(self._dados())
        with self.assertRaises(db.UltimoAdministradorError):
            db.excluir_usuario(unico_admin["id"])
        # A conta continua intacta apos a tentativa recusada.
        self.assertIsNotNone(db.obter_usuario(unico_admin["id"]))

    def test_excluir_e_permitido_quando_existe_outro_administrador_ativo(self):
        primeiro = db.criar_usuario(self._dados())
        db.criar_usuario(self._dados(login="bruno", nome="Bruno"))
        self.assertTrue(db.excluir_usuario(primeiro["id"]))
        self.assertIsNone(db.obter_usuario(primeiro["id"]))

    def test_registrar_login_usuario_grava_timestamp(self):
        criado = db.criar_usuario(self._dados())
        self.assertIsNone(criado["ultimo_login_em"])
        db.registrar_login_usuario(criado["id"])
        atualizado = db.obter_usuario(criado["id"])
        self.assertIsNotNone(atualizado["ultimo_login_em"])


if __name__ == "__main__":
    unittest.main()
