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

    def test_api_persiste_configuracoes(self):
        payload = {
            "coletarDados": True,
            "habilitarSons": True,
            "enviarEmails": True,
            "habilitarEquipamentos": True,
            "emailDestino": "teste@fazenda.com.br",
            "statusMinimoEmail": "perigo",
            "modoAutomatico": True,
            "intervaloLeituraSegundos": 4,
            "intervaloGravacaoMinutos": 2,
            "modoPontoOrvalho": "calculado",
            "modoUmidadeRelativa": "medido",
            "altitudeMetros": 800,
            "limiteUmidadeNebulizador": 68,
            "especie": "bovinos",
            "indice": "IGNU",
            "smtpHost": "smtp.fazenda.com.br",
            "smtpPorta": 465,
            "smtpUsuario": "sistema@fazenda.com.br",
            "smtpSenha": "segredo-app-password",
            "modoSimuladoZonas": False,
        }

        salvar = self.client.post("/api/configuracoes", json=payload)
        buscar = self.client.get("/api/configuracoes")

        self.assertEqual(200, salvar.status_code)
        self.assertEqual(200, buscar.status_code)

        # A senha SMTP nunca volta em texto puro pelo HTTP -- nem na
        # resposta do proprio POST que acabou de salva-la, nem em GETs
        # seguintes. O cliente so recebe a confirmacao de que ela esta
        # configurada.
        esperado_publico = dict(payload)
        esperado_publico["smtpSenha"] = ""
        esperado_publico["smtpSenhaConfigurada"] = True
        self.assertEqual(esperado_publico, salvar.json)
        self.assertEqual(esperado_publico, buscar.json)

    def test_api_mantem_senha_smtp_ao_salvar_sem_reenviar(self):
        primeiro = self.client.post(
            "/api/configuracoes", json={"smtpHost": "smtp.fazenda.com.br", "smtpSenha": "segredo123"}
        )
        self.assertTrue(primeiro.json["smtpSenhaConfigurada"])

        # Um segundo salvamento (ex.: so mudando outro campo qualquer) sem
        # reenviar a senha nao deve apagar a ja configurada.
        segundo = self.client.post(
            "/api/configuracoes", json={"smtpHost": "smtp.fazenda.com.br", "habilitarSons": True}
        )
        self.assertTrue(segundo.json["smtpSenhaConfigurada"])
        self.assertTrue(self.client.get("/api/configuracoes").json["smtpSenhaConfigurada"])

    def test_api_indice_incompativel_com_especie_cai_para_indice_valido(self):
        # ITUV so existe para frangos: ao mudar a especie persistida para
        # bovinos mantendo indice=ITUV, o servidor deve corrigir sozinho
        # para um indice valido daquela especie, em vez de guardar uma
        # combinacao impossivel.
        resposta = self.client.post(
            "/api/configuracoes", json={"especie": "bovinos", "indice": "ITUV"}
        )
        self.assertEqual("bovinos", resposta.json["especie"])
        self.assertIn(resposta.json["indice"], ("ITU", "IGNU"))

    def test_nao_calcula_indices_sem_campos_preenchidos(self):
        resposta = self.client.post(
            "/api/calcular",
            json={
                "especie": "frangos",
                "indice": "ITU",
                "entradas": {"tbs": 25, "tbu": 20},
                "config": {},
            },
        )

        self.assertEqual(200, resposta.status_code)
        self.assertEqual({"ITU"}, set(resposta.json["indices"]))
        self.assertEqual("ITU", resposta.json["indice"])

    def test_calcula_indice_compartilhado_quando_campos_estao_preenchidos(self):
        resposta = self.client.post(
            "/api/calcular",
            json={
                "especie": "frangos",
                "indice": "ITUV",
                "entradas": {"tbs": 25, "tbu": 20, "v": 1},
                "config": {},
            },
        )

        self.assertEqual(200, resposta.status_code)
        self.assertEqual({"ITU", "ITUV"}, set(resposta.json["indices"]))
        self.assertNotIn("IGNU", resposta.json["indices"])

    def test_indice_selecionado_continua_exigindo_campos(self):
        resposta = self.client.post(
            "/api/calcular",
            json={
                "especie": "frangos",
                "indice": "IGNU",
                "entradas": {"tgn": 25},
                "config": {},
            },
        )

        self.assertEqual(400, resposta.status_code)
        self.assertIn("Preencha todos os campos exigidos", resposta.json["erro"])

    def test_ignu_calcula_ponto_de_orvalho_por_tbs_tbu(self):
        resposta = self.client.post(
            "/api/calcular",
            json={
                "especie": "frangos",
                "indice": "IGNU",
                "entradas": {"tgn": 25, "tbs": 25, "tbu": 20},
                "config": {"modoPontoOrvalho": "calculado", "altitudeMetros": 0},
            },
        )

        self.assertEqual(200, resposta.status_code)
        self.assertAlmostEqual(17.5, resposta.json["entradas"]["tpo"], places=1)
        self.assertAlmostEqual(63.0, resposta.json["entradas"]["ur"], places=1)
        self.assertAlmostEqual(62.8, resposta.json["valor"], places=1)

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

    def test_email_da_api_inclui_dados_usados_no_calculo(self):
        resposta = self.client.post(
            "/api/calcular",
            json={
                "especie": "frangos",
                "indice": "ITUV",
                "entradas": {"tbs": 30, "tbu": 24, "v": 1.5},
                "config": {
                    "enviarEmails": True,
                    "emailDestino": "produtor@fazenda.com.br",
                },
            },
        )

        self.assertEqual(200, resposta.status_code)
        conteudo = resposta.json["email"]["conteudo"]
        self.assertIn("Dados usados no cálculo:", conteudo)
        self.assertIn("Temperatura de Bulbo Seco / Ambiente (tbs): 30.0", conteudo)
        self.assertIn("Temperatura de Bulbo Úmido (tbu): 24.0", conteudo)
        self.assertIn("Velocidade do Ar (v): 1.5 m/s", conteudo)

    def test_email_da_api_respeita_status_minimo_configurado(self):
        abaixo_do_limiar = self.client.post(
            "/api/calcular",
            json={
                "especie": "frangos",
                "indice": "ITUV",
                "entradas": {"tbs": 30, "tbu": 24, "v": 1.5},
                "config": {
                    "enviarEmails": True,
                    "emailDestino": "produtor@fazenda.com.br",
                    "statusMinimoEmail": "perigo",
                },
            },
        )
        acima_do_limiar = self.client.post(
            "/api/calcular",
            json={
                "especie": "frangos",
                "indice": "ITU",
                "entradas": {"tbs": 35, "tbu": 30},
                "config": {
                    "enviarEmails": True,
                    "emailDestino": "produtor@fazenda.com.br",
                    "statusMinimoEmail": "perigo",
                },
            },
        )

        self.assertEqual(200, abaixo_do_limiar.status_code)
        self.assertEqual("Alerta", abaixo_do_limiar.json["status"])
        self.assertIsNone(abaixo_do_limiar.json["email"])

        self.assertEqual(200, acima_do_limiar.status_code)
        self.assertEqual("Emergência", acima_do_limiar.json["status"])
        self.assertIsNotNone(acima_do_limiar.json["email"])

    def test_nebulizador_nao_liga_acima_do_limite_de_umidade(self):
        resposta = self.client.post(
            "/api/calcular",
            json={
                "especie": "frangos",
                "indice": "ITU",
                "entradas": {"tbs": 35, "tbu": 33},
                "config": {
                    "habilitarEquipamentos": True,
                    "limiteUmidadeNebulizador": 70,
                },
            },
        )

        self.assertEqual(200, resposta.status_code)
        self.assertEqual("Emergência", resposta.json["status"])
        self.assertGreater(resposta.json["entradas"]["ur"], 70)
        self.assertTrue(resposta.json["equipamento"]["ventilador"])
        self.assertFalse(resposta.json["equipamento"]["nebulizador"])

    def test_nebulizador_liga_quando_umidade_esta_no_limite(self):
        resposta = self.client.post(
            "/api/calcular",
            json={
                "especie": "frangos",
                "indice": "ITU",
                "entradas": {"tbs": 35, "tbu": 30},
                "config": {
                    "habilitarEquipamentos": True,
                    "limiteUmidadeNebulizador": 70,
                },
            },
        )

        self.assertEqual(200, resposta.status_code)
        self.assertEqual("Emergência", resposta.json["status"])
        self.assertLessEqual(resposta.json["entradas"]["ur"], 70)
        self.assertTrue(resposta.json["equipamento"]["ventilador"])
        self.assertTrue(resposta.json["equipamento"]["nebulizador"])

    def test_umidade_relativa_medida_nao_e_recalculada(self):
        resposta = self.client.post(
            "/api/calcular",
            json={
                "especie": "frangos",
                "indice": "ITU",
                "entradas": {"tbs": 35, "tbu": 33, "ur": 50},
                "config": {
                    "habilitarEquipamentos": True,
                    "modoUmidadeRelativa": "medido",
                    "limiteUmidadeNebulizador": 70,
                },
            },
        )

        self.assertEqual(200, resposta.status_code)
        self.assertEqual(50.0, resposta.json["entradas"]["ur"])
        self.assertTrue(resposta.json["equipamento"]["ventilador"])
        self.assertTrue(resposta.json["equipamento"]["nebulizador"])

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
        self.assertTrue(resposta.json["equipamento"]["ativo"])
        self.assertEqual(1, resposta.json["equipamento"]["leituras_conforto_consecutivas"])

        leitura_conforto_2 = self.client.get("/api/sensor?especie=frangos&indice=ITU").json
        self.assertLess(leitura_conforto_2["tbs"], resposta.json["entradas"]["tbs"])
        self.assertLess(leitura_conforto_2["tbu"], resposta.json["entradas"]["tbu"])
        segunda_conforto = self.client.post(
            "/api/calcular",
            json={
                "especie": "frangos",
                "indice": "ITU",
                "entradas": {**base_entradas, **leitura_conforto_2},
                "config": {"habilitarEquipamentos": True},
            },
        )
        self.assertEqual("Conforto", segunda_conforto.json["status"])
        self.assertTrue(segunda_conforto.json["equipamento"]["ativo"])
        self.assertEqual(2, segunda_conforto.json["equipamento"]["leituras_conforto_consecutivas"])

        leitura_conforto_3 = self.client.get("/api/sensor?especie=frangos&indice=ITU").json
        self.assertLess(leitura_conforto_3["tbs"], segunda_conforto.json["entradas"]["tbs"])
        self.assertLess(leitura_conforto_3["tbu"], segunda_conforto.json["entradas"]["tbu"])
        terceira_conforto = self.client.post(
            "/api/calcular",
            json={
                "especie": "frangos",
                "indice": "ITU",
                "entradas": {**base_entradas, **leitura_conforto_3},
                "config": {"habilitarEquipamentos": True},
            },
        )
        self.assertEqual("Conforto", terceira_conforto.json["status"])
        self.assertFalse(terceira_conforto.json["equipamento"]["ativo"])

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


