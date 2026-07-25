# -*- coding: utf-8 -*-
"""Contratos arquiteturais dos processos ICT e coletor."""

import os
import subprocess
import sys
import tempfile
import unittest
from html.parser import HTMLParser
from unittest.mock import patch

from app import database as db
from app.app_factory import (
    AppConfig,
    criar_app_coletor,
    criar_app_ict,
)
from tests.auth_test_utils import cliente_autenticado


def _rotas(app) -> set[str]:
    return {regra.rule for regra in app.url_map.iter_rules()}


class _IdsHTML(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = []

    def handle_starttag(self, _tag, attrs):
        atributos = dict(attrs)
        if atributos.get("id"):
            self.ids.append(atributos["id"])


class TestFabricasExplicitas(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path_original = db.DB_PATH
        db.DB_PATH = os.path.join(self.tempdir.name, "historico.db")

    def tearDown(self):
        db.DB_PATH = self.db_path_original
        self.tempdir.cleanup()

    def test_config_recusa_processo_desconhecido(self):
        with self.assertRaises(ValueError):
            AppConfig.from_env("dashboard")

    def test_ict_contem_todas_as_apis_publicas(self):
        rotas = _rotas(criar_app_ict())
        esperadas = {
            "/",
            "/login",
            "/api/analises",
            "/api/historico-leituras",
            "/api/configuracoes",
            "/api/zonas",
            "/api/zonas/<int:zona_id>/calcular",
            "/api/zonas/<int:zona_id>/controle",
            "/api/zonas/<int:zona_id>/comando",
            "/api/dados-entrada/gerar",
        }
        self.assertTrue(esperadas.issubset(rotas))
        self.assertFalse(any(rota.startswith("/api/interno/") for rota in rotas))
        self.assertNotIn("/health", rotas)

    def test_coletor_expoe_somente_health_e_api_interna(self):
        rotas = _rotas(criar_app_coletor())
        self.assertEqual(
            {
                "/static/<path:filename>",
                "/health",
                "/api/interno/zonas/<int:zona_id>/calcular",
                "/api/interno/zonas/<int:zona_id>/controle",
                "/api/interno/zonas/<int:zona_id>/comando",
                (
                    "/api/interno/zonas/<int:zona_id>/equipamentos/"
                    "<int:equipamento_id>/testar-conexao"
                ),
            },
            rotas,
        )

    def test_coletor_exige_token_em_toda_api_interna(self):
        cliente = criar_app_coletor().test_client()
        chamadas = (
            ("post", "/api/interno/zonas/1/calcular"),
            ("put", "/api/interno/zonas/1/controle"),
            ("post", "/api/interno/zonas/1/comando"),
            (
                "post",
                "/api/interno/zonas/1/equipamentos/1/testar-conexao",
            ),
        )
        for metodo, caminho in chamadas:
            with self.subTest(caminho=caminho):
                resposta = getattr(cliente, metodo)(caminho, json={})
                self.assertEqual(403, resposta.status_code)

        self.assertEqual(200, cliente.get("/health").status_code)

    def test_ict_nao_importa_codigo_modbus(self):
        raiz = os.path.dirname(os.path.dirname(__file__))
        codigo = (
            "import sys; "
            "from app.app_factory import criar_app_ict; "
            "criar_app_ict(); "
            "proibidos=['app.modbus_client','app.zona_service','app.coletor.estado']; "
            "print([nome for nome in proibidos if nome in sys.modules])"
        )
        ambiente = dict(os.environ)
        ambiente.pop("DATABASE_URL", None)
        resultado = subprocess.run(
            [sys.executable, "-c", codigo],
            cwd=raiz,
            env=ambiente,
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertEqual("[]", resultado.stdout.strip())


class TestAbasPorPerfil(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path_original = db.DB_PATH
        db.DB_PATH = os.path.join(self.tempdir.name, "historico.db")
        self.app = criar_app_ict()

    def tearDown(self):
        db.DB_PATH = self.db_path_original
        self.tempdir.cleanup()

    def _pagina(self, perfil):
        return cliente_autenticado(self.app, perfil=perfil).get("/").get_data(as_text=True)

    def test_administrador_ve_todas_as_abas(self):
        pagina = self._pagina("administrador")
        for aba in (
            "principal",
            "operacao",
            "analises",
            "historico",
            "zonas",
            "configuracoes",
            "sistema",
            "dados-entrada",
        ):
            self.assertIn(f'data-aba="{aba}"', pagina)

    def test_operador_ve_somente_dashboard_e_operacao(self):
        pagina = self._pagina("operador")
        self.assertIn('data-aba="principal"', pagina)
        self.assertIn('data-aba="operacao"', pagina)
        for aba in ("analises", "historico", "zonas", "configuracoes", "sistema"):
            self.assertNotIn(f'data-aba="{aba}"', pagina)

    def test_pagina_nao_possui_ids_duplicados(self):
        parser = _IdsHTML()
        parser.feed(self._pagina("administrador"))
        duplicados = {valor for valor in parser.ids if parser.ids.count(valor) > 1}
        self.assertEqual(set(), duplicados)

    def test_campos_tecnicos_permanecem_na_aba_sistema(self):
        pagina = self._pagina("administrador")
        inicio = pagina.index('id="aba-sistema"')
        fim = pagina.index('id="aba-zonas"')
        sistema = pagina[inicio:fim]
        for campo in (
            "cfg-zonas-simulado",
            "cfg-smtp-host",
            "cfg-smtp-porta",
            "cfg-altitude",
            "cfg-limite-umidade-nebulizador",
        ):
            self.assertIn(f'id="{campo}"', sistema)


if __name__ == "__main__":
    unittest.main()
