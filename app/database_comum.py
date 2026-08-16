"""Infraestrutura compartilhada pelos agregados de persistência."""

from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING

from . import db_backend

if TYPE_CHECKING:
    from collections.abc import Iterator

PERFIS_VALIDOS = (
    "operador",
    "tecnico",
    "veterinario",
    "analista",
    "gestor",
    "administrador",
)


@contextmanager
def conexao(*, escrita: bool = True) -> Iterator:
    """Abre uma conexão PostgreSQL, confirma ou desfaz a transação e a fecha."""
    conn = db_backend.abrir_conexao_postgres("historico")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def coagir_booleano(valor, padrao: bool) -> bool:
    if isinstance(valor, bool):
        return valor
    if isinstance(valor, (int, float)):
        return bool(valor)
    if isinstance(valor, str):
        normalizado = valor.strip().lower()
        if normalizado in ("true", "1", "sim", "on"):
            return True
        if normalizado in ("false", "0", "nao", "não", "off", ""):
            return False
    return padrao
