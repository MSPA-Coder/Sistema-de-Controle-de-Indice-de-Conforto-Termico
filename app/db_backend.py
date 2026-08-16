"""Conexão PostgreSQL da aplicação.

Não há fallback de persistência: uma configuração ausente ou de outro dialeto
falha antes de a aplicação iniciar.
"""

from __future__ import annotations

import datetime
import json
import os
import re
from collections.abc import Iterator, Mapping
from functools import lru_cache
from pathlib import Path
from typing import Any


def _ler_segredo(nome_variavel: str) -> str:
    caminho = os.environ.get(nome_variavel, "").strip()
    if not caminho:
        return ""
    try:
        return Path(caminho).read_text(encoding="utf-8").strip()
    except OSError as erro:
        raise RuntimeError(
            f"Não foi possível ler o segredo indicado por {nome_variavel}."
        ) from erro


def database_url() -> str:
    url_direta = os.environ.get("DATABASE_URL", "").strip()
    if url_direta:
        return url_direta

    senha = _ler_segredo("DB_PASSWORD_FILE")
    host = os.environ.get("DB_HOST", "").strip()
    if not host:
        raise RuntimeError("DB_HOST é obrigatório no ambiente PostgreSQL.")
    if not senha:
        raise RuntimeError("DB_PASSWORD_FILE é obrigatório no ambiente PostgreSQL.")

    from sqlalchemy.engine import URL

    url = URL.create(
        "postgresql+psycopg",
        username=os.environ.get("DB_USER", "conforto"),
        password=senha,
        host=host or "postgres",
        port=int(os.environ.get("DB_PORT", "5432")),
        database=os.environ.get("DB_NAME", "conforto_termico"),
    )
    return url.render_as_string(hide_password=False)


def postgres_ativo() -> bool:
    url = database_url()
    if not url.lower().startswith(("postgresql://", "postgresql+")):
        raise RuntimeError("DATABASE_URL deve apontar para PostgreSQL.")
    return True


_engines_criados: dict[str, Any] = {}


@lru_cache(maxsize=4)
def _engine(url: str):
    from sqlalchemy import create_engine

    engine = create_engine(
        url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
        pool_recycle=1800,
        connect_args={"application_name": "conforto_termico"},
    )
    _engines_criados[url] = engine
    return engine


class LinhaCompat(Mapping):
    """Linha indexável por nome ou posição e convertível com ``dict(linha)``."""

    def __init__(self, row) -> None:
        self._mapping = {chave: _normalizar_valor(valor) for chave, valor in row._mapping.items()}
        self._values = tuple(_normalizar_valor(valor) for valor in row)

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._values[key]
        return self._mapping[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._mapping)

    def __len__(self) -> int:
        return len(self._mapping)


def _normalizar_valor(valor):
    """Mantém o contrato simples compartilhado com as consultas da aplicação."""

    if isinstance(valor, (dict, list)):
        return json.dumps(valor, ensure_ascii=False)
    if isinstance(valor, (datetime.date, datetime.datetime)):
        return valor.isoformat()
    return valor


class ResultadoCompat:
    def __init__(self, result, connection, schema: str, table: str | None) -> None:
        self._result = result
        self._connection = connection
        self._schema = schema
        self._table = table

    @property
    def rowcount(self) -> int:
        return int(self._result.rowcount)

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
    connection.exec_driver_sql(f'SET search_path TO "{schema}", public')
    return ConexaoPostgresCompat(connection, schema)


