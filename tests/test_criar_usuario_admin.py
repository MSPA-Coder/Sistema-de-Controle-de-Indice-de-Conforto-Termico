# -*- coding: utf-8 -*-
"""
test_criar_usuario_admin.py
==============================
Cobre `criar_usuario_admin.py` -- o script que quebra o ciclo "ninguém
consegue logar numa instalação nova porque /usuarios exige estar logado
como administrador, e não existe nenhum administrador ainda" (ver o
docstring do próprio script)."""

from __future__ import annotations

import io
import os
import sys
import tempfile
import unittest

import criar_usuario_admin as script
from app import database as db


class TestCriarUsuarioAdmin(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path_original = db.DB_PATH
        db.DB_PATH = os.path.join(self.tempdir.name, "historico.db")
        self.argv_original = sys.argv
        self.stdin_original = sys.stdin

    def tearDown(self):
        db.DB_PATH = self.db_path_original
        sys.argv = self.argv_original
        sys.stdin = self.stdin_original
        self.tempdir.cleanup()

    def _rodar(self, *args, entrada_stdin: str = ""):
        sys.argv = ["criar_usuario_admin.py", *args]
        sys.stdin = io.StringIO(entrada_stdin)
        return script.main()

    def test_cria_primeiro_administrador_sem_pedir_confirmacao(self):
        codigo = self._rodar("--nome", "Ana Admin", "--login", "ana", "--senha", "senha-forte-123")
        self.assertEqual(0, codigo)
        criado = db.obter_usuario_por_login("ana")
        self.assertIsNotNone(criado)
        self.assertEqual("administrador", criado["perfil"])

    def test_senha_curta_e_recusada(self):
        codigo = self._rodar("--nome", "Ana", "--login", "ana", "--senha", "123")
        self.assertEqual(1, codigo)
        self.assertIsNone(db.obter_usuario_por_login("ana"))

    def test_login_duplicado_e_recusado(self):
        self._rodar("--nome", "Ana", "--login", "ana", "--senha", "senha-forte-123", "--sim")
        codigo = self._rodar(
            "--nome", "Outra Ana", "--login", "ana", "--senha", "senha-forte-456", "--sim"
        )
        self.assertEqual(1, codigo)
        self.assertEqual(1, len(db.listar_usuarios()))

    def test_segundo_administrador_pede_confirmacao_e_recusa_se_negado(self):
        self._rodar("--nome", "Ana", "--login", "ana", "--senha", "senha-forte-123")
        codigo = self._rodar(
            "--nome", "Beto", "--login", "beto", "--senha", "senha-forte-456",
            entrada_stdin="n\n",
        )
        self.assertEqual(1, codigo)
        self.assertEqual(1, len(db.listar_usuarios()))

    def test_segundo_administrador_e_criado_se_confirmado(self):
        self._rodar("--nome", "Ana", "--login", "ana", "--senha", "senha-forte-123")
        codigo = self._rodar(
            "--nome", "Beto", "--login", "beto", "--senha", "senha-forte-456",
            entrada_stdin="s\n",
        )
        self.assertEqual(0, codigo)
        self.assertEqual(2, len(db.listar_usuarios()))

    def test_flag_sim_pula_a_confirmacao(self):
        self._rodar("--nome", "Ana", "--login", "ana", "--senha", "senha-forte-123")
        codigo = self._rodar(
            "--nome", "Beto", "--login", "beto", "--senha", "senha-forte-456", "--sim"
        )
        self.assertEqual(0, codigo)
        self.assertEqual(2, len(db.listar_usuarios()))


if __name__ == "__main__":
    unittest.main()