class TestServidorLocal(unittest.TestCase):
    def test_servidor_local_nao_usa_reloader_e_debug_comeca_desligado(self):
        """O runner passa por AppConfig; por padrao (sem variaveis de
        ambiente CONFORTO_*), o debug deve vir DESLIGADO -- ver a nota de
        seguranca no topo de web.py sobre o console interativo do
        Werkzeug. Passar uma AppConfig explicita torna o teste
        deterministico, sem depender do ambiente de quem roda a suite."""
        config = flask_app.AppConfig(
            debug=False, host="127.0.0.1", port=5000, threaded=True, max_content_length=1_000_000
        )
        with patch.object(flask_app.app, "run") as run:
            flask_app.executar_servidor_local(config)

        run.assert_called_once_with(
            debug=False, host="127.0.0.1", port=5000, threaded=True, use_reloader=False
        )

    def test_servidor_local_respeita_config_explicita(self):
        config = flask_app.AppConfig(
            debug=True, host="0.0.0.0", port=8080, threaded=False, max_content_length=1_000_000
        )
        with patch.object(flask_app.app, "run") as run:
            flask_app.executar_servidor_local(config)

        run.assert_called_once_with(
            debug=True, host="0.0.0.0", port=8080, threaded=False, use_reloader=False
        )

    def test_app_config_from_env_usa_padroes_seguros_sem_variaveis(self):
        ambiente_limpo = {
            chave: valor
            for chave, valor in os.environ.items()
            if not chave.startswith("CONFORTO_")
        }
        with patch.dict(os.environ, ambiente_limpo, clear=True):
            config = flask_app.AppConfig.from_env()

        self.assertFalse(config.debug)
        self.assertEqual("127.0.0.1", config.host)
        self.assertEqual(5000, config.port)

    def test_app_config_from_env_le_variaveis_customizadas(self):
        variaveis = {
            "CONFORTO_DEBUG": "1",
            "CONFORTO_HOST": "0.0.0.0",
            "CONFORTO_PORT": "9090",
            "CONFORTO_THREADED": "0",
        }
        with patch.dict(os.environ, variaveis):
            config = flask_app.AppConfig.from_env()

        self.assertTrue(config.debug)
        self.assertEqual("0.0.0.0", config.host)
        self.assertEqual(9090, config.port)
        self.assertFalse(config.threaded)


