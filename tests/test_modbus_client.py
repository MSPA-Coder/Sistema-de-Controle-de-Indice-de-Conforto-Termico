# -*- coding: utf-8 -*-
"""
test_modbus_client.py
=======================
Testa a abstracao sobre pymodbus SEM depender de hardware real: substitui
`ModbusTcpClient`/`ModbusSerialClient` por classes falsas que simulam
respostas de sucesso, erro Modbus e excecao de rede.
"""

import unittest
from unittest.mock import patch

from conforto_termico import modbus_client


class _RespostaFalsa:
    def __init__(self, registers=None, erro=False):
        self.registers = registers or []
        self._erro = erro

    def isError(self):
        return self._erro


class _ClienteFalso:
    """Simula um ModbusTcpClient/ModbusSerialClient real."""

    ultima_instancia = None

    def __init__(self, *args, conectar=True, resposta_leitura=None, resposta_escrita=None, **kwargs):
        self.conectar_resultado = conectar
        self.resposta_leitura = resposta_leitura or _RespostaFalsa([300])
        self.resposta_escrita = resposta_escrita or _RespostaFalsa([])
        self.fechado = False
        _ClienteFalso.ultima_instancia = self

    def connect(self):
        return self.conectar_resultado

    def read_holding_registers(self, *args, **kwargs):
        return self.resposta_leitura

    def read_input_registers(self, *args, **kwargs):
        return self.resposta_leitura

    def write_register(self, *args, **kwargs):
        return self.resposta_escrita

    def write_coil(self, *args, **kwargs):
        return self.resposta_escrita

    def close(self):
        self.fechado = True


def _equipamento_tcp(**sobrescritas):
    base = {
        "nome": "Sensor Teste",
        "modo_conexao": "tcp",
        "host": "192.168.0.10",
        "porta": 502,
        "unidade_id": 1,
        "tipo_registrador": "holding",
        "endereco_registrador": 100,
        "tipo_dado": "int16",
        "fator_escala": 1.0,
    }
    base.update(sobrescritas)
    return base


class TestBibliotecaAusente(unittest.TestCase):
    """Sem pymodbus instalado, tudo deve degradar graciosamente (None/False),
    nunca lançar exceção."""

    def setUp(self):
        self._disponivel_original = modbus_client.PYMODBUS_DISPONIVEL
        modbus_client.PYMODBUS_DISPONIVEL = False

    def tearDown(self):
        modbus_client.PYMODBUS_DISPONIVEL = self._disponivel_original

    def test_ler_valor_devolve_none(self):
        self.assertIsNone(modbus_client.ler_valor(_equipamento_tcp()))

    def test_escrever_valor_devolve_false(self):
        self.assertFalse(modbus_client.escrever_valor(_equipamento_tcp(), True))

    def test_testar_conexao_devolve_false(self):
        self.assertFalse(modbus_client.testar_conexao(_equipamento_tcp()))


