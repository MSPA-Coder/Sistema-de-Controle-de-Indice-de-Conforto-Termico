"""Limites pequenos e locais para consultas custosas do ICT."""

from __future__ import annotations

import threading
import time
from collections import deque


class LimitadorJanela:
    """Rate limiter em memória com janelas fixas e cardinalidade limitada."""

    def __init__(self, limites: tuple[tuple[int, int], ...], *, max_chaves: int = 2048):
        self._limites = limites
        self._max_chaves = max_chaves
        self._eventos: dict[str, deque[float]] = {}
        self._lock = threading.RLock()

    def permitir(self, chave: str, *, agora: float | None = None) -> bool:
        instante = time.monotonic() if agora is None else agora
        with self._lock:
            eventos = self._eventos.get(chave)
            if eventos is None:
                if len(self._eventos) >= self._max_chaves:
                    self._eventos.pop(next(iter(self._eventos)))
                eventos = deque()
                self._eventos[chave] = eventos

            maior_janela = max(janela for janela, _ in self._limites)
            while eventos and eventos[0] <= instante - maior_janela:
                eventos.popleft()

            if any(sum(1 for evento in eventos if evento > instante - janela) >= limite
                   for janela, limite in self._limites):
                return False
            eventos.append(instante)
            return True
