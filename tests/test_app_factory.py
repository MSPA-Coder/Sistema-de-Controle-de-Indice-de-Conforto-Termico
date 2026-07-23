# -*- coding: utf-8 -*-
"""
test_app_factory.py
=====================
Testa `app_factory.criar_app`: cada `papel_app` registra o conjunto de
rotas esperado, o dashboard nao carrega codigo relacionado a Modbus e
os apps de coleta e visualizacao compartilham o mesmo banco SQLite."""

import os
import re
import sys
import tempfile
import unittest

from app import database as db
from app.app_factory import AppConfig, criar_app
from tests.auth_test_utils import cliente_autenticado


class TestCriarAppPorPapel(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path_original = db.DB_PATH
        db.DB_PATH = os.path.join(self.tempdir.name, "historico.db")

    def tearDown(self):
        db.DB_PATH = self.db_path_original
        self.tempdir.cleanup()

    @staticmethod
    def _rotas(app, metodo):
        return {
            regra.rule
            for regra in app.url_map.iter_rules()
            if metodo in regra.methods and regra.rule.startswith(("/api", "/"))
        }

    def test_papel_app_invalido_levanta_erro(self):
        with self.assertRaises(ValueError):
            criar_app(papel_app="fiscal")

    def test_papel_none_registra_rotas_de_coletor_e_dashboard(self):
        app = criar_app(papel_app=None)
        rotas = self._rotas(app, "GET")
        self.assertIn("/api/zonas/<int:zona_id>", rotas)  # exclusiva do coletor
        self.assertIn("/api/analises", rotas)  # exclusiva do dashboard
        self.assertIn("/api/historico-leituras", rotas)  # comum

    def test_papel_coletor_nao_registra_rotas_de_analise(self):
        app = criar_app(papel_app="coletor")
        rotas_get = self._rotas(app, "GET")
        rotas_post = self._rotas(app, "POST")
        self.assertIn("/api/zonas/<int:zona_id>", rotas_get)
        self.assertIn("/api/zonas/<int:zona_id>/calcular", rotas_post)
        self.assertNotIn("/api/analises", rotas_get)
        self.assertNotIn("/api/analises/painel-executivo", rotas_get)
        # rotas comuns continuam presentes
        self.assertIn("/api/historico-leituras", rotas_get)
        self.assertIn("/api/zonas", rotas_get)
        rotas_put = self._rotas(app, "PUT")
        self.assertIn("/api/zonas/<int:zona_id>/controle", rotas_put)
        pagina = cliente_autenticado(app).get("/").get_data(as_text=True)
        self.assertIn('id="campos-entrada-dashboard"', pagina)
        self.assertNotIn("Visualização somente leitura", pagina)
        self.assertIn('data-aba="operacao"', pagina)
        self.assertIn('id="campos-entrada"', pagina)
        self.assertIn('id="operacao-equipamentos"', pagina)
        self.assertIn("Comandos coletivos da zona", pagina)

    def test_papel_dashboard_so_tem_rotas_de_leitura(self):
        app = criar_app(papel_app="dashboard")
        rotas_get = self._rotas(app, "GET")
        rotas_post = self._rotas(app, "POST")

        self.assertIn("/api/analises", rotas_get)
        self.assertIn("/api/analises/painel-executivo", rotas_get)
        self.assertIn("/api/historico-leituras", rotas_get)  # comum
        self.assertIn("/api/zonas", rotas_get)  # comum, so listagem (GET)
        self.assertIn("/api/operacao/status", rotas_get)
        self.assertIn("/api/zonas/<int:zona_id>/historico", rotas_get)

        # nada que fale Modbus, calcule ou grave
        self.assertNotIn("/api/zonas/<int:zona_id>/calcular", rotas_post)
        self.assertNotIn("/api/zonas/calcular-ativas", rotas_post)
        self.assertNotIn("/api/configuracoes", rotas_post)
        self.assertNotIn("/api/backup-banco", rotas_post)
        self.assertNotIn("/api/zonas", rotas_post)  # criar zona e do coletor
        self.assertNotIn(
            "/api/zonas/<int:zona_id>/controle", self._rotas(app, "PUT")
        )

        pagina = cliente_autenticado(app).get("/").get_data(as_text=True)
        self.assertIn('data-aba="principal"', pagina)
        self.assertNotIn('data-aba="operacao"', pagina)
        self.assertIn('id="campos-entrada-dashboard"', pagina)


class TestOrganizacaoDasAbas(unittest.TestCase):
    """Verifica a visibilidade das abas por papel e os campos essenciais."""

    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path_original = db.DB_PATH
        db.DB_PATH = os.path.join(self.tempdir.name, "historico.db")

    def tearDown(self):
        db.DB_PATH = self.db_path_original
        self.tempdir.cleanup()

    def test_abas_administrativas_aparecem_somente_no_coletor(self):
        pagina_coletor = cliente_autenticado(criar_app(papel_app="coletor")).get("/").get_data(as_text=True)
        self.assertIn('data-aba="sistema"', pagina_coletor)
        self.assertIn('data-aba="configuracoes"', pagina_coletor)
        self.assertIn('data-aba="zonas"', pagina_coletor)

        pagina_dashboard = cliente_autenticado(criar_app(papel_app="dashboard")).get("/").get_data(as_text=True)
        self.assertNotIn('data-aba="sistema"', pagina_dashboard)
        self.assertNotIn('data-aba="configuracoes"', pagina_dashboard)
        self.assertNotIn('data-aba="zonas"', pagina_dashboard)

    def test_campos_tecnicos_estao_na_aba_sistema(self):
        pagina = cliente_autenticado(criar_app(papel_app="coletor")).get("/").get_data(as_text=True)
        inicio_sistema = pagina.index('id="aba-sistema"')
        fim_sistema = pagina.index('id="aba-zonas"')
        trecho_sistema = pagina[inicio_sistema:fim_sistema]

        for campo_id in (
            "cfg-zonas-simulado",
            "cfg-intervalo-leitura",
            "cfg-intervalo-gravacao",
            "cfg-ponto-orvalho",
            "cfg-umidade-relativa",
            "cfg-altitude",
            "cfg-limite-umidade-nebulizador",
            "cfg-smtp-host",
            "cfg-smtp-porta",
            "cfg-smtp-usuario",
            "cfg-smtp-senha",
            "btn-backup-banco",
        ):
            with self.subTest(campo=campo_id):
                self.assertIn(f'id="{campo_id}"', trecho_sistema)

        inicio_config = pagina.index('id="aba-configuracoes"')
        trecho_config = pagina[inicio_config:inicio_sistema]
        self.assertIn('id="cfg-status-minimo-email"', trecho_config)

    def test_nenhum_id_duplicado_na_pagina_renderizada(self):
        # IDs duplicados tornam o comportamento de `getElementById`
        # ambiguo e quebram a associacao entre controles e rotulos.
        pagina = cliente_autenticado(criar_app(papel_app=None)).get("/").get_data(as_text=True)
        ids = re.findall(r'\bid="([^"]+)"', pagina)
        duplicados = sorted({item for item in ids if ids.count(item) > 1})
        self.assertEqual([], duplicados, f"IDs duplicados no HTML: {duplicados}")

    def test_app_dashboard_nao_importa_modulos_de_modbus(self):
        """Nao basta a rota nao existir: um processo de dashboard genuino
        nao pode nem ter `modbus_client`/`ZonaService` carregados na
        memoria. Roda num subprocesso Python limpo para garantir que
        nenhum teste anterior ja tenha importado esses modulos antes
        (o que mascararia um resultado falso-positivo)."""
        import subprocess

        codigo = (
            "import sys; "
            "from app.app_factory import criar_app; "
            "criar_app(papel_app='dashboard'); "
            "proibidos = ['app.modbus_client', "
            "'app.zona_service', 'app.coletor.estado']; "
            "carregados = [m for m in proibidos if m in sys.modules]; "
            "print(','.join(carregados))"
        )
        resultado = subprocess.run(
            [sys.executable, "-c", codigo],
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual("", resultado.stdout.strip(), resultado.stderr)


class TestColetorEDashboardCompartilhamOMesmoBanco(unittest.TestCase):
    """Coletor e dashboard compartilham dados somente pelo banco SQLite."""

    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path_original = db.DB_PATH
        db.DB_PATH = os.path.join(self.tempdir.name, "historico.db")
        db.iniciar_banco()

        config = AppConfig(
            debug=False, host="127.0.0.1", port=0, threaded=False, max_content_length=1_000_000
        )
        self.coletor = cliente_autenticado(criar_app(papel_app="coletor", config=config))
        self.dashboard = cliente_autenticado(criar_app(papel_app="dashboard", config=config))

    def tearDown(self):
        db.DB_PATH = self.db_path_original
        self.tempdir.cleanup()

    def test_zona_criada_pelo_coletor_aparece_para_o_dashboard(self):
        resposta = self.coletor.post(
            "/api/zonas", json={"nome": "Aviário 1", "especie": "frangos", "indice": "ITU"}
        )
        self.assertEqual(201, resposta.status_code)

        lista = self.dashboard.get("/api/zonas")
        self.assertEqual(1, len(lista.json))
        self.assertEqual("Aviário 1", lista.json[0]["nome"])

    def test_calculo_do_coletor_aparece_no_painel_executivo_do_dashboard(self):
        zona_id = self.coletor.post(
            "/api/zonas", json={"nome": "Aviário 1", "especie": "frangos", "indice": "ITU"}
        ).json["id"]
        self.coletor.post(
            f"/api/zonas/{zona_id}/equipamentos",
            json={
                "tipo": "ventilador",
                "nome": "VENT-1",
                "modo_conexao": "tcp",
                "host": "10.0.0.2",
                "tipo_registrador": "coil",
                "endereco_registrador": 0,
            },
        )
        self.coletor.post(
            "/api/configuracoes", json={"habilitarEquipamentos": True}
        )
        self.coletor.put(
            f"/api/zonas/{zona_id}/controle",
            json={"modo": "manual", "acionamento_habilitado": True},
        )

        resposta_calculo = self.coletor.post(
            f"/api/zonas/{zona_id}/calcular", json={"entradas": {"tbs": 38, "tbu": 30}}
        )
        self.assertEqual(200, resposta_calculo.status_code)

        resposta_painel = self.dashboard.get("/api/analises/painel-executivo")
        self.assertEqual(200, resposta_painel.status_code)
        [painel] = resposta_painel.json
        self.assertEqual(zona_id, painel["zona_id"])
        self.assertEqual(resposta_calculo.json["status"], painel["status_atual"])
        # O estado do ventilador foi decidido pelo coletor (em memoria, no
        # processo dele) mas chegou ao dashboard so pela tabela
        # `estado_equipamentos` -- nenhum estado em memoria e compartilhado
        # entre os dois clientes/apps.
        self.assertEqual(1, painel["equipamentos_ligados"]["ventiladores_ligados"])

    def test_dashboard_nao_consegue_criar_nem_calcular_zona(self):
        criar = self.dashboard.post(
            "/api/zonas", json={"nome": "X", "especie": "frangos", "indice": "ITU"}
        )
        self.assertEqual(405, criar.status_code)

        calcular = self.dashboard.post("/api/zonas/1/calcular", json={})
        self.assertEqual(404, calcular.status_code)


if __name__ == "__main__":
    unittest.main()
