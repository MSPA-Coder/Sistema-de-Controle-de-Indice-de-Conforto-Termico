# -*- coding: utf-8 -*-
"""
modbus_client.py
================
Abstracao fina sobre a biblioteca `pymodbus` para ler sensores e acionar
atuadores (ventiladores/nebulizadores) de campo conectados via Modbus TCP
ou Modbus RTU (serial, tipico de redes RS-485 com um HAT em Raspberry Pi).

PRINCIPIO DE DESIGN: nenhuma funcao aqui lanca excecao para cima. Se a
biblioteca `pymodbus` nao estiver instalada, se o equipamento nao responder
(sem hardware conectado, cabo desconectado, endereco/porta errados,
timeout), ou se o dispositivo devolver uma excecao Modbus, `ler_valor`
devolve `None` e `escrever_valor` devolve `False`. Isso segue o mesmo
principio ja adotado no resto do projeto para sensores/e-mail/graficos:
uma falha num aspecto de hardware/rede nunca deve derrubar o calculo do
indice como um todo -- ela apenas fica registrada (no log e, no caso dos
sensores, na lista de "falhas" devolvida por ZonaService.ler_sensores).

`pymodbus` e uma dependencia OPCIONAL (ver requirements-modbus.txt): o
resto do app funciona normalmente sem ela instalada -- as zonas cadastradas
simplesmente nao conseguem ler/escrever ate a biblioteca ser instalada no
ambiente onde o servidor roda de fato (ex.: o Raspberry Pi conectado ao
barramento RS-485 real).
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

try:
    from pymodbus.client import ModbusSerialClient, ModbusTcpClient

    PYMODBUS_DISPONIVEL = True
except ImportError:  # pragma: no cover - exercitado apenas sem a lib instalada
    ModbusSerialClient = None  # type: ignore[assignment]
    ModbusTcpClient = None  # type: ignore[assignment]
    PYMODBUS_DISPONIVEL = False


# Complemento de dois: registradores Modbus de 16 bits sao, por natureza do
# protocolo, sempre lidos como inteiros sem sinal (0-65535). Sensores que
# reportam valores negativos (ex.: temperatura abaixo de zero) codificam
# isso via complemento de dois -- o proprio equipamento (ou o fabricante,
# na documentacao) e quem informa se o registrador deve ser interpretado
# como "int16" (com sinal) ou "uint16" (sem sinal).
def _aplicar_sinal(bruto: int, tipo_dado: str) -> int:
    if tipo_dado == "int16" and bruto > 32767:
        return bruto - 65536
    return bruto


def _criar_cliente(equipamento: dict[str, Any]):
    if not PYMODBUS_DISPONIVEL:
        return None
    if equipamento.get("modo_conexao") == "tcp":
        host = equipamento.get("host")
        if not host:
            return None
        porta = int(equipamento.get("porta") or 502)
        return ModbusTcpClient(host, port=porta, timeout=3)

    porta_serial = equipamento.get("porta_serial")
    if not porta_serial:
        return None
    baud_rate = int(equipamento.get("baud_rate") or 9600)
    return ModbusSerialClient(port=porta_serial, baudrate=baud_rate, timeout=3)


def testar_conexao(equipamento: dict[str, Any]) -> bool:
    """Tenta abrir e fechar a conexao, sem ler/escrever nada. Usado pela
    interface para o botao "testar conexao" ao cadastrar um equipamento."""
    if not PYMODBUS_DISPONIVEL:
        return False
    cliente = _criar_cliente(equipamento)
    if cliente is None:
        return False
    try:
        return bool(cliente.connect())
    except Exception:
        logger.exception("Falha ao testar conexao Modbus com %s", equipamento.get("nome"))
        return False
    finally:
        _fechar(cliente)


def _fechar(cliente) -> None:
    try:
        cliente.close()
    except Exception:  # pragma: no cover - defensivo, close() raramente falha
        pass


def ler_valor(equipamento: dict[str, Any]) -> float | None:
    """Le um registrador (holding ou input) e aplica o fator de escala
    configurado. Devolve `None` em qualquer falha -- biblioteca ausente,
    equipamento sem resposta, ou excecao Modbus (ex.: endereco invalido
    naquele dispositivo)."""
    cliente = _criar_cliente(equipamento)
    if cliente is None:
        return None

    try:
        if not cliente.connect():
            return None

        endereco = int(equipamento["endereco_registrador"])
        unidade = int(equipamento.get("unidade_id") or 1)
        tipo_registrador = equipamento.get("tipo_registrador", "holding")

        if tipo_registrador == "input":
            resposta = cliente.read_input_registers(endereco, count=1, device_id=unidade)
        else:
            resposta = cliente.read_holding_registers(endereco, count=1, device_id=unidade)

        if resposta.isError():
            return None

        bruto = _aplicar_sinal(resposta.registers[0], equipamento.get("tipo_dado", "int16"))
        fator = float(equipamento.get("fator_escala") or 1.0)
        return bruto * fator
    except Exception:
        logger.exception("Falha ao ler equipamento Modbus %s", equipamento.get("nome"))
        return None
    finally:
        _fechar(cliente)


def escrever_valor(equipamento: dict[str, Any], ligar: bool) -> bool:
    """Liga/desliga um atuador (ventilador/nebulizador) via coil ou
    holding register. Devolve `False` em qualquer falha."""
    cliente = _criar_cliente(equipamento)
    if cliente is None:
        return False

    try:
        if not cliente.connect():
            return False

        endereco = int(equipamento["endereco_registrador"])
        unidade = int(equipamento.get("unidade_id") or 1)

        if equipamento.get("tipo_registrador") == "coil":
            resposta = cliente.write_coil(endereco, ligar, device_id=unidade)
        else:
            resposta = cliente.write_register(endereco, 1 if ligar else 0, device_id=unidade)

        return not resposta.isError()
    except Exception:
        logger.exception("Falha ao acionar equipamento Modbus %s", equipamento.get("nome"))
        return False
    finally:
        _fechar(cliente)
