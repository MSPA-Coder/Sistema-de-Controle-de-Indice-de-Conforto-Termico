"""Núcleo térmico: índices de conforto, orquestração por zona e agregação.

``thermal_indices`` é o cálculo puro (ITU, ITGU, CTR e afins);
``zona_service`` orquestra esse cálculo POR ZONA, lendo sensores e
decidindo acionamento; ``agregacao`` consolida o histórico de leituras em
janelas de 15 minutos e resumos horários.
"""