class TestLeituraComClienteFalso(unittest.TestCase):
    def setUp(self):
        self._disponivel_original = modbus_client.PYMODBUS_DISPONIVEL
        modbus_client.PYMODBUS_DISPONIVEL = True

    def tearDown(self):
        modbus_client.PYMODBUS_DISPONIVEL = self._disponivel_original

    def test_leitura_bem_sucedida_aplica_fator_de_escala(self):
        cliente = _ClienteFalso(resposta_leitura=_RespostaFalsa([300]))
        with patch.object(modbus_client, "ModbusTcpClient", return_value=cliente):
            valor = modbus_client.ler_valor(_equipamento_tcp(fator_escala=0.1))
        self.assertEqual(30.0, valor)
        self.assertTrue(cliente.fechado)

    def test_leitura_input_register(self):
        cliente = _ClienteFalso(resposta_leitura=_RespostaFalsa([250]))
        with patch.object(modbus_client, "ModbusTcpClient", return_value=cliente):
            valor = modbus_client.ler_valor(_equipamento_tcp(tipo_registrador="input", fator_escala=0.1))
        self.assertEqual(25.0, valor)

    def test_valor_negativo_via_complemento_de_dois_int16(self):
        # -50 em complemento de dois (16 bits) = 65486
        cliente = _ClienteFalso(resposta_leitura=_RespostaFalsa([65486]))
        with patch.object(modbus_client, "ModbusTcpClient", return_value=cliente):
            valor = modbus_client.ler_valor(_equipamento_tcp(tipo_dado="int16", fator_escala=1.0))
        self.assertEqual(-50.0, valor)

    def test_uint16_nao_aplica_sinal(self):
        cliente = _ClienteFalso(resposta_leitura=_RespostaFalsa([65486]))
        with patch.object(modbus_client, "ModbusTcpClient", return_value=cliente):
            valor = modbus_client.ler_valor(_equipamento_tcp(tipo_dado="uint16", fator_escala=1.0))
        self.assertEqual(65486.0, valor)

    def test_falha_ao_conectar_devolve_none(self):
        cliente = _ClienteFalso(conectar=False)
        with patch.object(modbus_client, "ModbusTcpClient", return_value=cliente):
            self.assertIsNone(modbus_client.ler_valor(_equipamento_tcp()))

    def test_resposta_de_erro_modbus_devolve_none(self):
        cliente = _ClienteFalso(resposta_leitura=_RespostaFalsa(erro=True))
        with patch.object(modbus_client, "ModbusTcpClient", return_value=cliente):
            self.assertIsNone(modbus_client.ler_valor(_equipamento_tcp()))

    def test_excecao_durante_leitura_devolve_none_sem_propagar(self):
        class ClienteQuebrado(_ClienteFalso):
            def read_holding_registers(self, *a, **k):
                raise RuntimeError("falha de rede simulada")

        with patch.object(modbus_client, "ModbusTcpClient", return_value=ClienteQuebrado()):
            self.assertIsNone(modbus_client.ler_valor(_equipamento_tcp()))

    def test_sem_host_tcp_devolve_none_sem_criar_cliente(self):
        self.assertIsNone(modbus_client.ler_valor(_equipamento_tcp(host="")))

    def test_rtu_sem_porta_serial_devolve_none(self):
        equipamento = {
            "nome": "x", "modo_conexao": "rtu", "porta_serial": "",
            "unidade_id": 1, "tipo_registrador": "holding", "endereco_registrador": 1,
        }
        self.assertIsNone(modbus_client.ler_valor(equipamento))


class TestEscritaComClienteFalso(unittest.TestCase):
    def setUp(self):
        self._disponivel_original = modbus_client.PYMODBUS_DISPONIVEL
        modbus_client.PYMODBUS_DISPONIVEL = True

    def tearDown(self):
        modbus_client.PYMODBUS_DISPONIVEL = self._disponivel_original

    def test_escrita_holding_register_bem_sucedida(self):
        cliente = _ClienteFalso(resposta_escrita=_RespostaFalsa())
        with patch.object(modbus_client, "ModbusTcpClient", return_value=cliente):
            resultado = modbus_client.escrever_valor(_equipamento_tcp(), True)
        self.assertTrue(resultado)

    def test_escrita_coil_bem_sucedida(self):
        cliente = _ClienteFalso(resposta_escrita=_RespostaFalsa())
        with patch.object(modbus_client, "ModbusTcpClient", return_value=cliente):
            resultado = modbus_client.escrever_valor(_equipamento_tcp(tipo_registrador="coil"), False)
        self.assertTrue(resultado)

    def test_escrita_com_erro_modbus_devolve_false(self):
        cliente = _ClienteFalso(resposta_escrita=_RespostaFalsa(erro=True))
        with patch.object(modbus_client, "ModbusTcpClient", return_value=cliente):
            resultado = modbus_client.escrever_valor(_equipamento_tcp(), True)
        self.assertFalse(resultado)

    def test_excecao_durante_escrita_devolve_false_sem_propagar(self):
        class ClienteQuebrado(_ClienteFalso):
            def write_register(self, *a, **k):
                raise RuntimeError("falha de rede simulada")

        with patch.object(modbus_client, "ModbusTcpClient", return_value=ClienteQuebrado()):
            resultado = modbus_client.escrever_valor(_equipamento_tcp(), True)
        self.assertFalse(resultado)


class TestTestarConexao(unittest.TestCase):
    def setUp(self):
        self._disponivel_original = modbus_client.PYMODBUS_DISPONIVEL
        modbus_client.PYMODBUS_DISPONIVEL = True

    def tearDown(self):
        modbus_client.PYMODBUS_DISPONIVEL = self._disponivel_original

    def test_conexao_bem_sucedida(self):
        cliente = _ClienteFalso(conectar=True)
        with patch.object(modbus_client, "ModbusTcpClient", return_value=cliente):
            self.assertTrue(modbus_client.testar_conexao(_equipamento_tcp()))
        self.assertTrue(cliente.fechado)

    def test_conexao_falha(self):
        cliente = _ClienteFalso(conectar=False)
        with patch.object(modbus_client, "ModbusTcpClient", return_value=cliente):
            self.assertFalse(modbus_client.testar_conexao(_equipamento_tcp()))


if __name__ == "__main__":
    unittest.main()
