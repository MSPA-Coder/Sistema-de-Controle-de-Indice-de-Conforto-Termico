"""
services.py
===========
Estrategias de geracao e resfriamento usadas pelo simulador de sensores.
"""

from __future__ import annotations

import random
import threading
from dataclasses import dataclass
from typing import Protocol, cast

from app.termico import thermal_indices as ti


@dataclass(frozen=True)
class EstadoSensor:
    entradas: dict[str, float]
    valor: float
    status: str


class FonteAleatoria(Protocol):
    def uniform(self, a: float, b: float) -> float: ...


class GeradorLeituraAleatoria:
    """Estado sintético conjunto; não representa uma distribuição de campo."""

    def __init__(self, rng: FonteAleatoria | None = None) -> None:
        self._rng = rng if rng is not None else random.Random()

    def gerar(self, indice: str) -> dict[str, float]:
        if indice in ("ITU", "ITUV"):
            tbs = round(self._rng.uniform(18, 40), 1)
            # Depressão limitada evita vapor derivado inválido. A margem de
            # 1 °C também acomoda jitter oposto de até 0,4 °C por sensor.
            entradas = {"tbs": tbs, "tbu": round(tbs - self._rng.uniform(1, 6), 1)}
            if indice == "ITUV":
                entradas["v"] = round(self._rng.uniform(0.5, 5.0), 2)
            return entradas
        if indice == "IGNU":
            tgn = round(self._rng.uniform(18, 45), 1)
            return {"tgn": tgn, "tpo": round(self._rng.uniform(5, min(30, tgn - 1)), 1)}
        raise ti.EntradaInvalidaError("Índice inválido.")


class EstrategiaResfriamento:
    """Estrategia de leitura quando ventilador/nebulizador estao ligados."""

    def __init__(
        self,
        fator_resfriamento: float = 0.95,
        fator_ventilacao: float = 1.05,
    ) -> None:
        self._fator_resfriamento = fator_resfriamento
        self._fator_ventilacao = fator_ventilacao

    def aplicar(self, especie: str, indice: str, estado: EstadoSensor) -> EstadoSensor:
        entradas = dict(estado.entradas)
        ajustadas = {
            campo: round(self._valor_ajustado(campo, entradas[campo]), 2 if campo == "v" else 1)
            for campo in ti.CAMPOS_POR_INDICE[indice]
        }
        if "tbs" in ajustadas and "tbu" in ajustadas:
            # Somente a estratégia SIMULADA: a validação de sensores reais
            # não é corrigida nem relaxada. Conserva margem para o jitter.
            ajustadas["tbu"] = min(ajustadas["tbu"], round(ajustadas["tbs"] - 1, 1))
        valor, status = ti.calcular_e_classificar(especie, indice, ajustadas)
        return EstadoSensor(entradas=ajustadas, valor=valor, status=status)

    def _valor_ajustado(self, campo: str, valor: float) -> float:
        minimo, maximo = ti.RANGE_VALIDACAO[campo]
        # Cenário ambiental do simulador: o resfriamento não pode empurrar
        # indefinidamente a amostra para temperaturas próximas de zero e
        # tornar inválido o ponto de orvalho derivado após o jitter.
        minimo = max(minimo, {"tbs": 18.0, "tbu": 12.0, "tgn": 18.0, "tpo": 5.0, "v": 0.5}[campo])
        if campo == "v":
            ajustado = valor * self._fator_ventilacao
        elif valor >= 0:
            ajustado = valor * self._fator_resfriamento
        else:
            ajustado = valor / self._fator_resfriamento
        return cast("float", max(minimo, min(maximo, ajustado)))


class SensorSimuladoService:
    """Controla o estado do sensor simulado.

    Padrao aplicado: Strategy. O servico escolhe entre geracao aleatoria e
    estrategia de resfriamento sem expor essa decisao as rotas.
    """

    def __init__(
        self,
        gerador_aleatorio: GeradorLeituraAleatoria | None = None,
        estrategia_resfriamento: EstrategiaResfriamento | None = None,
    ) -> None:
        self._gerador_aleatorio = gerador_aleatorio or GeradorLeituraAleatoria()
        self._estrategia_resfriamento = estrategia_resfriamento or EstrategiaResfriamento()
        self._estados: dict[tuple[str, str], EstadoSensor] = {}
        self._lock = threading.Lock()

    def registrar_calculo(
        self,
        especie: str,
        indice: str,
        entradas: dict[str, float],
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
