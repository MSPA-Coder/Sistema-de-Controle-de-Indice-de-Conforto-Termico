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
from typing import TYPE_CHECKING, Any, TypeVar

if TYPE_CHECKING:
    from collections.abc import Callable

T = TypeVar("T")


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
        self._hits = 0
        self._misses = 0

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
                self._misses += 1
                return None

            # Verifica se expirou
            if time.time() - entrada.timestamp > self._ttl_padrao:
                del self._cache[chave]
                self._misses += 1
                return None

            self._hits += 1
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
            self._hits = 0
            self._misses = 0

    def invalidate_pattern(self, padrao: str) -> int:
        """
        Invalida todas as chaves que correspondem a um padrão.

        Args:
            padrao: Prefixo ou padrão para matching (usa startswith).

        Returns:
            Número de entradas invalidadas.
        """
        with self._lock:
            chaves_para_remover = [k for k in self._cache if k.startswith(padrao)]
            for chave in chaves_para_remover:
                del self._cache[chave]
            return len(chaves_para_remover)

    def stats(self) -> dict[str, Any]:
        """
        Retorna estatísticas de uso do cache.

        Returns:
            Dicionário com hits, misses, hit_rate e tamanho atual.
        """
        with self._lock:
            total = self._hits + self._misses
            hit_rate = (self._hits / total * 100) if total > 0 else 0.0
            return {
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": round(hit_rate, 2),
                "tamanho": len(self._cache),
            }

    def cached(self, chave_prefixo: str = "") -> Callable[[Callable[..., T]], Callable[..., T]]:
        """
        Decorador para cachear automaticamente o resultado de uma função.

        Args:
            chave_prefixo: Prefixo opcional para as chaves geradas.

        Returns:
            Decorador que aplica caching à função decorada.

        Exemplo:
            @cache.cached("config_")
            def obter_configuracao_zona(zona_id: int) -> dict:
                ...
        """

        def decorator(func: Callable[..., T]) -> Callable[..., T]:
            def wrapper(*args: Any, **kwargs: Any) -> T:
                # Gera chave única baseada nos argumentos
                chave_args = "_".join(str(a) for a in args)
                chave_kwargs = "_".join(f"{k}={v}" for k, v in sorted(kwargs.items()))
                chave = f"{chave_prefixo}{func.__name__}:{chave_args}:{chave_kwargs}"

                # Tenta obter do cache
                valor_cached = self.get(chave)
                if valor_cached is not None:
                    return valor_cached

                # Executa a função e armazena no cache
                resultado = func(*args, **kwargs)
                self.set(chave, resultado)
                return resultado

            wrapper.__name__ = func.__name__
            wrapper.__doc__ = func.__doc__
            return wrapper

        return decorator


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


def resetar_cache_global() -> None:
    """Reseta o cache global (útil para testes)."""
    global _cache_global
    if _cache_global is not None:
        _cache_global.clear()
        _cache_global = None
