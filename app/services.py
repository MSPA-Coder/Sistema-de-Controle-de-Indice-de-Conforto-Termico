"""
services.py
===========
Estrategias de geracao e resfriamento usadas pelo simulador de sensores.
"""

from __future__ import annotations

import random
import threading
from dataclasses import dataclass

from . import thermal_indices as ti


@dataclass(frozen=True)
class EstadoSensor:
    entradas: dict[str, float]
    valor: float
    status: str


class GeradorLeituraAleatoria:
    """Estrategia de geracao aleatoria para o sensor simulado."""

    def gerar(self, indice: str) -> dict[str, float]:
        if indice == "ITU":
            return {
                "tbs": round(random.uniform(18, 40), 1),
                "tbu": round(random.uniform(12, 30), 1),
            }
        if indice == "ITUV":
            return {
                "tbs": round(random.uniform(18, 40), 1),
                "tbu": round(random.uniform(12, 30), 1),
                "v": round(random.uniform(0.1, 5.0), 2),
            }
        if indice == "IGNU":
            return {
                "tgn": round(random.uniform(18, 45), 1),
                "tpo": round(random.uniform(5, 30), 1),
            }
        raise ti.EntradaInvalidaError("Índice inválido.")


class EstrategiaResfriamento:
    """Estrategia de leitura quando ventilador/nebulizador estao ligados."""

    def __init__(
        self,
        fator_resfriamento: float = 0.95,
        fator_ventilacao: float = 1.05,
    ):
        self._fator_resfriamento = fator_resfriamento
        self._fator_ventilacao = fator_ventilacao

    def aplicar(self, especie: str, indice: str, estado: EstadoSensor) -> EstadoSensor:
        entradas = dict(estado.entradas)
        ajustadas = {
            campo: round(self._valor_ajustado(campo, entradas[campo]), 2 if campo == "v" else 1)
            for campo in ti.CAMPOS_POR_INDICE[indice]
        }
        valor, status = ti.calcular_e_classificar(especie, indice, ajustadas)
        return EstadoSensor(entradas=ajustadas, valor=valor, status=status)

    def _valor_ajustado(self, campo: str, valor: float) -> float:
        minimo, maximo = ti.RANGE_VALIDACAO[campo]
        if campo == "v":
            ajustado = valor * self._fator_ventilacao
        elif valor >= 0:
            ajustado = valor * self._fator_resfriamento
        else:
            ajustado = valor / self._fator_resfriamento
        return max(minimo, min(maximo, ajustado))


class SensorSimuladoService:
    """Controla o estado do sensor simulado.

    Padrao aplicado: Strategy. O servico escolhe entre geracao aleatoria e
    estrategia de resfriamento sem expor essa decisao as rotas.
    """

    def __init__(
        self,
        gerador_aleatorio: GeradorLeituraAleatoria | None = None,
        estrategia_resfriamento: EstrategiaResfriamento | None = None,
    ):
        self._gerador_aleatorio = gerador_aleatorio or GeradorLeituraAleatoria()
        self._estrategia_resfriamento = estrategia_resfriamento or EstrategiaResfriamento()
        self._estados: dict[tuple[str, str], EstadoSensor] = {}
        self._lock = threading.Lock()

    def registrar_calculo(
        self,
        especie: str,
        indice: str,
        entradas: dict,
        valor: float,
        status: str,
    ) -> None:
        estado = EstadoSensor(entradas=dict(entradas), valor=valor, status=status)
        with self._lock:
            self._estados[(especie, indice)] = estado

    def gerar(
        self,
        especie: str,
        indice: str,
        resfriamento_ativo: bool,
    ) -> dict[str, float]:
        if resfriamento_ativo:
            leitura_resfriada = self._gerar_com_resfriamento(especie, indice)
            if leitura_resfriada is not None:
                return leitura_resfriada
        return self._gerador_aleatorio.gerar(indice)

    def _gerar_com_resfriamento(
        self,
        especie: str,
        indice: str,
    ) -> dict[str, float] | None:
        chave = (especie, indice)
        with self._lock:
            estado = self._estados.get(chave)

        if not estado:
            return None

        novo_estado = self._estrategia_resfriamento.aplicar(especie, indice, estado)

        with self._lock:
            self._estados[chave] = novo_estado

        return dict(novo_estado.entradas)
