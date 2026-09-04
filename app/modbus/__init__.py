"""Fala com os equipamentos: cliente Modbus, simulador e estratégias.

``modbus_client`` é a abstração fina sobre ``pymodbus``; ``modbus_simulador``
substitui o hardware quando ele não está presente; ``estrategias`` guarda as
curvas de geração e resfriamento que o simulador usa.
"""
