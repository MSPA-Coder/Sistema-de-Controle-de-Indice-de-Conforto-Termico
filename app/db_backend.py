"""Conexão PostgreSQL e compatibilidade da API de persistência.

Não há fallback: uma configuração ausente ou de outro dialeto falha antes de a
aplicação iniciar. A camada preserva contratos existentes como marcadores `?`,
`lastrowid` e `LinhaCompat`; ela não é um backend SQLite alternativo.

Duas limitações exigem cuidado:

1. **`RETURNING id` não é geral.** Várias tabelas gravadas não têm coluna `id`,
   portanto acrescentar a cláusula a todo INSERT quebraria upserts válidos. A
   leitura de `currval` é protegida por `rowcount` quando nada foi inserido.
2. **`%` literal no SQL.** Ao converter para o estilo `%s` do psycopg, um
   `LIKE '%termo%'` pode ser interpretado como formatação. Escapar às cegas
   também quebraria SQL que já usa `%s`; o primeiro uso precisa tratar a
   distinção explicitamente.
"""

from __future__ import annotations

import datetime
import json
import os
import re
from collections.abc import Iterator, Mapping
from functools import lru_cache
from typing import Any

from sharedauth.config import montar_url_postgres
from sharedauth.secrets import DIRETORIO_SECRETS_COMPOSE, resolver_segredo


def _ler_segredo(nome: str) -> str:
    """Senha do Postgres, exclusivamente pelo Docker secret esperado."""
    valor = resolver_segredo(
        nome,
        aceitar_variavel=False,
        caminho_esperado=DIRETORIO_SECRETS_COMPOSE / "postgres_password",
    )
    return valor or ""


def database_url() -> str:
    url_direta = os.environ.get("DATABASE_URL", "").strip()
    if url_direta:
        return url_direta

    senha = _ler_segredo("DB_PASSWORD")
    host = os.environ.get("DB_HOST", "").strip()
    if not host:
        raise RuntimeError("DB_HOST é obrigatório no ambiente PostgreSQL.")
    if not senha:
        raise RuntimeError("DB_PASSWORD_FILE é obrigatório no ambiente PostgreSQL.")

    # `montar_url_postgres` (sharedauth.config) escapa usuário, senha e banco
    # com `quote(..., safe="")` e valida a porta. Uma senha com `@`, `/` ou `:`
    # apontaria a conexão para outro host sem que nada acusasse erro de escape.
    # Python puro -- não traz SQLAlchemy para este caminho de configuração.
    try:
        return montar_url_postgres(
            usuario=os.environ.get("DB_USER", "conforto"),
            senha=senha,
            host=host or "postgres",
            banco=os.environ.get("DB_NAME", "conforto_termico"),
            porta=os.environ.get("DB_PORT", "5432"),
        )
    except ValueError as erro:
        raise RuntimeError(f"Configuração PostgreSQL inválida: {erro}") from erro


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
        # Nenhuma linha inserida (o caso do `ON CONFLICT ... DO NOTHING` que
        # bateu no conflito): `currval` devolveria o id da última inserção
        # ANTERIOR na mesma sessão -- um número plausível, de outra linha, sem
        # nada indicando o engano. Latente hoje (o único DO NOTHING do projeto
        # é em `estado_equipamentos`, que não tem coluna `id` e cujo lastrowid
        # ninguém lê), e é exatamente por ser latente que merece a guarda: o
        # dia em que alguém ler vai ser um dia normal.
        if self.rowcount == 0:
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

    def fetchmany(self, tamanho: int = 1000) -> list[LinhaCompat]:
        """Lê um lote sem materializar o restante do resultado em memória."""
        return [LinhaCompat(row) for row in self._result.fetchmany(tamanho)]


_INSERT_TABLE_RE = re.compile(
    r"^\s*INSERT\s+INTO\s+(?:[A-Za-z_][A-Za-z0-9_]*\.)?"
    r"([A-Za-z_][A-Za-z0-9_]*)",
    re.IGNORECASE,
)


# Início de literal com cifrão: `$$` ou `$tag$`.
_DOLAR_RE = re.compile(r"\$(?:[A-Za-z_][A-Za-z0-9_]*)?\$")

# `?|` e `?&` são operadores de `jsonb` no PostgreSQL, não marcadores.
_OPERADORES_JSONB = ("?|", "?&")


