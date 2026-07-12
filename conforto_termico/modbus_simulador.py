# -*- coding: utf-8 -*-
"""
modbus_simulador.py
=====================
Simula leitura/escrita/teste de conexao Modbus para as Zonas, SEM nenhuma
comunicacao de rede real. Existe para permitir testar e demonstrar o fluxo
completo de uma zona (ler sensores, calcular o indice, acionar
ventilador/nebulizador) antes de haver hardware Modbus de verdade
conectado -- ou simplesmente para ambientes de desenvolvimento/demonstracao.

Deliberadamente "nada sofisticado": reaproveita a MESMA logica de geracao
de valores plausiveis e resfriamento gradual ja usada pelo sensor simulado
da aba Principal (`services.SensorSimuladoService` /
`services.GeradorLeituraAleatoria` / `services.EstrategiaResfriamento`),
apenas com um estado independente por zona -- e o "modo automatico" de
hoje, so que aplicado a cada zona em vez de a uma unica estacao.

Uma zona em modo simulado usa esta classe no lugar de
`modbus_client.ler_valor` / `escrever_valor` / `testar_conexao` (ver
`ZonaService._em_modo_simulado`).
"""

from __future__ import annotations

import random
import threading
import time
from typing import Callable

from . import thermal_indices as ti
from .services import SensorSimuladoService


class SimuladorModbusZonas:
    """Gera leituras simuladas plausiveis por zona e sempre "sucede" ao
    simular escrita em atuador ou teste de conexao."""

    def __init__(
        self,
        obter_zona: Callable[[int], dict | None],
        obter_resfriamento_ativo: Callable[[int], bool],
        ttl_cache_segundos: float = 2.0,
    ):
        self._obter_zona = obter_zona
        self._obter_resfriamento_ativo = obter_resfriamento_ativo
        self._ttl = ttl_cache_segundos
        # Um SensorSimuladoService por zona: cada zona tem seu proprio
        # estado de "ultima leitura" para o resfriamento gradual (5% por
        # ciclo ate voltar ao Conforto) funcionar de forma independente
        # entre zonas, exatamente como o Resfriamento ja funciona por zona
        # em ZonaService.
        self._geradores: dict[int, SensorSimuladoService] = {}
        self._cache_leitura: dict[int, tuple[float, dict[str, float]]] = {}
        self._lock = threading.Lock()

    def _gerador_da_zona(self, zona_id: int) -> SensorSimuladoService:
        with self._lock:
            if zona_id not in self._geradores:
                self._geradores[zona_id] = SensorSimuladoService()
            return self._geradores[zona_id]

    def registrar_calculo(
        self, zona_id: int, especie: str, indice: str, entradas: dict, valor: float, status: str
    ) -> None:
        """Deve ser chamado apos cada calculo bem-sucedido da zona (ver
        ZonaService.calcular), para que a proxima leitura simulada saiba
        se deve reduzir gradualmente a carga termica (equipamento ligado)
        ou sortear um novo valor aleatorio (equipamento desligado)."""
        self._gerador_da_zona(zona_id).registrar_calculo(especie, indice, entradas, valor, status)
        with self._lock:
            # Forca a proxima leitura a gerar um conjunto novo em vez de
            # reusar o cache desta leitura que acabou de ser processada.
            self._cache_leitura.pop(zona_id, None)

    def _entradas_da_zona(self, zona: dict) -> dict[str, float]:
        zona_id = zona["id"]
        agora = time.monotonic()
        with self._lock:
            em_cache = self._cache_leitura.get(zona_id)
        if em_cache is not None and (agora - em_cache[0]) < self._ttl:
            return em_cache[1]

        ativo = bool(self._obter_resfriamento_ativo(zona_id))
        entradas = self._gerador_da_zona(zona_id).gerar(zona["especie"], zona["indice"], ativo)
        with self._lock:
            self._cache_leitura[zona_id] = (agora, entradas)
        return entradas

    def ler_valor(self, equipamento: dict) -> float | None:
        campo = equipamento.get("campo_medido")
        zona_id = equipamento.get("zona_id")
        if not campo or not zona_id:
            return None

        zona = self._obter_zona(zona_id)
        if not zona:
            return None

        entradas = self._entradas_da_zona(zona)
        valor_base = entradas.get(campo)
        if valor_base is None:
            return None

        # Jitter pequeno por sensor: sem isso, todo sensor do mesmo campo
        # numa zona leria exatamente o mesmo "valor verdadeiro" simulado, o
        # que tornaria a MEDIA entre sensores um teste trivial (todos os
        # valores identicos). O jitter imita a variacao natural entre
        # sensores fisicos reais medindo o mesmo ambiente.
        valor = valor_base + random.uniform(-0.4, 0.4)
        if campo in ti.RANGE_VALIDACAO:
            minimo, maximo = ti.RANGE_VALIDACAO[campo]
            valor = min(maximo, max(minimo, valor))
        return round(valor, 2)

    def escrever_valor(self, equipamento: dict, ligar: bool) -> bool:  # noqa: ARG002
        return True

    def testar_conexao(self, equipamento: dict) -> bool:  # noqa: ARG002
        return True
