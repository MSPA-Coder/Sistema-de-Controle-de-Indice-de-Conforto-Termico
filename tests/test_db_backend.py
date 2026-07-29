import datetime
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from app import db_backend


class TestSelecaoBackend(unittest.TestCase):
    def test_sem_database_url_usa_sqlite_para_testes(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(db_backend.postgres_ativo())

    def test_url_postgresql_ativa_backend_de_producao(self):
        with patch.dict(
            os.environ,
            {"DATABASE_URL": "postgresql+psycopg://user:pass@postgres/app"},
            clear=True,
        ):
            self.assertTrue(db_backend.postgres_ativo())

    def test_url_de_outro_dialeto_nao_cai_silenciosamente_em_sqlite(self):
        with (
            patch.dict(
                os.environ,
                {"DATABASE_URL": "sqlite:////workspace/instance/producao.db"},
                clear=True,
            ),
            self.assertRaisesRegex(RuntimeError, "deve apontar para PostgreSQL"),
        ):
            db_backend.postgres_ativo()

    def test_monta_url_postgresql_a_partir_de_segredo_em_arquivo(self):
        with tempfile.TemporaryDirectory() as diretorio:
            segredo = Path(diretorio) / "senha.txt"
            segredo.write_text("senha-com-#-e-@", encoding="utf-8")
            with patch.dict(
                os.environ,
                {
                    "DB_HOST": "postgres",
                    "DB_PORT": "5432",
                    "DB_NAME": "conforto_termico",
                    "DB_USER": "conforto",
                    "DB_PASSWORD_FILE": str(segredo),
                },
                clear=True,
            ):
                url = db_backend.database_url()

        self.assertTrue(url.startswith("postgresql+psycopg://conforto:"))
        self.assertIn("@postgres:5432/conforto_termico", url)
        self.assertNotIn("senha-com-#-e-@", url)

    def test_configuracao_postgresql_sem_segredo_falha_cedo(self):
        with patch.dict(os.environ, {"DB_HOST": "postgres"}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "DB_PASSWORD_FILE"):
                db_backend.database_url()

    def test_normaliza_json_e_data_para_contrato_compartilhado(self):
        self.assertEqual(
            '{"temperatura": 25}',
            db_backend._normalizar_valor({"temperatura": 25}),
        )
        self.assertEqual(
            "2026-07-25",
            db_backend._normalizar_valor(datetime.date(2026, 7, 25)),
        )

    def test_limpar_cache_descarta_pools_existentes(self):
        engine = Mock()
        db_backend._engines_criados["postgresql://teste"] = engine

        db_backend.limpar_cache_engine()

        engine.dispose.assert_called_once_with()
        self.assertEqual({}, db_backend._engines_criados)


if __name__ == "__main__":
    unittest.main()
