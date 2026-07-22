# -*- coding: utf-8 -*-
"""
test_models.py
===============
Cobre as classes de dominio em models.py que ainda nao tinham um arquivo de
teste dedicado, com foco na validacao de e-mail adicionada como defesa em
profundidade contra injecao de cabecalho SMTP (ver models.Email.enviar).
"""

import os
import unittest
from unittest.mock import patch

from app.models import Email, _email_valido


class TestEmailValido(unittest.TestCase):
    def test_aceita_enderecos_bem_formados(self):
        self.assertTrue(_email_valido("produtor@fazenda.com.br"))
        self.assertTrue(_email_valido("nome.sobrenome@exemplo.com"))

    def test_rejeita_valores_nao_string(self):
        self.assertFalse(_email_valido(None))
        self.assertFalse(_email_valido(123))
        self.assertFalse(_email_valido(["a@b.com"]))

    def test_rejeita_formato_invalido(self):
        self.assertFalse(_email_valido("nao e um email"))
        self.assertFalse(_email_valido("sem-arroba.com"))
        self.assertFalse(_email_valido(""))

    def test_rejeita_quebras_de_linha_usadas_para_injecao_de_cabecalho(self):
        self.assertFalse(_email_valido("vitima@fazenda.com.br\r\nBcc: atacante@evil.com"))
        self.assertFalse(_email_valido("vitima@fazenda.com.br\nX-Injected: 1"))


class TestEmailConteudo(unittest.TestCase):
    def test_conteudo_inclui_dados_usados_no_calculo(self):
        conteudo = Email.montar_conteudo(
            "ITUV",
            29.34,
            "Alerta",
            {"tbs": 30.0, "tbu": 24.0, "v": 1.5},
            {"id": 7, "nome": "Aviário 7"},
        )

        self.assertIn("Zona: Aviário 7 (ID 7)", conteudo)
        self.assertIn("Dados usados no cálculo:", conteudo)
        self.assertIn("Temperatura de Bulbo Seco / Ambiente (tbs): 30.0", conteudo)
        self.assertIn("Temperatura de Bulbo Úmido (tbu): 24.0", conteudo)
        self.assertIn("Velocidade do Ar (v): 1.5 m/s", conteudo)


class TestEmailEnviar(unittest.TestCase):
    def test_sem_smtp_host_configurado_opera_em_modo_simulado(self):
        with patch.dict(os.environ, {}, clear=True):
            email = Email("produtor@fazenda.com.br", "conteudo qualquer")
            enviado = email.enviar()

        self.assertFalse(enviado)
        self.assertFalse(email.informar_envio())

    def test_destino_malformado_nunca_chega_a_montar_mensagem_smtp(self):
        """Mesmo com SMTP_HOST configurado, um destino invalido deve ser
        recusado ANTES de qualquer tentativa de conexao SMTP -- nunca deve
        chegar a instanciar smtplib.SMTP com um cabecalho malformado."""
        variaveis = {
            "SMTP_HOST": "smtp.exemplo.com",
            "SMTP_USER": "sistema@fazenda.com.br",
            "SMTP_PASS": "senha",
        }
        with patch.dict(os.environ, variaveis), patch("smtplib.SMTP") as smtp_mock:
            email = Email("vitima@fazenda.com.br\r\nBcc: atacante@evil.com", "conteudo")
            enviado = email.enviar()

        self.assertFalse(enviado)
        smtp_mock.assert_not_called()

    def test_destino_valido_tenta_enviar_via_smtp(self):
        variaveis = {
            "SMTP_HOST": "smtp.exemplo.com",
            "SMTP_USER": "sistema@fazenda.com.br",
            "SMTP_PASS": "senha",
        }
        with patch.dict(os.environ, variaveis), patch("smtplib.SMTP") as smtp_mock:
            servidor = smtp_mock.return_value.__enter__.return_value
            email = Email("produtor@fazenda.com.br", "conteudo")
            enviado = email.enviar()

        self.assertTrue(enviado)
        self.assertTrue(email.informar_envio())
        servidor.sendmail.assert_called_once()

    def test_smtp_config_explicito_tem_prioridade_sobre_variaveis_de_ambiente(self):
        variaveis = {
            "SMTP_HOST": "smtp-do-ambiente.com",
            "SMTP_USER": "usuario-ambiente",
            "SMTP_PASS": "senha-ambiente",
        }
        smtp_config = {
            "host": "smtp-do-banco.com.br",
            "porta": 465,
            "usuario": "usuario-banco",
            "senha": "senha-banco",
        }
        with patch.dict(os.environ, variaveis), patch("smtplib.SMTP") as smtp_mock:
            servidor = smtp_mock.return_value.__enter__.return_value
            email = Email("produtor@fazenda.com.br", "conteudo")
            enviado = email.enviar(smtp_config)

        self.assertTrue(enviado)
        smtp_mock.assert_called_once_with("smtp-do-banco.com.br", 465, timeout=10)
        servidor.login.assert_called_once_with("usuario-banco", "senha-banco")

    def test_smtp_config_com_campos_vazios_cai_para_variaveis_de_ambiente(self):
        variaveis = {
            "SMTP_HOST": "smtp-do-ambiente.com",
            "SMTP_USER": "usuario-ambiente",
            "SMTP_PASS": "senha-ambiente",
        }
        with patch.dict(os.environ, variaveis), patch("smtplib.SMTP") as smtp_mock:
            email = Email("produtor@fazenda.com.br", "conteudo")
            enviado = email.enviar({"host": "", "porta": None, "usuario": "", "senha": ""})

        self.assertTrue(enviado)
        smtp_mock.assert_called_once_with("smtp-do-ambiente.com", 587, timeout=10)


if __name__ == "__main__":
    unittest.main()
