"""Módulo base para repositórios com gerenciamento de conexão."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator

from app.database import DB_PATH, TIMEOUT_CONEXAO_SEGUNDOS


@contextmanager
def get_conexao() -> Iterator[sqlite3.Connection]:
    """Gerencia conexão com o banco de dados.

    Yields:
        Conexão SQLite que será fechada automaticamente.
    """
    conn = sqlite3.connect(DB_PATH, timeout=TIMEOUT_CONEXAO_SEGUNDOS)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()
