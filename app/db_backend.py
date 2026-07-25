# -*- coding: utf-8 -*-
"""Compatibilidade mínima entre o contrato sqlite3 existente e PostgreSQL.

O projeto continua aceitando SQLite quando ``DATABASE_URL`` não está
definida, o que preserva os testes unitários rápidos. No ambiente Docker, as
conexões são abertas pelo SQLAlchemy e este adaptador mantém o pequeno
subconjunto da API DB-API usado pelos módulos de persistência.
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterator, Mapping
from functools import lru_cache
from typing import Any


def database_url() -> str:
    return os.environ.get("DATABASE_URL", "").strip()


def postgres_ativo() -> bool:
    return database_url().lower().startswith(("postgresql://", "postgresql+"))


@lru_cache(maxsize=4)
def _engine(url: str):
    from sqlalchemy import create_engine

    return create_engine(
        url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
    )


class LinhaCompat(Mapping):
    """Linha indexável por nome ou posição e convertível com ``dict(linha)``."""

    def __init__(self, row) -> None:
        self._mapping = row._mapping
        self._values = tuple(row)

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._values[key]
        return self._mapping[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._mapping)

    def __len__(self) -> int:
        return len(self._mapping)


class ResultadoCompat:
    def __init__(self, result, connection, schema: str, table: str | None) -> None:
        self._result = result
        self._connection = connection
        self._schema = schema
        self._table = table

    @property
    def rowcount(self) -> int:
        return self._result.rowcount

    @property
    def lastrowid(self) -> int | None:
        if not self._table:
            return None
        sequence = self._connection.exec_driver_sql(
            "SELECT currval(pg_get_serial_sequence(%s, %s))",
            (f"{self._schema}.{self._table}", "id"),
        ).scalar_one_or_none()
        return int(sequence) if sequence is not None else None

    def fetchone(self):
        row = self._result.fetchone()
        return LinhaCompat(row) if row is not None else None

    def fetchall(self) -> list[LinhaCompat]:
        return [LinhaCompat(row) for row in self._result.fetchall()]


_INSERT_TABLE_RE = re.compile(
    r"^\s*INSERT\s+INTO\s+(?:[A-Za-z_][A-Za-z0-9_]*\.)?"
    r"([A-Za-z_][A-Za-z0-9_]*)",
    re.IGNORECASE,
)


def _adaptar_placeholders(sql: str) -> str:
    # As consultas do projeto não contêm o caractere '?' em literais SQL.
    return sql.replace("?", "%s")


class ConexaoPostgresCompat:
    def __init__(self, connection, schema: str) -> None:
        self._connection = connection
        self.schema = schema

    def execute(self, sql: str, parametros: tuple | list = ()) -> ResultadoCompat:
        adapted = _adaptar_placeholders(sql)
        result = self._connection.exec_driver_sql(adapted, tuple(parametros))
        match = _INSERT_TABLE_RE.match(sql)
        table = match.group(1) if match else None
        return ResultadoCompat(result, self._connection, self.schema, table)

    def executemany(self, sql: str, parametros: list[tuple]) -> ResultadoCompat:
        result = self._connection.exec_driver_sql(
            _adaptar_placeholders(sql),
            [tuple(item) for item in parametros],
        )
        match = _INSERT_TABLE_RE.match(sql)
        table = match.group(1) if match else None
        return ResultadoCompat(result, self._connection, self.schema, table)

    def commit(self) -> None:
        self._connection.commit()

    def rollback(self) -> None:
        self._connection.rollback()

    def close(self) -> None:
        self._connection.close()


def abrir_conexao_postgres(schema: str) -> ConexaoPostgresCompat:
    connection = _engine(database_url()).connect()
    connection.exec_driver_sql(
        f'SET search_path TO "{schema}", public'
    )
    return ConexaoPostgresCompat(connection, schema)


def limpar_cache_engine() -> None:
    _engine.cache_clear()