class TestValidacaoDeParametros(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path_original = db.DB_PATH
        db.DB_PATH = os.path.join(self.tempdir.name, "historico.db")
        db.iniciar_banco()
        self.client = flask_app.app.test_client()

    def tearDown(self):
        db.DB_PATH = self.db_path_original
        self.tempdir.cleanup()

    def test_historico_rejeita_especie_desconhecida(self):
        resposta = self.client.get("/api/historico?especie=marciano&indice=ITU")
        self.assertEqual(400, resposta.status_code)
        self.assertIn("erro", resposta.json)

    def test_historico_rejeita_indice_incompativel_com_especie(self):
        # ITUV so existe para frangos, nao para bovinos.
        resposta = self.client.get("/api/historico?especie=bovinos&indice=ITUV")
        self.assertEqual(400, resposta.status_code)

    def test_historico_todos_rejeita_especie_desconhecida(self):
        resposta = self.client.get("/api/historico-todos?especie=marciano")
        self.assertEqual(400, resposta.status_code)

    def test_historico_grafico_todos_rejeita_especie_desconhecida(self):
        resposta = self.client.get("/api/historico-grafico-todos?especie=marciano")
        self.assertEqual(400, resposta.status_code)

    def test_sensor_rejeita_indice_incompativel_com_especie(self):
        resposta = self.client.get("/api/sensor?especie=suinos&indice=ITUV")
        self.assertEqual(400, resposta.status_code)

    def test_reset_rejeita_especie_desconhecida(self):
        resposta = self.client.post("/api/reset", json={"especie": "marciano"})
        self.assertEqual(400, resposta.status_code)

    def test_reset_aceita_ausencia_de_especie_e_indice(self):
        resposta = self.client.post("/api/reset", json={})
        self.assertEqual(200, resposta.status_code)
        self.assertTrue(resposta.json["ok"])

    def test_backup_banco_cria_arquivo_no_mesmo_diretorio(self):
        db.salvar_leitura("frangos", "ITU", 70.0, "Conforto", {"tbs": 25, "tbu": 20})

        resposta = self.client.post("/api/backup-banco")

        self.assertEqual(200, resposta.status_code)
        self.assertTrue(resposta.json["ok"])
        caminho = resposta.json["backup"]["caminho"]
        self.assertTrue(os.path.exists(caminho))
        self.assertEqual(os.path.dirname(db.DB_PATH), os.path.dirname(caminho))

    def test_historico_com_parametros_validos_continua_funcionando(self):
        resposta = self.client.get("/api/historico?especie=frangos&indice=ITU")
        self.assertEqual(200, resposta.status_code)
        self.assertEqual([], resposta.json)


class TestCabecalhosDeSeguranca(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path_original = db.DB_PATH
        db.DB_PATH = os.path.join(self.tempdir.name, "historico.db")
        db.iniciar_banco()
        self.client = flask_app.app.test_client()

    def tearDown(self):
        db.DB_PATH = self.db_path_original
        self.tempdir.cleanup()

    def test_resposta_api_inclui_cabecalhos_de_seguranca(self):
        resposta = self.client.get("/api/configuracoes")
        self.assertEqual("nosniff", resposta.headers.get("X-Content-Type-Options"))
        self.assertEqual("DENY", resposta.headers.get("X-Frame-Options"))
        self.assertEqual("no-referrer", resposta.headers.get("Referrer-Policy"))
        self.assertEqual("no-store", resposta.headers.get("Cache-Control"))

    def test_pagina_inicial_carrega_com_dicionarios_congelados(self):
        # thermal_indices.py congela seus dicts com MappingProxyType; esta
        # rota depende do ProvedorJSON customizado para serializar
        # `| tojson` corretamente. Um regressao aqui quebraria a pagina
        # inteira com um TypeError silencioso no lado do servidor.
        resposta = self.client.get("/")
        self.assertEqual(200, resposta.status_code)
        self.assertIn(b"indicesPorEspecie", resposta.data)


class TestErroInternoNaoVazaDetalhe(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path_original = db.DB_PATH
        db.DB_PATH = os.path.join(self.tempdir.name, "historico.db")
        db.iniciar_banco()
        self.client = flask_app.app.test_client()

    def tearDown(self):
        db.DB_PATH = self.db_path_original
        self.tempdir.cleanup()

    def test_excecao_inesperada_nao_vaza_mensagem_original(self):
        segredo = "detalhe-interno-sensivel-do-servidor"
        with patch.object(
            flask_app.calculo_ict_service, "calcular", side_effect=RuntimeError(segredo)
        ):
            resposta = self.client.post(
                "/api/calcular",
                json={
                    "especie": "frangos",
                    "indice": "ITU",
                    "entradas": {"tbs": 25, "tbu": 20},
                    "config": {},
                },
            )

        self.assertEqual(500, resposta.status_code)
        self.assertNotIn(segredo, resposta.json["erro"])
        self.assertEqual(flask_app.MENSAGEM_ERRO_INTERNO, resposta.json["erro"])


class TestZonasApi(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path_original = db.DB_PATH
        db.DB_PATH = os.path.join(self.tempdir.name, "historico.db")
        db.iniciar_banco()
        flask_app.zona_service.limpar_historico_grafico()
        self.client = flask_app.app.test_client()

    def tearDown(self):
        flask_app.zona_service.limpar_historico_grafico()
        db.DB_PATH = self.db_path_original
        self.tempdir.cleanup()

    def _criar_zona(self, **sobrescritas):
        payload = {"nome": "Aviário 1", "especie": "frangos", "indice": "ITU"}
        payload.update(sobrescritas)
        return self.client.post("/api/zonas", json=payload)

    def test_criar_e_listar_zona(self):
        resposta = self._criar_zona()
        self.assertEqual(201, resposta.status_code)
        zona_id = resposta.json["id"]

        lista = self.client.get("/api/zonas")
        self.assertEqual(200, lista.status_code)
        self.assertEqual(1, len(lista.json))
        self.assertEqual(zona_id, lista.json[0]["id"])

    def test_criar_zona_invalida_devolve_400(self):
        resposta = self._criar_zona(nome="")
        self.assertEqual(400, resposta.status_code)
        self.assertIn("erro", resposta.json)

    def test_obter_zona_inexistente_devolve_404(self):
        resposta = self.client.get("/api/zonas/9999")
        self.assertEqual(404, resposta.status_code)

    def test_atualizar_zona(self):
        zona_id = self._criar_zona().json["id"]
        resposta = self.client.put(
            f"/api/zonas/{zona_id}",
            json={"nome": "Renomeada", "especie": "frangos", "indice": "IGNU"},
        )
        self.assertEqual(200, resposta.status_code)
        self.assertEqual("Renomeada", resposta.json["nome"])
        self.assertEqual("IGNU", resposta.json["indice"])

    def test_atualizar_zona_inexistente_devolve_404(self):
        resposta = self.client.put(
            "/api/zonas/9999", json={"nome": "x", "especie": "frangos", "indice": "ITU"}
        )
        self.assertEqual(404, resposta.status_code)

    def test_excluir_zona(self):
        zona_id = self._criar_zona().json["id"]
        resposta = self.client.delete(f"/api/zonas/{zona_id}")
        self.assertEqual(200, resposta.status_code)
        self.assertEqual(404, self.client.get(f"/api/zonas/{zona_id}").status_code)

    def test_criar_equipamento_na_zona(self):
        zona_id = self._criar_zona().json["id"]
        resposta = self.client.post(
            f"/api/zonas/{zona_id}/equipamentos",
            json={
                "tipo": "sensor",
                "nome": "Sensor TBS",
                "modo_conexao": "tcp",
                "host": "192.168.0.10",
                "tipo_registrador": "input",
                "endereco_registrador": 100,
                "campo_medido": "tbs",
            },
        )
        self.assertEqual(201, resposta.status_code)
        self.assertEqual(zona_id, resposta.json["zona_id"])

    def test_criar_equipamento_em_zona_inexistente_devolve_404(self):
        resposta = self.client.post(
            "/api/zonas/9999/equipamentos",
            json={
                "tipo": "sensor", "nome": "x", "modo_conexao": "tcp", "host": "1",
                "tipo_registrador": "input", "endereco_registrador": 1, "campo_medido": "tbs",
            },
        )
        self.assertEqual(404, resposta.status_code)

    def test_criar_equipamento_invalido_devolve_400(self):
        zona_id = self._criar_zona().json["id"]
        resposta = self.client.post(
            f"/api/zonas/{zona_id}/equipamentos",
            json={"tipo": "aspirador", "nome": "x", "modo_conexao": "tcp", "host": "1",
                  "tipo_registrador": "input", "endereco_registrador": 1},
        )
        self.assertEqual(400, resposta.status_code)

    def test_excluir_equipamento(self):
        zona_id = self._criar_zona().json["id"]
        equipamento_id = self.client.post(
            f"/api/zonas/{zona_id}/equipamentos",
            json={
                "tipo": "sensor", "nome": "Sensor TBS", "modo_conexao": "tcp", "host": "1",
                "tipo_registrador": "input", "endereco_registrador": 1, "campo_medido": "tbs",
            },
        ).json["id"]

        resposta = self.client.delete(f"/api/zonas/{zona_id}/equipamentos/{equipamento_id}")
        self.assertEqual(200, resposta.status_code)

        zona = self.client.get(f"/api/zonas/{zona_id}").json
        self.assertEqual([], zona["equipamentos"])

    def test_excluir_equipamento_de_outra_zona_devolve_404(self):
        zona_a = self._criar_zona(nome="Zona A").json["id"]
        zona_b = self._criar_zona(nome="Zona B").json["id"]
        equipamento_id = self.client.post(
            f"/api/zonas/{zona_a}/equipamentos",
            json={
                "tipo": "sensor", "nome": "Sensor", "modo_conexao": "tcp", "host": "1",
                "tipo_registrador": "input", "endereco_registrador": 1, "campo_medido": "tbs",
            },
        ).json["id"]

        resposta = self.client.delete(f"/api/zonas/{zona_b}/equipamentos/{equipamento_id}")
        self.assertEqual(404, resposta.status_code)

    def test_calcular_zona_sem_sensores_respondendo_devolve_400(self):
        zona_id = self._criar_zona().json["id"]
        self.client.post(
            f"/api/zonas/{zona_id}/equipamentos",
            json={
                "tipo": "sensor", "nome": "Sensor Inatingível", "modo_conexao": "tcp",
                "host": "203.0.113.1", "porta": 502, "tipo_registrador": "input",
                "endereco_registrador": 1, "campo_medido": "tbs",
            },
        )
        # Mocka a leitura Modbus (em vez de bater numa rede real) para o
        # teste ser rapido e deterministico -- o objetivo aqui e validar o
        # tratamento de erro da rota, nao o cliente Modbus em si (isso ja
        # e coberto em test_modbus_client.py).
        with patch.object(flask_app.zona_service, "_ler_modbus", return_value=None):
            resposta = self.client.post(f"/api/zonas/{zona_id}/calcular")
        self.assertEqual(400, resposta.status_code)
        self.assertIn("erro", resposta.json)

    def test_calcular_zona_inexistente_devolve_400(self):
        resposta = self.client.post("/api/zonas/9999/calcular")
        self.assertEqual(400, resposta.status_code)

    def test_calcular_zona_com_entradas_digitadas_nao_exige_sensores(self):
        zona_id = self._criar_zona().json["id"]
        resposta = self.client.post(
            f"/api/zonas/{zona_id}/calcular",
            json={"entradas": {"tbs": 25.0, "tbu": 20.0}},
        )
        self.assertEqual(200, resposta.status_code)
        self.assertEqual(zona_id, resposta.json["zona_id"])
        self.assertEqual(1, len(resposta.json["historico_grafico"]))
        self.assertEqual(1, len(db.obter_historico_por_zona(zona_id)))

    def test_reset_limpa_historico_visual_e_persistido_das_zonas(self):
        zona_id = self._criar_zona().json["id"]
        self.client.post(
            f"/api/zonas/{zona_id}/calcular",
            json={"entradas": {"tbs": 25.0, "tbu": 20.0}},
        )
        self.assertEqual(1, len(self.client.get(f"/api/zonas/{zona_id}/historico").json))
        self.assertEqual(1, len(db.obter_historico_por_zona(zona_id)))

        resposta = self.client.post("/api/reset", json={})

        self.assertEqual(200, resposta.status_code)
        self.assertEqual([], self.client.get(f"/api/zonas/{zona_id}/historico").json)
        self.assertEqual([], db.obter_historico_por_zona(zona_id))

    def test_email_da_zona_inclui_dados_usados_no_calculo(self):
        self.client.post(
            "/api/configuracoes",
            json={"enviarEmails": True, "emailDestino": "produtor@fazenda.com.br"},
        )
        zona_id = self._criar_zona().json["id"]

        resposta = self.client.post(
            f"/api/zonas/{zona_id}/calcular",
            json={"entradas": {"tbs": 25.0, "tbu": 20.0}},
        )

        self.assertEqual(200, resposta.status_code)
        conteudo = resposta.json["email"]["conteudo"]
        self.assertIn(f"Zona: Aviário 1 (ID {zona_id})", conteudo)
        self.assertIn("Dados usados no cálculo:", conteudo)
        self.assertIn("Temperatura de Bulbo Seco / Ambiente (tbs): 25.0", conteudo)
        self.assertIn("Temperatura de Bulbo Úmido (tbu): 20.0", conteudo)

    def test_email_das_zonas_respeita_status_minimo_configurado(self):
        self.client.post(
            "/api/configuracoes",
            json={
                "enviarEmails": True,
                "emailDestino": "produtor@fazenda.com.br",
                "statusMinimoEmail": "perigo",
            },
        )
        zona_conforto = self._criar_zona(nome="Zona Conforto").json["id"]
        zona_emergencia = self._criar_zona(nome="Zona Emergencia").json["id"]

        for zona_id in (zona_conforto, zona_emergencia):
            for campo in ("tbs", "tbu"):
                self.client.post(
                    f"/api/zonas/{zona_id}/equipamentos",
                    json={
                        "tipo": "sensor",
                        "nome": f"Sensor {campo.upper()} {zona_id}",
                        "modo_conexao": "tcp",
                        "host": "127.0.0.1",
                        "porta": 502,
                        "tipo_registrador": "input",
                        "endereco_registrador": 1,
                        "campo_medido": campo,
                    },
                )

        def ler_modbus(equipamento):
            if equipamento["zona_id"] == zona_conforto:
                return 25.0 if equipamento["campo_medido"] == "tbs" else 20.0
            return 35.0 if equipamento["campo_medido"] == "tbs" else 30.0

        with patch.object(flask_app.zona_service, "_ler_modbus", side_effect=ler_modbus):
            resposta = self.client.post("/api/zonas/calcular-ativas")

        self.assertEqual(200, resposta.status_code)
        por_zona = {item["zona_id"]: item for item in resposta.json["resultados"]}
        self.assertEqual("Conforto", por_zona[zona_conforto]["status"])
        self.assertNotIn("email", por_zona[zona_conforto])

        self.assertEqual("Emergência", por_zona[zona_emergencia]["status"])
        self.assertNotIn("email", por_zona[zona_emergencia])

        self.assertIn("email", resposta.json)
        self.assertEqual([zona_emergencia], resposta.json["email"]["zonas"])
        conteudo = resposta.json["email"]["conteudo"]
        self.assertIn("Zona: Zona Emergencia", conteudo)
        self.assertNotIn("Zona: Zona Conforto", conteudo)

    def test_calcular_zonas_ativas_usa_sensores_de_todas_as_ativas(self):
        zona_a = self._criar_zona(nome="Zona A").json["id"]
        zona_b = self._criar_zona(nome="Zona B").json["id"]
        zona_inativa = self._criar_zona(nome="Zona Inativa", ativa=False).json["id"]
        for zona_id in (zona_a, zona_b, zona_inativa):
            for campo in ("tbs", "tbu"):
                self.client.post(
                    f"/api/zonas/{zona_id}/equipamentos",
                    json={
                        "tipo": "sensor",
                        "nome": f"Sensor {campo.upper()} {zona_id}",
                        "modo_conexao": "tcp",
                        "host": "127.0.0.1",
                        "porta": 502,
                        "tipo_registrador": "input",
                        "endereco_registrador": 1,
                        "campo_medido": campo,
                    },
                )

        def ler_modbus(equipamento):
            return 25.0 if equipamento["campo_medido"] == "tbs" else 20.0

        with patch.object(flask_app.zona_service, "_ler_modbus", side_effect=ler_modbus):
            resposta = self.client.post("/api/zonas/calcular-ativas")

        self.assertEqual(200, resposta.status_code)
        ids = {item["zona_id"] for item in resposta.json["resultados"]}
        self.assertEqual({zona_a, zona_b}, ids)
        self.assertNotIn(zona_inativa, ids)

    def test_calcular_zonas_ativas_nao_derruba_rota_com_entrada_invalida(self):
        zona_id = self._criar_zona(nome="Zona ITUV", indice="ITUV").json["id"]
        for campo in ("tbs", "tbu", "v"):
            self.client.post(
                f"/api/zonas/{zona_id}/equipamentos",
                json={
                    "tipo": "sensor",
                    "nome": f"Sensor {campo.upper()}",
                    "modo_conexao": "tcp",
                    "host": "127.0.0.1",
                    "porta": 502,
                    "tipo_registrador": "input",
                    "endereco_registrador": 1,
                    "campo_medido": campo,
                },
            )

        def ler_modbus(equipamento):
            valores = {"tbs": 25.0, "tbu": 20.0, "v": -0.27}
            return valores[equipamento["campo_medido"]]

        with patch.object(flask_app.zona_service, "_ler_modbus", side_effect=ler_modbus):
            resposta = self.client.post("/api/zonas/calcular-ativas")

        self.assertEqual(200, resposta.status_code)
        self.assertEqual(zona_id, resposta.json["resultados"][0]["zona_id"])
        self.assertIn("fora da faixa esperada", resposta.json["resultados"][0]["erro"])

    def test_historico_de_zona_inexistente_devolve_404(self):
        resposta = self.client.get("/api/zonas/9999/historico")
        self.assertEqual(404, resposta.status_code)

    def test_historico_de_zona_vazio_inicialmente(self):
        zona_id = self._criar_zona().json["id"]
        resposta = self.client.get(f"/api/zonas/{zona_id}/historico")
        self.assertEqual(200, resposta.status_code)
        self.assertEqual([], resposta.json)

    def test_historico_leituras_persistido_exibe_zona(self):
        zona = self._criar_zona().json
        db.salvar_leitura(
            "frangos",
            "ITU",
            71.0,
            "Alerta",
            {"tbs": 26.0, "tbu": 21.0},
            intervalo_minutos=0,
            zona_id=zona["id"],
        )

        resposta = self.client.get("/api/historico-leituras?limite=30")

        self.assertEqual(200, resposta.status_code)
        self.assertEqual(1, resposta.json["total"])
        self.assertEqual(zona["id"], resposta.json["leituras"][0]["zona_id"])
        self.assertEqual(zona["nome"], resposta.json["leituras"][0]["zona_nome"])

    def test_historico_leituras_rejeita_zona_inexistente(self):
        resposta = self.client.get("/api/historico-leituras?zona_id=9999")
        self.assertEqual(404, resposta.status_code)

    def test_grafico_de_zona_atualiza_a_cada_calculo_mesmo_sem_gravar_no_banco(self):
        zona_id = self._criar_zona().json["id"]
        for campo in ("tbs", "tbu"):
            self.client.post(
                f"/api/zonas/{zona_id}/equipamentos",
                json={
                    "tipo": "sensor",
                    "nome": f"Sensor {campo.upper()}",
                    "modo_conexao": "tcp",
                    "host": "127.0.0.1",
                    "porta": 502,
                    "tipo_registrador": "input",
                    "endereco_registrador": 1,
                    "campo_medido": campo,
                },
            )

        ciclos = [{"tbs": 25.0, "tbu": 20.0}, {"tbs": 26.0, "tbu": 21.0}]
        chamadas = []

        def ler_modbus(equipamento):
            ciclo = min(len(chamadas) // 2, len(ciclos) - 1)
            chamadas.append(equipamento["campo_medido"])
            return ciclos[ciclo][equipamento["campo_medido"]]

        with patch.object(flask_app.zona_service, "_ler_modbus", side_effect=ler_modbus):
            primeira = self.client.post(f"/api/zonas/{zona_id}/calcular")
            segunda = self.client.post(f"/api/zonas/{zona_id}/calcular")

        self.assertEqual(200, primeira.status_code)
        self.assertTrue(primeira.json["leitura_gravada"])
        self.assertEqual(1, len(primeira.json["historico_grafico"]))

        self.assertEqual(200, segunda.status_code)
        self.assertFalse(segunda.json["leitura_gravada"])
        self.assertEqual(2, len(segunda.json["historico_grafico"]))

        historico_endpoint = self.client.get(f"/api/zonas/{zona_id}/historico")
        self.assertEqual(200, historico_endpoint.status_code)
        self.assertEqual(2, len(historico_endpoint.json))
        self.assertEqual(1, len(db.obter_historico_por_zona(zona_id)))

    def test_grafico_de_zona_mantem_ultimas_30_leituras(self):
        zona_id = self._criar_zona().json["id"]
        ultima = None
        for i in range(31):
            ultima = self.client.post(
                f"/api/zonas/{zona_id}/calcular",
                json={"entradas": {"tbs": 20.0 + i, "tbu": 18.0}},
            )

        self.assertEqual(200, ultima.status_code)
        self.assertEqual(30, len(ultima.json["historico_grafico"]))
        self.assertEqual(21.0, ultima.json["historico_grafico"][0]["entradas"]["tbs"])
        self.assertEqual(50.0, ultima.json["historico_grafico"][-1]["entradas"]["tbs"])

    def test_testar_conexao_de_equipamento_inexistente_devolve_404(self):
        zona_id = self._criar_zona().json["id"]
        resposta = self.client.post(f"/api/zonas/{zona_id}/equipamentos/9999/testar-conexao")
        self.assertEqual(404, resposta.status_code)


if __name__ == "__main__":
    unittest.main()
