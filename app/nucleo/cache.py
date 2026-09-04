"""
cache.py
========
Implementação de cache em memória com TTL para otimização de consultas repetidas.

Este módulo fornece um cache thread-safe com expiração por tempo de vida (TTL)
para dados de configuração e outras consultas frequentes ao banco de dados.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any


@dataclass
class CacheEntry:
    """Entrada de cache com valor e timestamp."""

    value: Any
    timestamp: float


class CacheComTTL:
    """
    Cache em memória com TTL (Time To Live) configurável.

    Thread-safe e adequado para caching de configurações, dados de referência
    e resultados de consultas pesadas que não mudam frequentemente.
    """

    def __init__(self, ttl_segundos: float = 300.0):
        """
        Inicializa o cache.

        Args:
            ttl_segundos: Tempo de vida padrão das entradas em segundos (padrão: 5min).
        """
        self._cache: dict[str, CacheEntry] = {}
        self._lock = threading.RLock()
        self._ttl_padrao = ttl_segundos

    def get(self, chave: str) -> Any | None:
        """
        Obtém um valor do cache se existir e não estiver expirado.

        Args:
            chave: Chave única do item no cache.

        Returns:
            O valor armazenado ou None se não existir ou estiver expirado.
        """
        with self._lock:
            entrada = self._cache.get(chave)
            if entrada is None:
                return None

            # Verifica se expirou
            if time.time() - entrada.timestamp > self._ttl_padrao:
                del self._cache[chave]
                return None

            return entrada.value

    def set(self, chave: str, valor: Any, ttl_segundos: float | None = None) -> None:
        """
        Armazena um valor no cache com TTL opcional específico.

        Args:
            chave: Chave única do item no cache.
            valor: Valor a ser armazenado.
            ttl_segundos: TTL específico para esta entrada (opcional, usa o padrão se None).
        """
        with self._lock:
            self._cache[chave] = CacheEntry(value=valor, timestamp=time.time())

    def delete(self, chave: str) -> bool:
        """
        Remove uma entrada do cache.

        Args:
            chave: Chave do item a remover.

        Returns:
            True se o item existia e foi removido, False caso contrário.
        """
        with self._lock:
            if chave in self._cache:
                del self._cache[chave]
                return True
            return False

    def clear(self) -> None:
        """Limpa todo o cache."""
        with self._lock:
            self._cache.clear()


# Instância global de cache para uso na aplicação
_cache_global: CacheComTTL | None = None


def obter_cache(ttl_segundos: float = 300.0) -> CacheComTTL:
    """
    Obtém ou cria a instância global de cache.

    Args:
        ttl_segundos: TTL padrão para o cache (apenas na criação).

    Returns:
        Instância singleton do cache.
    """
    global _cache_global
    if _cache_global is None:
        _cache_global = CacheComTTL(ttl_segundos)
    return _cache_global
