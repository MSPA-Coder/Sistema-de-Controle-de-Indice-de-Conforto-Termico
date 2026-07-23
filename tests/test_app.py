# -*- coding: utf-8 -*-

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import app_factory
from app import database as db
from app.coletor import estado as coletor_estado
from app import web as flask_app
from tests.auth_test_utils import cliente_autenticado


class TestConfiguracoesApi(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path_original = db.DB_PATH
        db.DB_PATH = os.path.join(self.tempdir.name, "historico.db")
        db.iniciar_banco()
        self.client = cliente_autenticado(flask_app.app)

    def tearDown(self):
        db.DB_PATH = self.db_path_original
        self.tempdir.cleanup()

    def test_api_persiste_configuracoes(self):
        payload = {
            "coletarDados": True,
            "habilitarSons": True,
            "enviarEmails": True,
            "habilitarEquipamentos": True,
            "emailDestino": "teste@fazenda.com.br",
            "statusMinimoEmail": "perigo",
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


class TestServidorLocal(unittest.TestCase):
    def test_servidor_local_nao_usa_reloader_e_debug_comeca_desligado(self):
        """O runner passa por AppConfig; por padrao (sem variaveis de
        ambiente CONFORTO_*), o debug deve vir DESLIGADO -- ver a nota de
        seguranca em `app_factory.py` sobre o console interativo do
        Werkzeug. Passar uma AppConfig explicita torna o teste
        deterministico, sem depender do ambiente de quem roda a suite."""
        config = app_factory.AppConfig(
            debug=False, host="127.0.0.1", port=5000, threaded=True, max_content_length=1_000_000
        )
        with patch.object(flask_app.app, "run") as run:
            flask_app.executar_servidor_local(config)

        run.assert_called_once_with(
            debug=False, host="127.0.0.1", port=5000, threaded=True, use_reloader=False
        )

    def test_servidor_local_respeita_config_explicita(self):
        config = app_factory.AppConfig(
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
            config = app_factory.AppConfig.from_env()

        self.assertFalse(config.debug)
        self.assertEqual("127.0.0.1", config.host)
        self.assertEqual(5000, config.port)

    def test_app_config_from_env_usa_config_por_papel(self):
        with tempfile.TemporaryDirectory() as tempdir:
            config_path = Path(tempdir) / "servidor.json"
            config_path.write_text(
                """
{
  "padrao": {"host": "127.0.0.1", "port": 5000},
  "coletor": {"port": 5100},
  "dashboard": {"port": 5101}
}
""".strip(),
                encoding="utf-8",
            )
            ambiente_limpo = {
                chave: valor
                for chave, valor in os.environ.items()
                if not chave.startswith("CONFORTO_")
            }

            with patch.object(app_factory, "CONFIG_SERVIDOR_PATH", config_path):
                with patch.dict(os.environ, ambiente_limpo, clear=True):
                    coletor = app_factory.AppConfig.from_env("coletor")
                    dashboard = app_factory.AppConfig.from_env("dashboard")

        self.assertEqual(5100, coletor.port)
        self.assertEqual(5101, dashboard.port)

    def test_app_config_from_env_le_variaveis_customizadas(self):
        variaveis = {
            "CONFORTO_DEBUG": "1",
            "CONFORTO_HOST": "0.0.0.0",
            "CONFORTO_PORT": "9090",
            "CONFORTO_THREADED": "0",
        }
        with patch.dict(os.environ, variaveis):
            config = app_factory.AppConfig.from_env()

        self.assertTrue(config.debug)
        self.assertEqual("0.0.0.0", config.host)
        self.assertEqual(9090, config.port)
        self.assertFalse(config.threaded)


class TestManutencaoApi(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path_original = db.DB_PATH
        db.DB_PATH = os.path.join(self.tempdir.name, "historico.db")
        db.iniciar_banco()
        self.client = cliente_autenticado(flask_app.app)

    def tearDown(self):
        db.DB_PATH = self.db_path_original
        self.tempdir.cleanup()

    def test_reset_limpa_o_historico(self):
        resposta = self.client.post("/api/reset", json={})
        self.assertEqual(200, resposta.status_code)
        self.assertTrue(resposta.json["ok"])

    def test_backup_banco_cria_arquivo_no_mesmo_diretorio(self):
        zona = db.criar_zona(
            {"nome": "Zona backup", "especie": "frangos", "indice": "ITU"}
        )
        db.salvar_leitura(
            "frangos",
            "ITU",
            70.0,
            "Conforto",
            {"tbs": 25, "tbu": 20},
            zona_id=zona["id"],
        )

        resposta = self.client.post("/api/backup-banco")

        self.assertEqual(200, resposta.status_code)
        self.assertTrue(resposta.json["ok"])
        caminho = resposta.json["backup"]["caminho"]
        self.assertTrue(os.path.exists(caminho))
        self.assertEqual(os.path.dirname(db.DB_PATH), os.path.dirname(caminho))


class TestCabecalhosDeSeguranca(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path_original = db.DB_PATH
        db.DB_PATH = os.path.join(self.tempdir.name, "historico.db")
        db.iniciar_banco()
        self.client = cliente_autenticado(flask_app.app)

    def tearDown(self):
        db.DB_PATH = self.db_path_original
        self.tempdir.cleanup()

    def test_resposta_api_inclui_cabecalhos_de_seguranca(self):
        resposta = self.client.get("/api/configuracoes")
        self.assertEqual("nosniff", resposta.headers.get("X-Content-Type-Options"))
        self.assertEqual("DENY", resposta.headers.get("X-Frame-Options"))
        self.assertEqual("no-referrer", resposta.headers.get("Referrer-Policy"))
        self.assertEqual("no-store", resposta.headers.get("Cache-Control"))

    def test_pagina_inicial_renderiza_configuracao_dos_indices(self):
        resposta = self.client.get("/")
        self.assertEqual(200, resposta.status_code)
        self.assertIn(b"indicesPorEspecie", resposta.data)


class TestErroInternoNaoVazaDetalhe(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path_original = db.DB_PATH
        db.DB_PATH = os.path.join(self.tempdir.name, "historico.db")
        db.iniciar_banco()
        self.client = cliente_autenticado(flask_app.app)

    def tearDown(self):
        db.DB_PATH = self.db_path_original
        self.tempdir.cleanup()

    def test_excecao_inesperada_nao_vaza_mensagem_original(self):
        zona = self.client.post(
            "/api/zonas",
            json={"nome": "Zona de teste", "especie": "frangos", "indice": "ITU"},
        ).json
        segredo = "detalhe-interno-sensivel-do-servidor"
        with patch.object(
            coletor_estado.gerenciador_controle,
            "calcular_manual",
            side_effect=RuntimeError(segredo),
        ), patch.object(flask_app.app.logger, "exception") as registrar_erro:
            resposta = self.client.post(
                f"/api/zonas/{zona['id']}/calcular",
                json={"entradas": {"tbs": 25, "tbu": 20}},
            )

        self.assertEqual(500, resposta.status_code)
        self.assertNotIn(segredo, resposta.json["erro"])
        self.assertEqual(app_factory.MENSAGEM_ERRO_INTERNO, resposta.json["erro"])
        registrar_erro.assert_called_once()


class TestZonasApi(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path_original = db.DB_PATH
        db.DB_PATH = os.path.join(self.tempdir.name, "historico.db")
        db.iniciar_banco()
        coletor_estado.zona_service.limpar_historico_grafico()
        coletor_estado.zona_service.limpar_resfriador()
        self.client = cliente_autenticado(flask_app.app)

    def tearDown(self):
        coletor_estado.zona_service.limpar_historico_grafico()
        coletor_estado.zona_service.limpar_resfriador()
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

    def test_modos_travas_comando_e_estado_confirmado(self):
        zona_id = self._criar_zona().json["id"]
        self.client.post(
            f"/api/zonas/{zona_id}/equipamentos",
            json={
                "tipo": "ventilador",
                "nome": "VENT-OPERACAO",
                "modo_conexao": "tcp",
                "host": "127.0.0.1",
                "tipo_registrador": "coil",
                "endereco_registrador": 0,
            },
        )

        bloqueado = self.client.post(
            f"/api/zonas/{zona_id}/comando",
            json={"tipo": "ventilador", "ligar": True},
        )
        self.assertEqual(400, bloqueado.status_code)

        self.client.post("/api/configuracoes", json={"habilitarEquipamentos": True})
        controle = self.client.put(
            f"/api/zonas/{zona_id}/controle",
            json={"modo": "manual", "acionamento_habilitado": True},
        )
        self.assertEqual(200, controle.status_code)

        comando = self.client.post(
            f"/api/zonas/{zona_id}/comando",
            json={"tipo": "ventilador", "ligar": True},
        )
        self.assertEqual(200, comando.status_code)
        self.assertTrue(comando.json["desejado"])
        self.assertTrue(comando.json["confirmado"])

        status = self.client.get("/api/operacao/status").json
        [estado_zona] = status["zonas"]
        self.assertEqual("manual", estado_zona["modo"])
        self.assertTrue(estado_zona["desejado"]["ventilador"])
        self.assertTrue(estado_zona["confirmado"]["ventilador"])
        self.assertTrue(self.client.get(f"/api/operacao/eventos?zona_id={zona_id}").json)

        self.client.put(
            f"/api/zonas/{zona_id}/controle", json={"modo": "automatico"}
        )
        manual_fora_do_modo = self.client.post(
            f"/api/zonas/{zona_id}/calcular",
            json={"entradas": {"tbs": 25, "tbu": 20}},
        )
        self.assertEqual(400, manual_fora_do_modo.status_code)

    def test_criar_zona_invalida_devolve_400(self):
        resposta = self._criar_zona(nome="")
        self.assertEqual(400, resposta.status_code)
        self.assertIn("erro", resposta.json)

    def test_analises_devolve_uma_entrada_por_zona(self):
        zona = self._criar_zona().json

        resposta = self.client.get("/api/analises")

        self.assertEqual(200, resposta.status_code)
        self.assertEqual(1, len(resposta.json))
        self.assertEqual(zona["id"], resposta.json[0]["zona_id"])
        self.assertIsNone(resposta.json[0]["percentuais"])

    def test_painel_executivo_devolve_uma_entrada_por_zona_sem_leitura(self):
        zona = self._criar_zona().json

        resposta = self.client.get("/api/analises/painel-executivo")

        self.assertEqual(200, resposta.status_code)
        self.assertEqual(1, len(resposta.json))
        painel = resposta.json[0]
        self.assertEqual(zona["id"], painel["zona_id"])
        self.assertIsNone(painel["status_atual"])
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
        self.assertIn("Ainda não há leitura", painel["recomendacao"])

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
        with patch.object(coletor_estado.zona_service, "_ler_modbus", return_value=None):
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

    def test_historico_leituras_rejeita_valor_referencia_invalido(self):
        resposta = self.client.get("/api/historico-leituras?valor_referencia=nao-numerico")
        self.assertEqual(400, resposta.status_code)
        self.assertIn("numérico", resposta.json["erro"])

    def test_historico_leituras_filtra_pelos_valores_mais_proximos(self):
        zona = self._criar_zona().json
        for valor in (70.0, 72.0, 75.0, 80.0):
            db.salvar_leitura(
                "frangos",
                "ITU",
                valor,
                "Alerta",
                {"tbs": 26.0, "tbu": 21.0},
                intervalo_minutos=0,
                zona_id=zona["id"],
            )

        resposta = self.client.get(
            f"/api/historico-leituras?zona_id={zona['id']}&valor_referencia=73.4"
        )

        self.assertEqual(200, resposta.status_code)
        self.assertEqual([72.0, 75.0], [leitura["valor"] for leitura in resposta.json["leituras"]])
        self.assertEqual([72.0, 75.0], resposta.json["valores_encontrados"])

    def test_historico_leituras_api_aceita_periodo_com_paginacao(self):
        zona = self._criar_zona().json
        for valor in (70.0, 71.0, 72.0):
            db.salvar_leitura(
                "frangos", "ITU", valor, "Alerta",
                {"tbs": valor - 45, "tbu": valor - 50},
                intervalo_minutos=0, zona_id=zona["id"],
            )
        with db._conexao() as conn:
            ids = [linha["id"] for linha in conn.execute(
                "SELECT id FROM leituras ORDER BY id"
            ).fetchall()]
            conn.executemany(
                "UPDATE leituras SET criado_em=? WHERE id=?",
                zip(
                    ("2024-01-31 23:59:59", "2024-02-01T00:00:00", "2024-02-29 23:59:59"),
                    ids,
                ),
            )

        resposta = self.client.get(
            f"/api/historico-leituras?zona_id={zona['id']}"
            "&data_inicio=2024-02-01&data_fim=2024-02-29"
        )

        self.assertEqual(200, resposta.status_code)
        self.assertEqual(2, resposta.json["total"])
        self.assertEqual(30, resposta.json["limite"])
        self.assertEqual([71.0, 72.0], [item["valor"] for item in resposta.json["leituras"]])
        self.assertEqual({"ITU": 71.0}, resposta.json["minimos"]["indices"])
        self.assertEqual({"ITU": 72.0}, resposta.json["maximos"]["indices"])
        self.assertEqual(
            {"tbs": 26.0, "tbu": 21.0},
            resposta.json["minimos"]["entradas"],
        )
        self.assertEqual(
            {"tbs": 27.0, "tbu": 22.0},
            resposta.json["maximos"]["entradas"],
        )

    def test_historico_leituras_api_rejeita_periodo_invertido(self):
        resposta = self.client.get(
            "/api/historico-leituras?data_inicio=2024-03-01&data_fim=2024-02-01"
        )
        self.assertEqual(400, resposta.status_code)
        self.assertIn("posterior", resposta.json["erro"])

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

        with patch.object(coletor_estado.zona_service, "_ler_modbus", side_effect=ler_modbus):
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