def _adaptar_placeholders(sql: str) -> tuple[str, int]:
    """Converte `?` (estilo SQLite) em `%s` (estilo psycopg).

    A versão anterior era `sql.replace("?", "%s")`, com o comentário "as
    consultas do projeto não contêm o caractere '?' em literais SQL". O
    invariante estava garantido por um comentário, e o comentário não é
    executável: bastava alguém escrever `WHERE nome = 'e agora?'` ou usar um
    operador de `jsonb` para a consulta ser corrompida em silêncio.

    E não é hipótese distante — este projeto já consulta `jsonb`
    (`l.entradas::jsonb`, em `app/database/leituras.py`). `?`, `?|` e `?&` são
    operadores legítimos ali: `coluna ? 'chave'` pergunta se a chave existe. No
    dia em que alguém escrevesse a consulta natural, o `replace` a transformaria
    em `coluna %s 'chave'` e o erro apareceria longe da causa.

    Percorre o SQL respeitando literais com aspas simples (inclusive `''`),
    identificadores entre aspas duplas, literais com cifrão (`$$`/`$tag$`),
    comentários de linha e de bloco (que aninham no PostgreSQL). Devolve o SQL
    convertido e QUANTOS marcadores foram convertidos -- a contagem é o que
    permite recusar a consulta ambígua em vez de deixá-la passar torta.
    """
    saida: list[str] = []
    convertidos = 0
    i = 0
    n = len(sql)

    while i < n:
        c = sql[i]

        if c == "'" or c == '"':
            fechamento = c
            j = i + 1
            while j < n:
                if sql[j] == fechamento:
                    # Aspa dobrada é escape, não fechamento.
                    if j + 1 < n and sql[j + 1] == fechamento:
                        j += 2
                        continue
                    j += 1
                    break
                j += 1
            saida.append(sql[i:j])
            i = j
            continue

        if c == "$":
            marca = _DOLAR_RE.match(sql, i)
            if marca:
                etiqueta = marca.group(0)
                fim = sql.find(etiqueta, i + len(etiqueta))
                j = n if fim == -1 else fim + len(etiqueta)
                saida.append(sql[i:j])
                i = j
                continue

        if sql.startswith("--", i):
            fim = sql.find("\n", i)
            j = n if fim == -1 else fim
            saida.append(sql[i:j])
            i = j
            continue

        if sql.startswith("/*", i):
            profundidade = 0
            j = i
            while j < n:
                if sql.startswith("/*", j):
                    profundidade += 1
                    j += 2
                    continue
                if sql.startswith("*/", j):
                    profundidade -= 1
                    j += 2
                    if profundidade == 0:
                        break
                    continue
                j += 1
            saida.append(sql[i:j])
            i = j
            continue

        if c == "?":
            if sql.startswith(_OPERADORES_JSONB, i):
                saida.append(sql[i : i + 2])
                i += 2
                continue
            saida.append("%s")
            convertidos += 1
            i += 1
            continue

        saida.append(c)
        i += 1

    return "".join(saida), convertidos


def _conferir_aridade(sql: str, convertidos: int, esperados: int) -> None:
    """Recusa a consulta quando a contagem de marcadores não bate.

    É a rede que pega o caso que o percorredor não tem como decidir sozinho: um
    `?` solto de `jsonb` (`coluna ? 'chave'`) é indistinguível de um marcador
    olhando só o texto. Se a contagem divergir dos parâmetros passados, a
    consulta iria para o banco torta -- melhor falhar aqui, com a causa à mão,
    do que produzir erro de sintaxe ou, pior, resultado errado.
    """
    if convertidos == esperados:
        return
    raise ValueError(
        f"Marcadores '?' convertidos ({convertidos}) não batem com os "
        f"parâmetros passados ({esperados}).\n"
        f"Causa provável: um '?' que não é marcador -- operador de jsonb, ou "
        f"um '?' dentro de literal que o percorredor não reconheceu.\n"
        f"Para perguntar se uma chave existe em jsonb sem ambiguidade, use "
        f"jsonb_exists(coluna, ?) no lugar de (coluna ? 'chave').\n"
        f"SQL: {' '.join(sql.split())[:300]}"
    )


class ConexaoPostgresCompat:
    def __init__(self, connection, schema: str) -> None:
        self._connection = connection
        self.schema = schema

    def execute(self, sql: str, parametros: tuple | list = ()) -> ResultadoCompat:
        adapted, convertidos = _adaptar_placeholders(sql)
        _conferir_aridade(sql, convertidos, len(tuple(parametros)))
        result = self._connection.exec_driver_sql(adapted, tuple(parametros))
        match = _INSERT_TABLE_RE.match(sql)
        table = match.group(1) if match else None
        return ResultadoCompat(result, self._connection, self.schema, table)

    def executemany(self, sql: str, parametros: list[tuple]) -> ResultadoCompat:
        adapted, convertidos = _adaptar_placeholders(sql)
        # A aridade se confere pela primeira linha: as demais têm de ter o
        # mesmo formato, e o driver reclama se não tiverem.
        if parametros:
            _conferir_aridade(sql, convertidos, len(tuple(parametros[0])))
        result = self._connection.exec_driver_sql(
            adapted,
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
