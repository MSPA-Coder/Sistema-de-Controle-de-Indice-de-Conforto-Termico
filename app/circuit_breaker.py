"""Circuit Breaker para chamadas ao serviço Coletor.

Implementa o padrão Circuit Breaker para prevenir falhas em cascata
quando o serviço coletor está indisponível, permitindo fallback rápido
e recuperação gradual.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, TypeVar, Any

T = TypeVar("T")


class EstadoCircuitBreaker(Enum):
    """Estados possíveis do circuit breaker."""

    FECHADO = "fechado"  # Operações normais
    ABERTO = "aberto"  # Falhas recentes, operações bloqueadas
    MEIO_ABERTO = "meio_aberto"  # Testando recuperação


@dataclass
class Circuito:
    """Estado interno de um circuit breaker."""

    estado: EstadoCircuitBreaker = EstadoCircuitBreaker.FECHADO
    falhas_consecutivas: int = 0
    ultima_falha: float = 0.0
    ultima_sucesso: float = 0.0
    tentativas_meio_aberto: int = 0


class CircuitBreaker:
    """Circuit Breaker para proteção de chamadas externas.

    Args:
        nome: Identificador único do circuito (ex: "coletor")
        limite_falhas: Número de falhas consecutivas para abrir o circuito
        timeout_recuperacao: Segundos aguardando antes de tentar recuperar (meio-aberto)
        max_tentativas_meio_aberto: Máximo de tentativas no estado meio-aberto
    """

    def __init__(
        self,
        nome: str,
        limite_falhas: int = 5,
        timeout_recuperacao: float = 30.0,
        max_tentativas_meio_aberto: int = 3,
    ) -> None:
        self.nome = nome
        self.limite_falhas = limite_falhas
        self.timeout_recuperacao = timeout_recuperacao
        self.max_tentativas_meio_aberto = max_tentativas_meio_aberto

        self._circuitos: dict[str, Circuito] = {}
        self._lock = threading.Lock()

    def _obter_circuito(self, chave: str = "default") -> Circuito:
        """Obtém ou cria circuito para a chave especificada."""
        with self._lock:
            if chave not in self._circuitos:
                self._circuitos[chave] = Circuito()
            return self._circuitos[chave]

    def _registrar_sucesso(self, circuito: Circuito) -> None:
        """Registra operação bem-sucedida."""
        circuito.falhas_consecutivas = 0
        circuito.ultima_sucesso = time.time()
        circuito.estado = EstadoCircuitBreaker.FECHADO
        circuito.tentativas_meio_aberto = 0

    def _registrar_falha(self, circuito: Circuito) -> None:
        """Registra falha e atualiza estado se necessário."""
        circuito.falhas_consecutivas += 1
        circuito.ultima_falha = time.time()

        if circuito.estado == EstadoCircuitBreaker.MEIO_ABERTO:
            circuito.tentativas_meio_aberto += 1
            if circuito.tentativas_meio_aberto >= self.max_tentativas_meio_aberto:
                circuito.estado = EstadoCircuitBreaker.ABERTO
                circuito.tentativas_meio_aberto = 0
        elif circuito.falhas_consecutivas >= self.limite_falhas:
            circuito.estado = EstadoCircuitBreaker.ABERTO

    def _pode_executar(self, circuito: Circuito) -> bool:
        """Verifica se operação pode ser executada no estado atual."""
        agora = time.time()

        if circuito.estado == EstadoCircuitBreaker.FECHADO:
            return True

        if circuito.estado == EstadoCircuitBreaker.ABERTO:
            if agora - circuito.ultima_falha >= self.timeout_recuperacao:
                circuito.estado = EstadoCircuitBreaker.MEIO_ABERTO
                circuito.tentativas_meio_aberto = 0
                return True
            return False

        # MEIO_ABERTO: permite tentativa limitada
        return circuito.tentativas_meio_aberto < self.max_tentativas_meio_aberto

    def executar(
        self,
        operacao: Callable[[], T],
        chave: str = "default",
        fallback: Callable[[], T] | None = None,
    ) -> T:
        """Executa operação protegida pelo circuit breaker.

        Args:
            operacao: Função a ser executada
            chave: Identificador da operação (para múltiplos circuitos)
            fallback: Função alternativa em caso de circuito aberto

        Returns:
            Resultado da operação ou fallback

        Raises:
            CircuitBreakerAbertoError: Se circuito estiver aberto e não houver fallback
        """
        circuito = self._obter_circuito(chave)

        with self._lock:
            if not self._pode_executar(circuito):
                if fallback:
                    return fallback()
                raise CircuitBreakerAbertoError(
                    f"Circuit breaker '{self.nome}' está aberto. "
                    f"Estado: {circuito.estado.value}, "
                    f"Falhas: {circuito.falhas_consecutivas}"
                )

        try:
            resultado = operacao()
            with self._lock:
                self._registrar_sucesso(circuito)
            return resultado

        except Exception as erro:
            with self._lock:
                self._registrar_falha(circuito)

            if fallback:
                return fallback()
            raise


class CircuitBreakerAbertoError(Exception):
    """Exceção levantada quando circuit breaker está aberto."""

    pass


# Instância global para o coletor
circuit_breaker_coletor = CircuitBreaker(
    nome="coletor",
    limite_falhas=5,
    timeout_recuperacao=30.0,
    max_tentativas_meio_aberto=3,
)


def obter_circuit_breaker(nome: str) -> CircuitBreaker:
    """Obtém circuit breaker por nome.

    Args:
        nome: Nome do circuit breaker desejado

    Returns:
        Instância do circuit breaker
    """
    if nome == "coletor":
        return circuit_breaker_coletor

    # Cria novo circuit breaker para outros serviços
    return CircuitBreaker(nome=nome)
