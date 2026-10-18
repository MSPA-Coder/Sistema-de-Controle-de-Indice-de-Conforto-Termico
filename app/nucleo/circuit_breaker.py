"""Proteção local por dependência, sem retries implícitos de comandos."""

from __future__ import annotations

import math
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import TypeVar

T = TypeVar("T")


class EstadoCircuitBreaker(Enum):
    FECHADO = "fechado"
    ABERTO = "aberto"
    MEIO_ABERTO = "meio_aberto"


@dataclass
class Circuito:
    estado: EstadoCircuitBreaker = EstadoCircuitBreaker.FECHADO
    falhas_consecutivas: int = 0
    ultima_falha: float = 0.0
    em_voo: int = 0
    geracao: int = 0


class CircuitBreakerAbertoError(Exception):
    """Uma chamada foi recusada antes de acessar a dependência."""


class CircuitBreaker:
    """Somente falhas elegíveis alteram o circuito; erros de código propagam.

    O lock protege a admissão e os resultados, nunca rede ou fallback. Uma
    geração invalida respostas de chamadas anteriores à abertura/recuperação.
    O limite de sondas é por processo, não uma coordenação entre instâncias.
    """

    def __init__(
        self,
        nome: str,
        limite_falhas: int = 5,
        timeout_recuperacao: float = 30.0,
        max_tentativas_meio_aberto: int = 3,
        *,
        relogio: Callable[[], float] = time.monotonic,
        falhas_esperadas: tuple[type[Exception], ...] = (OSError,),
    ) -> None:
        if limite_falhas < 1 or max_tentativas_meio_aberto < 1:
            raise ValueError("Os limites do circuito precisam ser positivos.")
        if not math.isfinite(timeout_recuperacao) or timeout_recuperacao < 0:
            raise ValueError("O prazo de recuperação precisa ser finito e não negativo.")
        self.nome = nome
        self.limite_falhas = limite_falhas
        self.timeout_recuperacao = timeout_recuperacao
        self.max_tentativas_meio_aberto = max_tentativas_meio_aberto
        self._relogio = relogio
        self._falhas_esperadas = falhas_esperadas
        self._circuitos: dict[str, Circuito] = {}
        self._lock = threading.Lock()

    def _reservar(self, chave: str) -> tuple[Circuito, int] | None:
        with self._lock:
            circuito = self._circuitos.setdefault(chave, Circuito())
            if circuito.estado == EstadoCircuitBreaker.ABERTO:
                if self._relogio() - circuito.ultima_falha < self.timeout_recuperacao:
                    return None
                circuito.estado = EstadoCircuitBreaker.MEIO_ABERTO
                circuito.geracao += 1
                circuito.em_voo = 0
            if circuito.estado == EstadoCircuitBreaker.MEIO_ABERTO:
                if circuito.em_voo >= self.max_tentativas_meio_aberto:
                    return None
                circuito.em_voo += 1
            return circuito, circuito.geracao

    def _finalizar(self, circuito: Circuito, geracao: int, *, falhou: bool) -> None:
        with self._lock:
            if circuito.geracao != geracao:
                return
            recuperando = circuito.estado == EstadoCircuitBreaker.MEIO_ABERTO
            if recuperando:
                circuito.em_voo -= 1
            if falhou:
                circuito.falhas_consecutivas += 1
                if recuperando or circuito.falhas_consecutivas >= self.limite_falhas:
                    circuito.estado = EstadoCircuitBreaker.ABERTO
                    circuito.ultima_falha = self._relogio()
                    circuito.geracao += 1
                    circuito.em_voo = 0
            elif not recuperando or circuito.em_voo == 0:
                circuito.falhas_consecutivas = 0
                circuito.estado = EstadoCircuitBreaker.FECHADO
                if recuperando:
                    circuito.geracao += 1

    def executar(
        self,
        operacao: Callable[[], T],
        chave: str = "default",
        fallback: Callable[[], T] | None = None,
    ) -> T:
        reserva = self._reservar(chave)
        if reserva is None:
            if fallback is not None:
                return fallback()
            raise CircuitBreakerAbertoError(f"Circuit breaker '{self.nome}' está aberto.")
        circuito, geracao = reserva
        try:
            resultado = operacao()
        except self._falhas_esperadas:
            self._finalizar(circuito, geracao, falhou=True)
            if fallback is not None:
                return fallback()
            raise
        except BaseException:
            # Libera a sonda sem converter um defeito de programação em 502.
            self._finalizar(circuito, geracao, falhou=False)
            raise
        self._finalizar(circuito, geracao, falhou=False)
        return resultado
