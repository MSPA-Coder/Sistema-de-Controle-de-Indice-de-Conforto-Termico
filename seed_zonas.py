# -*- coding: utf-8 -*-
"""
seed_zonas.py
=============
Script utilitario (nao faz parte do app em si) para popular o banco com 5
zonas de exemplo, cada uma com sensores/ventiladores/nebulizadores
Modbus cadastrados com parametros plausiveis de uma instalacao real.

Uso:
    python seed_zonas.py            # cria as 5 zonas (se ainda nao existirem)
    python seed_zonas.py --forcar   # cria mesmo se ja houver zonas cadastradas

Notas sobre as escolhas de cadastro (para quem for revisar/ajustar depois):

- RTU (serial/RS-485): porta serial no padrao Linux (`/dev/ttyUSB0`), baud
  rate 9600 (padrao mais comum em redes Modbus RTU de sensores de baixo
  custo). Cada equipamento na MESMA porta serial tem um `unidade_id`
  (slave id) DIFERENTE -- e assim que varios dispositivos compartilham o
  mesmo barramento RS-485.
- TCP: IPs de rede local (192.168.1.x), porta 502 (porta padrao do Modbus
  TCP) -- tipico de um gateway Modbus TCP/RTU ou de sensores com modulo
  ESP32/ESP8266 embutido conectados direto na rede local da granja.
- Sensores de temperatura/globo negro/ponto de orvalho: `int16` com fator
  de escala 0.1 -- convencao comum de sensores industriais baratos que
  reportam a leitura como inteiro multiplicado por 10 (permite casas
  decimais e valores negativos sem precisar de ponto flutuante no
  registrador).
- Velocidade do ar: `uint16` com fator de escala 0.01 -- tipico de
  anemometros que reportam em cm/s (nunca negativo).
- Ventiladores/nebulizadores: acionados via `coil` (bit unico de liga/
  desliga) -- o caso mais comum e barato (rele/contator simples), em vez
  de um holding register de velocidade variavel (VFD).
- Duas das cinco zonas tem um sensor REDUNDANTE no mesmo campo (ex.: dois
  sensores de TBS), justamente para exercitar a media entre sensores do
  mesmo campo numa zona -- o motivo original de ZonaService.ler_sensores
  existir.
"""

from __future__ import annotations

import sys

from conforto_termico import database as db

ZONAS = [
    {
        "zona": {"nome": "Aviário 1 - Galpão A", "especie": "frangos", "indice": "ITU"},
        "sensores": [
            {
                "nome": "Sonda TBS/TBU 1 - Bulbo Seco", "modo_conexao": "rtu",
                "porta_serial": "/dev/ttyUSB0", "baud_rate": 9600, "unidade_id": 1,
                "tipo_registrador": "input", "endereco_registrador": 0,
                "tipo_dado": "int16", "fator_escala": 0.1, "campo_medido": "tbs",
            },
            {
                "nome": "Sonda TBS/TBU 1 - Bulbo Úmido", "modo_conexao": "rtu",
                "porta_serial": "/dev/ttyUSB0", "baud_rate": 9600, "unidade_id": 1,
                "tipo_registrador": "input", "endereco_registrador": 1,
                "tipo_dado": "int16", "fator_escala": 0.1, "campo_medido": "tbu",
            },
        ],
        "ventiladores": 3,
        "nebulizadores": 2,
    },
    {
        "zona": {"nome": "Aviário 2 - Galpão B", "especie": "frangos", "indice": "ITUV"},
        "sensores": [
            {
                "nome": "Sensor Temperatura Ambiente 1", "modo_conexao": "tcp",
                "host": "192.168.1.101", "porta": 502, "unidade_id": 1,
                "tipo_registrador": "input", "endereco_registrador": 0,
                "tipo_dado": "int16", "fator_escala": 0.1, "campo_medido": "tbs",
            },
            {
                "nome": "Sensor Bulbo Úmido 1", "modo_conexao": "tcp",
                "host": "192.168.1.101", "porta": 502, "unidade_id": 1,
                "tipo_registrador": "input", "endereco_registrador": 1,
                "tipo_dado": "int16", "fator_escala": 0.1, "campo_medido": "tbu",
            },
            {
                "nome": "Anemômetro 1", "modo_conexao": "tcp",
                "host": "192.168.1.102", "porta": 502, "unidade_id": 1,
                "tipo_registrador": "input", "endereco_registrador": 0,
                "tipo_dado": "uint16", "fator_escala": 0.01, "campo_medido": "v",
            },
        ],
        "ventiladores": 5,
        "nebulizadores": 3,
    },
    {
        "zona": {"nome": "Confinamento Bovino 1", "especie": "bovinos", "indice": "ITU"},
        "sensores": [
            {
                "nome": "Sensor TBS Curral Norte", "modo_conexao": "tcp",
                "host": "192.168.1.110", "porta": 502, "unidade_id": 1,
                "tipo_registrador": "input", "endereco_registrador": 0,
                "tipo_dado": "int16", "fator_escala": 0.1, "campo_medido": "tbs",
            },
            {
                # Segundo sensor de TBS (redundante) -- o curral e grande e
                # tem dois pontos de medicao, cuja media e usada no calculo.
                "nome": "Sensor TBS Curral Sul", "modo_conexao": "tcp",
                "host": "192.168.1.111", "porta": 502, "unidade_id": 1,
                "tipo_registrador": "input", "endereco_registrador": 0,
                "tipo_dado": "int16", "fator_escala": 0.1, "campo_medido": "tbs",
            },
            {
                "nome": "Sensor TBU Curral Norte", "modo_conexao": "tcp",
                "host": "192.168.1.110", "porta": 502, "unidade_id": 1,
                "tipo_registrador": "input", "endereco_registrador": 1,
                "tipo_dado": "int16", "fator_escala": 0.1, "campo_medido": "tbu",
            },
        ],
        "ventiladores": 2,
        "nebulizadores": 2,
    },
    {
        "zona": {"nome": "Maternidade Suínos 1", "especie": "suinos", "indice": "IGNU"},
        "sensores": [
            {
                "nome": "Termômetro de Globo Negro 1", "modo_conexao": "rtu",
                "porta_serial": "/dev/ttyUSB1", "baud_rate": 19200, "unidade_id": 1,
                "tipo_registrador": "holding", "endereco_registrador": 0,
                "tipo_dado": "int16", "fator_escala": 0.1, "campo_medido": "tgn",
            },
            {
                "nome": "Sensor Ponto de Orvalho 1", "modo_conexao": "rtu",
                "porta_serial": "/dev/ttyUSB1", "baud_rate": 19200, "unidade_id": 2,
                "tipo_registrador": "holding", "endereco_registrador": 0,
                "tipo_dado": "int16", "fator_escala": 0.1, "campo_medido": "tpo",
            },
        ],
        "ventiladores": 4,
        "nebulizadores": 3,
    },
    {
        "zona": {"nome": "Creche Suínos 2", "especie": "suinos", "indice": "ITU"},
        "sensores": [
            {
                "nome": "Sensor TBS Creche 2", "modo_conexao": "tcp",
                "host": "192.168.1.120", "porta": 502, "unidade_id": 1,
                "tipo_registrador": "input", "endereco_registrador": 0,
                "tipo_dado": "int16", "fator_escala": 0.1, "campo_medido": "tbs",
            },
            {
                "nome": "Sensor TBU Creche 2 - Baia A", "modo_conexao": "tcp",
                "host": "192.168.1.120", "porta": 502, "unidade_id": 1,
                "tipo_registrador": "input", "endereco_registrador": 1,
                "tipo_dado": "int16", "fator_escala": 0.1, "campo_medido": "tbu",
            },
            {
                # Redundancia no campo TBU desta vez, para variar qual
                # campo tem media entre as zonas de exemplo.
                "nome": "Sensor TBU Creche 2 - Baia B", "modo_conexao": "tcp",
                "host": "192.168.1.121", "porta": 502, "unidade_id": 1,
                "tipo_registrador": "input", "endereco_registrador": 1,
                "tipo_dado": "int16", "fator_escala": 0.1, "campo_medido": "tbu",
            },
        ],
        "ventiladores": 3,
        "nebulizadores": 2,
    },
]


