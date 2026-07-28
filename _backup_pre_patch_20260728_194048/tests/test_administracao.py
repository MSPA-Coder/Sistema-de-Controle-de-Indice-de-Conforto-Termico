# -*- coding: utf-8 -*-
"""
test_administracao.py
========================
Cobre a travessia HTTP real entre ICT e coletor para teste de conexão e
ações da aba Operação.

Tambem cobre `auth.obter_ou_criar_token_interno` isoladamente (geracao,
persistencia, precedencia da variavel de ambiente) e a rejeicao da rota
interna sem token valido.
"""

import os
import tempfile
import threading
import unittest

from werkzeug.serving import make_server

from app import auth
from app import database as db
from app.app_factory import AppConfig, criar_app_coletor, criar_app_ict
from tests.auth_test_utils import cliente_autenticado


class _ServidorEmThread:
    """Sobe um app Flask de verdade numa porta livre do SO, numa thread
    separada -- usado so aqui, para testar a travessia HTTP real entre
    coletor e "outra parte" sem precisar de dois processos de verdade."""

    def __init__(self, app):
        self._servidor = make_server("127.0.0.1", 0, app)
        self.porta = self._servidor.server_port
        self._thread = threading.Thread(target=self._servidor.serve_forever, daemon=True)

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._servidor.shutdown()
        self._thread.join(timeout=3)


class TestTokenInterno(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path_original = db.DB_PATH
        db.DB_PATH = os.path.join(self.tempdir.name, "historico.db")
        self.token_ambiente_original = os.environ.pop("CONFORTO_INTERNO_TOKEN", None)

    def tearDown(self):
        db.DB_PATH = self.db_path_original
        self.tempdir.cleanup()
        if self.token_ambiente_original is not None:
            os.environ["CONFORTO_INTERNO_TOKEN"] = self.token_ambiente_original

    def test_token_e_gerado_e_persistido_entre_chamadas(self):
        primeiro = auth.obter_ou_criar_token_interno()
        segundo = auth.obter_ou_criar_token_interno()
        self.assertEqual(primeiro, segundo)
        self.assertGreaterEqual(len(primeiro), 32)

    def test_variavel_de_ambiente_tem_precedencia_sobre_arquivo_persistido(self):
        auth.obter_ou_criar_token_interno()  # garante que um arquivo já existe
        os.environ["CONFORTO_INTERNO_TOKEN"] = "token-definido-a-mao"
        self.assertEqual("token-definido-a-mao", auth.obter_ou_criar_token_interno())


class TestProxyTesteDeConexao(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path_original = db.DB_PATH
        db.DB_PATH = os.path.join(self.tempdir.name, "historico.db")
        db.iniciar_banco()

        config = AppConfig(
            debug=False, host="127.0.0.1", port=0, threaded=True, max_content_length=1_000_000
        )
        self.app_coletor = criar_app_coletor(config)
        self.app_ict = criar_app_ict(config)
        self.ict = cliente_autenticado(self.app_ict)

        self.coletor = self.app_coletor.test_client()
        zona_id = self.ict.post(
            "/api/zonas", json={"nome": "Aviário 1", "especie": "frangos", "indice": "ITU"}
        ).json["id"]
        equipamento = self.ict.post(
            f"/api/zonas/{zona_id}/equipamentos",
            json={
                "tipo": "ventilador",
                "nome": "VENT-1",
                "modo_conexao": "tcp",
                "host": "10.0.0.2",
                "tipo_registrador": "coil",
                "endereco_registrador": 0,
            },
        ).json
        self.zona_id = zona_id
        self.equipamento_id = equipamento["id"]

        self.coletor_url_original = os.environ.get("COLETOR_URL")

    def tearDown(self):
        db.DB_PATH = self.db_path_original
        self.tempdir.cleanup()
        if self.coletor_url_original is None:
            os.environ.pop("COLETOR_URL", None)
        else:
            os.environ["COLETOR_URL"] = self.coletor_url_original

    def test_rota_interna_rejeita_chamada_sem_token(self):
        resposta = self.coletor.post(
            f"/api/interno/zonas/{self.zona_id}/equipamentos/{self.equipamento_id}/testar-conexao"
        )
        self.assertEqual(403, resposta.status_code)

    def test_rota_interna_aceita_token_valido(self):
        token = auth.obter_ou_criar_token_interno()
        resposta = self.coletor.post(
            f"/api/interno/zonas/{self.zona_id}/equipamentos/{self.equipamento_id}/testar-conexao",
            headers={"X-Interno-Token": token},
        )
        self.assertEqual(200, resposta.status_code)
        self.assertIn("conectado", resposta.json)

    def test_proxy_http_real_entre_ict_e_coletor(self):
        with _ServidorEmThread(self.app_coletor) as servidor:
            os.environ["COLETOR_URL"] = f"http://127.0.0.1:{servidor.porta}"
            resposta = self.ict.post(
                f"/api/zonas/{self.zona_id}/equipamentos/{self.equipamento_id}/testar-conexao"
            )

        self.assertEqual(200, resposta.status_code)
        self.assertIn("conectado", resposta.json)
        self.assertTrue(resposta.json.get("modo_simulado"))  # modoSimuladoZonas comeca ligado

    def test_proxy_http_falha_com_502_quando_coletor_esta_fora(self):
        os.environ["COLETOR_URL"] = "http://127.0.0.1:1"  # ninguem escuta aqui
        resposta = self.ict.post(
            f"/api/zonas/{self.zona_id}/equipamentos/{self.equipamento_id}/testar-conexao"
        )
        self.assertEqual(502, resposta.status_code)
        self.assertIn("erro", resposta.json)

    def test_operacao_publica_do_ict_atravessa_o_coletor(self):
        with _ServidorEmThread(self.app_coletor) as servidor:
            os.environ["COLETOR_URL"] = f"http://127.0.0.1:{servidor.porta}"
            controle = self.ict.put(
                f"/api/zonas/{self.zona_id}/controle",
                json={"modo": "manual", "acionamento_habilitado": False},
            )
            calculo = self.ict.post(
                f"/api/zonas/{self.zona_id}/calcular",
                json={"entradas": {"tbs": 25, "tbu": 20}},
            )

        self.assertEqual(200, controle.status_code)
        self.assertEqual("manual", controle.json["modo"])
        self.assertEqual(200, calculo.status_code)
        self.assertIn("valor", calculo.json)


if __name__ == "__main__":
    unittest.main()
