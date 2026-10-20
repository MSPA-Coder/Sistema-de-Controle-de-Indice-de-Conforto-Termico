"""Respostas do driver, falhas de rede e fechamento de conexão."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.modbus import modbus_client as m


@pytest.fixture
def driver(monkeypatch):
    cliente = Mock()
    cliente.connect.return_value = True
    resposta = SimpleNamespace(isError=lambda: False, registers=[65526], bits=[True])
    for metodo in ("read_input_registers", "read_holding_registers", "read_coils", "write_coil", "write_register"):
        getattr(cliente, metodo).return_value = resposta
    monkeypatch.setattr(m, "PYMODBUS_DISPONIVEL", True)
    monkeypatch.setattr(m, "ModbusTcpClient", Mock(return_value=cliente))
    monkeypatch.setattr(m, "ModbusSerialClient", Mock(return_value=cliente))
    equipamento = {"modo_conexao": "tcp", "host": "sensor.invalid", "nome": "QA",
                   "endereco_registrador": 12, "unidade_id": 7, "fator_escala": 0.1}
    return cliente, equipamento


@pytest.mark.parametrize("registrador", ["holding", "input"])
def test_leitura_temperatura_negativa_escala_e_unidade(driver, registrador):
    cliente, e = driver
    assert m.ler_valor({**e, "tipo_registrador": registrador}) == -1.0
    metodo = cliente.read_input_registers if registrador == "input" else cliente.read_holding_registers
    metodo.assert_called_once_with(12, count=1, device_id=7)
    cliente.close.assert_called_once()


@pytest.mark.parametrize("registrador", ["coil", "holding"])
@pytest.mark.parametrize("ligar", [True, False])
def test_escrita_e_confirmacao_separadas(driver, registrador, ligar):
    cliente, e = driver
    e["tipo_registrador"] = registrador
    resposta = SimpleNamespace(isError=lambda: False, registers=[int(ligar)], bits=[ligar])
    cliente.read_holding_registers.return_value = resposta
    cliente.read_coils.return_value = resposta
    assert m.escrever_valor(e, ligar)
    assert m.ler_estado_atuador(e) is ligar
    if registrador == "coil":
        cliente.write_coil.assert_called_once_with(12, ligar, device_id=7)
    else:
        cliente.write_register.assert_called_once_with(12, int(ligar), device_id=7)
    assert cliente.close.call_count == 2


@pytest.mark.parametrize("operacao,esperado", [(m.ler_valor, None), (m.escrever_valor, False), (m.ler_estado_atuador, None), (m.testar_conexao, False)])
@pytest.mark.parametrize("falha", ["desconectado", "timeout", "protocolo"])
def test_falha_nao_propaga_e_libera_recurso(driver, operacao, esperado, falha):
    cliente, e = driver
    if falha == "desconectado":
        cliente.connect.return_value = False
    elif falha == "timeout":
        cliente.connect.side_effect = TimeoutError("Sem resposta")
    else:
        cliente.connect.side_effect = OSError("Conexão perdida")
    cliente.close.side_effect = OSError("Conexão já fechada")
    args = (e, True) if operacao is m.escrever_valor else (e,)
    assert operacao(*args) is esperado
    cliente.close.assert_called_once()


@pytest.mark.parametrize("registrador", ["coil", "holding"])
@pytest.mark.parametrize("resposta", [SimpleNamespace(isError=lambda: True), SimpleNamespace(isError=lambda: False, bits=[], registers=[])])
def test_resposta_incompleta_nao_confirma_estado(driver, registrador, resposta):
    cliente, e = driver
    cliente.read_coils.return_value = resposta
    cliente.read_holding_registers.return_value = resposta
    assert m.ler_estado_atuador({**e, "tipo_registrador": registrador}) is None


def test_rtu_e_ausencia_de_endereco_ou_driver(driver, monkeypatch):
    cliente, e = driver
    assert m.testar_conexao({**e, "modo_conexao": "rtu", "porta_serial": "/dev/ttyQA", "baud_rate": 19200})
    m.ModbusSerialClient.assert_called_once_with(port="/dev/ttyQA", baudrate=19200, timeout=3)
    assert m.ler_valor({"modo_conexao": "tcp"}) is None
    assert m.escrever_valor({"modo_conexao": "rtu"}, True) is False
    monkeypatch.setattr(m, "PYMODBUS_DISPONIVEL", False)
    assert m.ler_valor(e) is None
    assert m.testar_conexao(e) is False
    assert cliente.close.call_count == 1
