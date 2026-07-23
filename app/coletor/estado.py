# -*- coding: utf-8 -*-
"""
coletor/estado.py
===================
Instancia, uma unica vez por processo, os servicos com estado que a malha
de controle usa: leitura/escrita Modbus, calculo do indice, e o estado
ATIVO (ligado/desligado, intensidade) de cada zona.

Modulo separado das rotas (`coletor/rotas.py`) de proposito: e o unico
lugar do pacote `coletor` que cria os objetos "globais" do processo, o que
torna claro, so pelo import, quais partes do sistema dependem de estado em
memoria (e portanto nao podem ser replicadas ingenuamente por um segundo
processo -- ver a nota sobre `estado_equipamentos` em `database.py`)."""

from __future__ import annotations

from .. import database as db
from .. import modbus_client
from ..modbus_simulador import SimuladorModbusZonas
from ..zona_service import ZonaService
from .controle import GerenciadorControleZonas

zona_service = ZonaService(
    obter_zona=db.obter_zona,
    salvar_leitura=db.salvar_leitura,
    obter_configuracoes=db.obter_configuracoes,
    obter_historico=db.obter_historico_por_zona,
    salvar_estado_equipamentos=db.salvar_estado_equipamentos,
    obter_controle_zona=db.obter_controle_zona,
    ler_estado_atuador_real=modbus_client.ler_estado_atuador,
    salvar_leitura_recente=db.salvar_leitura_recente_zona,
)
# `SimuladorModbusZonas` precisa poder perguntar ao proprio zona_service
# qual e o estado de resfriamento atual de uma zona (para decidir se a
# proxima leitura simulada deve reduzir gradualmente ou sortear um valor
# novo) -- por isso e conectado depois da criacao de zona_service, via
# `definir_simulador`, em vez de no construtor.
zona_simulador = SimuladorModbusZonas(
    obter_zona=db.obter_zona,
    obter_resfriamento_ativo=lambda zona_id: zona_service.resfriador_da_zona(zona_id).estado()[
        "ativo"
    ],
)
zona_service.definir_simulador(zona_simulador)
gerenciador_controle = GerenciadorControleZonas(zona_service)