def _criar_ventiladores(zona_id: int, quantidade: int, prefixo_host: str) -> None:
    for i in range(1, quantidade + 1):
        db.criar_equipamento(zona_id, {
            "tipo": "ventilador",
            "nome": f"Ventilador {i}",
            "modo_conexao": "tcp",
            "host": f"{prefixo_host}.{i}",
            "porta": 502,
            "unidade_id": 1,
            "tipo_registrador": "coil",
            "endereco_registrador": i - 1,
        })


def _criar_nebulizadores(zona_id: int, quantidade: int, prefixo_host: str) -> None:
    for i in range(1, quantidade + 1):
        db.criar_equipamento(zona_id, {
            "tipo": "nebulizador",
            "nome": f"Nebulizador {i}",
            "modo_conexao": "tcp",
            "host": f"{prefixo_host}.{i}",
            "porta": 502,
            "unidade_id": 1,
            "tipo_registrador": "coil",
            "endereco_registrador": i - 1,
        })


def semear(forcar: bool = False) -> None:
    db.iniciar_banco()

    if db.listar_zonas() and not forcar:
        print(
            "Já existem zonas cadastradas -- nada foi feito. "
            "Rode com --forcar para adicionar mesmo assim."
        )
        return

    for indice_zona, definicao in enumerate(ZONAS, start=1):
        zona = db.criar_zona(definicao["zona"])
        print(f"Zona criada: #{zona['id']} {zona['nome']} ({zona['especie']}/{zona['indice']})")

        for sensor in definicao["sensores"]:
            db.criar_equipamento(zona["id"], {**sensor, "tipo": "sensor"})
        print(f"  {len(definicao['sensores'])} sensor(es) cadastrado(s)")

        prefixo_ventilador = f"192.168.{10 + indice_zona}.2"
        prefixo_nebulizador = f"192.168.{10 + indice_zona}.3"
        _criar_ventiladores(zona["id"], definicao["ventiladores"], prefixo_ventilador)
        _criar_nebulizadores(zona["id"], definicao["nebulizadores"], prefixo_nebulizador)
        print(
            f"  {definicao['ventiladores']} ventilador(es) e "
            f"{definicao['nebulizadores']} nebulizador(es) cadastrado(s)"
        )

    print("\nConcluído.")


if __name__ == "__main__":
    semear(forcar="--forcar" in sys.argv)
