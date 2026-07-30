"""Testes do provisionamento de segredos locais para a imagem não-root."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import configurar_segredos


class ConfigurarSegredosTests(unittest.TestCase):
    def test_gravar_atribui_segundo_o_usuario_da_imagem(self):
        with tempfile.TemporaryDirectory() as diretorio:
            caminho = Path(diretorio) / "segredo.txt"

            with patch.object(configurar_segredos.os, "chown") as chown:
                criado = configurar_segredos._gravar(caminho, 12, force=False)

            self.assertTrue(criado)
            self.assertTrue(caminho.read_text(encoding="utf-8"))
            _, uid, gid = chown.call_args.args
            self.assertEqual(configurar_segredos.APP_UID, uid)
            self.assertEqual(configurar_segredos.APP_GID, gid)

    def test_forcar_substitui_um_arquivo_existente(self):
        with tempfile.TemporaryDirectory() as diretorio:
            caminho = Path(diretorio) / "segredo.txt"
            caminho.write_text("valor-antigo", encoding="utf-8")

            with patch.object(configurar_segredos.os, "chown"):
                criado = configurar_segredos._gravar(caminho, 12, force=True)

            self.assertTrue(criado)
            self.assertNotEqual("valor-antigo", caminho.read_text(encoding="utf-8"))
