"""Contrato do smoke test PostgreSQL para instalações novas."""

from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from scripts import verificar_postgres


class VerificarPostgresTests(unittest.TestCase):
    def test_aceita_banco_recém_migrado_sem_dados_operacionais(self):
        conexao = Mock()
        conexao.execute.return_value.lastrowid = 1
        contexto = Mock()
        contexto.__enter__ = Mock(return_value=conexao)
        contexto.__exit__ = Mock(return_value=False)

        with (
            patch.object(verificar_postgres.db_backend, "postgres_ativo", return_value=True),
            patch.object(verificar_postgres.database, "listar_zonas", return_value=[]),
            patch.object(verificar_postgres.database, "listar_usuarios", return_value=[]),
            patch.object(verificar_postgres.database, "obter_painel_zonas", return_value=[]),
            patch.object(verificar_postgres.dados_entrada_db, "listar_execucoes", return_value=[]),
            patch.object(verificar_postgres.database, "_conexao", return_value=contexto),
            patch.object(verificar_postgres.database, "contar_leituras", return_value=0),
        ):
            self.assertEqual(0, verificar_postgres.main())

        conexao.rollback.assert_called_once()
