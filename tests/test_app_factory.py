# -*- coding: utf-8 -*-
"""
test_app_factory.py
=====================
Testa `app_factory.criar_app`: que cada `papel_app` registra exatamente o
conjunto de rotas esperado, que um app "dashboard" nunca importa codigo
relacionado a Modbus (nao so "a rota nao existe" -- o MODULO nao e
carregado), e que dois apps distintos (coletor e dashboard) conseguem
operar sobre o MESMO arquivo SQLite -- o cenario da Fase 1 (mesma
maquina, dois processos), simulado aqui com dois apps Flask no mesmo
interpretador."""

import os
import sys
import tempfile
import unittest

from conforto_termico import database as db
from conforto_termico.app_factory import AppConfig, criar_app


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

    def test_papel_dashboard_so_tem_rotas_de_leitura(self):
        app = criar_app(papel_app="dashboard")
        rotas_get = self._rotas(app, "GET")
        rotas_post = self._rotas(app, "POST")

        self.assertIn("/api/analises", rotas_get)
        self.assertIn("/api/analises/painel-executivo", rotas_get)
        self.assertIn("/api/historico-leituras", rotas_get)  # comum
        self.assertIn("/api/zonas", rotas_get)  # comum, so listagem (GET)

        # nada que fale Modbus, calcule ou grave
        self.assertNotIn("/api/zonas/<int:zona_id>/calcular", rotas_post)
        self.assertNotIn("/api/zonas/calcular-ativas", rotas_post)
        self.assertNotIn("/api/calcular", rotas_post)
        self.assertNotIn("/api/configuracoes", rotas_post)
        self.assertNotIn("/api/backup-banco", rotas_post)
        self.assertNotIn("/api/zonas", rotas_post)  # criar zona e do coletor

    def test_app_dashboard_nao_importa_modulos_de_modbus(self):
        """Nao basta a rota nao existir: um processo de dashboard genuino
        nao pode nem ter `modbus_client`/`ZonaService` carregados na
        memoria. Roda num subprocesso Python limpo para garantir que
        nenhum teste anterior ja tenha importado esses modulos antes
        (o que mascararia um resultado falso-positivo)."""
        import subprocess

        codigo = (
            "import sys; "
            "from conforto_termico.app_factory import criar_app; "
            "criar_app(papel_app='dashboard'); "
            "proibidos = ['conforto_termico.modbus_client', "
            "'conforto_termico.zona_service', 'conforto_termico.coletor.estado']; "
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
    """O cenario central da Fase 1: coletor e dashboard sao dois apps
    Flask (na pratica, dois PROCESSOS) distintos, mas apontam para o MESMO
    arquivo SQLite. Tudo que o coletor grava -- leitura, estado dos
    equipamentos -- precisa aparecer para o dashboard, sem nenhuma
    comunicacao direta entre os dois alem do arquivo."""

    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path_original = db.DB_PATH
        db.DB_PATH = os.path.join(self.tempdir.name, "historico.db")
        db.iniciar_banco()

        config = AppConfig(
            debug=False, host="127.0.0.1", port=0, threaded=False, max_content_length=1_000_000
        )
        self.coletor = criar_app(papel_app="coletor", config=config).test_client()
        self.dashboard = criar_app(papel_app="dashboard", config=config).test_client()

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
