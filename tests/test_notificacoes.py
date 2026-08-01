"""
test_notificacoes.py
======================
Testa `app/notificacoes.py`: a regra compartilhada de "quando alertar" e
o worker da fila assincrona, isolados de qualquer rede de verdade
(`Email.enviar` e sempre substituido por um dublê nestes testes).
"""

import unittest
from unittest.mock import patch

from app import notificacoes


class TestDeveNotificarEmail(unittest.TestCase):
    def test_nao_notifica_quando_enviar_emails_desligado(self):
        resposta = {"status": "Emergência"}
        config = {"enviarEmails": False, "statusMinimoEmail": "conforto"}
        self.assertFalse(notificacoes.deve_notificar_email(resposta, config))

    def test_notifica_quando_status_atinge_o_piso_configurado(self):
        resposta = {"status": "Perigo"}
        config = {"enviarEmails": True, "statusMinimoEmail": "alerta"}
        self.assertTrue(notificacoes.deve_notificar_email(resposta, config))

    def test_nao_notifica_quando_status_fica_abaixo_do_piso_configurado(self):
        resposta = {"status": "Alerta"}
        config = {"enviarEmails": True, "statusMinimoEmail": "perigo"}
        self.assertFalse(notificacoes.deve_notificar_email(resposta, config))


class TestFilaNotificacoes(unittest.TestCase):
    def setUp(self):
        self.fila = notificacoes.FilaNotificacoes()

    def tearDown(self):
        self.fila.parar()

    def test_worker_processa_item_enfileirado(self):
        with patch("app.notificacoes.Email") as email_falso:
            email_falso.return_value.enviar.return_value = True
            self.fila.iniciar()
            self.fila.enfileirar("destino@fazenda.com.br", "conteudo qualquer", {"host": None})
            # `parar()` enfileira um sentinela DEPOIS do item real e so
            # devolve quando o worker esvaziou a fila -- sincroniza sem
            # precisar de polling manual.
            self.fila.parar(timeout=2)

            email_falso.assert_called_once_with("destino@fazenda.com.br", "conteudo qualquer")
            email_falso.return_value.enviar.assert_called_once_with({"host": None})

    def test_falha_no_envio_nao_derruba_o_worker(self):
        with patch("app.notificacoes.Email") as email_falso:
            email_falso.return_value.enviar.side_effect = RuntimeError("smtp indisponível")
            self.fila.iniciar()
            self.fila.enfileirar("a@fazenda.com.br", "x", {})
            self.fila.enfileirar("b@fazenda.com.br", "y", {})
            self.fila.parar(timeout=2)

        self.assertEqual(2, email_falso.return_value.enviar.call_count)

    def test_parar_sem_ter_iniciado_nao_levanta_erro(self):
        self.fila.parar()  # nao deve levantar excecao


class TestNotificarZonaAutomatico(unittest.TestCase):
    def _resposta(self, status="Emergência"):
        return {
            "zona_id": 1,
            "zona_nome": "Aviário 1",
            "status": status,
            "valor": 90.0,
            "indice": "ITU",
            "entradas": {"tbs": 38.0, "tbu": 30.0},
        }

    def test_enfileira_e_marca_resposta_quando_deve_notificar(self):
        config = {
            "enviarEmails": True,
            "statusMinimoEmail": "alerta",
            "emailDestino": "produtor@fazenda.com.br",
        }
        chamadas = []
        with patch.object(
            notificacoes.fila_notificacoes,
            "enfileirar",
            side_effect=lambda destino, conteudo, smtp_config: chamadas.append(destino),
        ):
            resposta = notificacoes.notificar_zona_automatico(self._resposta(), config)

        self.assertEqual(["produtor@fazenda.com.br"], chamadas)
        self.assertTrue(resposta["email"]["enfileirado"])

    def test_nao_enfileira_quando_status_abaixo_do_piso(self):
        config = {
            "enviarEmails": True,
            "statusMinimoEmail": "perigo",
            "emailDestino": "produtor@fazenda.com.br",
        }
        chamadas = []
        with patch.object(
            notificacoes.fila_notificacoes,
            "enfileirar",
            side_effect=lambda destino, conteudo, smtp_config: chamadas.append(destino),
        ):
            resposta = notificacoes.notificar_zona_automatico(
                self._resposta(status="Alerta"), config
            )

        self.assertEqual([], chamadas)
        self.assertNotIn("email", resposta)


if __name__ == "__main__":
    unittest.main()
