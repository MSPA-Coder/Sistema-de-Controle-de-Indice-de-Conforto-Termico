"""Contrato do `.env` local, que é somente leitura para a aplicação."""

import os
import tempfile
import unittest
from pathlib import Path

from app import env_config
from app.app_factory import criar_app_ict
from tests.auth_test_utils import cliente_autenticado
from tests.postgres_test_utils import TestCasePostgres


class TestEnvConfig(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.caminho_original = env_config.CAMINHO_ENV
        env_config.CAMINHO_ENV = Path(self.tempdir.name) / ".env"
        self.ambiente_original = {chave: os.environ.pop(chave, None) for chave in env_config.CHAVES}

    def tearDown(self):
        env_config.CAMINHO_ENV = self.caminho_original
        self.tempdir.cleanup()
        for chave, valor in self.ambiente_original.items():
            if valor is None:
                os.environ.pop(chave, None)
            else:
                os.environ[chave] = valor

    def test_arquivo_inexistente_e_inerte(self):
        env_config.carregar()
        self.assertNotIn("SMTP_HOST", os.environ)

    def test_carrega_somente_chaves_conhecidas(self):
        env_config.CAMINHO_ENV.write_text(
            "COLETOR_URL=http://127.0.0.1:5001\nPATH=/tentativa\n",
            encoding="utf-8",
        )
        path_original = os.environ.get("PATH")
        env_config.carregar()
        self.assertEqual("http://127.0.0.1:5001", os.environ["COLETOR_URL"])
        self.assertEqual(path_original, os.environ.get("PATH"))

    def test_nao_sobrescreve_variavel_injetada_pelo_processo(self):
        env_config.CAMINHO_ENV.write_text("COLETOR_URL=http://arquivo:5001\n", encoding="utf-8")
        os.environ["COLETOR_URL"] = "http://compose:5000"
        env_config.carregar()
        self.assertEqual("http://compose:5000", os.environ["COLETOR_URL"])


class TestAmbienteNaoEditavelPeloICT(TestCasePostgres):
    def test_ict_nao_expoe_api_para_regravar_env_da_implantacao(self):
        cliente = cliente_autenticado(criar_app_ict())
        self.assertEqual(404, cliente.get("/api/ambiente").status_code)
        self.assertEqual(404, cliente.post("/api/ambiente", json={}).status_code)


if __name__ == "__main__":
    unittest.main()
