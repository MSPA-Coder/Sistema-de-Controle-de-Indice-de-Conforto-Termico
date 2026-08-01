"""
postgres_test_utils.py
=======================
Infraestrutura compartilhada para testes que exercem persistência real,
conforme a base de engenharia (AGENTS.md): "Testes de models, repositories,
serviços com persistência e rotas que gravam dados usam PostgreSQL
descartável."

Este módulo NUNCA cria nem usa um arquivo SQLite. O PostgreSQL de teste é
lido das mesmas variáveis de ambiente usadas pelo Compose em produção
(DB_HOST, DB_PORT, DB_USER, DB_NAME, DB_PASSWORD_FILE) ou de DATABASE_URL
diretamente -- mas deve sempre apontar para uma instância descartável,
nunca para o banco operacional. Ver `compose.test.yaml` para como subir essa
instância localmente ou em CI, e o README ("Testes") para o passo a passo.

Isolamento entre testes
------------------------
`app.database._conexao()` confirma (`commit`) a cada chamada -- não existe
uma única transação externa em que se possa envolver o teste inteiro para
desfazer com rollback ao final. Em vez disso, cada teste começa com
`limpar_banco_teste()`, que esvazia (`TRUNCATE ... RESTART IDENTITY CASCADE`)
todas as tabelas das schemas `historico` e `dados_entrada`. Isso:

- reseta as sequences, então os IDs gerados em cada teste começam do mesmo
  ponto, como no antigo arquivo SQLite novo por teste;
- garante que nenhum teste veja linhas deixadas por outro;
- evita recriar o schema a cada teste (as migrações Alembic já rodaram uma
  vez, no início do processo) -- o que manteria a suíte rápida o bastante
  para o ciclo de desenvolvimento descrito no AGENTS.md.

Isso substitui, na prática, o par `db.DB_PATH = tempfile(...); db.iniciar_banco()`
que a suíte legada usava por classe de teste.
"""

from __future__ import annotations

import os
import unittest
from pathlib import Path

from app import dados_entrada_db, db_backend
from app import database as db

_RAIZ_PROJETO = Path(__file__).resolve().parents[1]
_migracoes_aplicadas = False


def banco_teste_configurado() -> bool:
    """Confirma um alvo de teste explicitamente identificado.

    `limpar_banco_teste` executa TRUNCATE; portanto, presença de uma conexão
    PostgreSQL não é suficiente para autorizar a suíte a utilizá-la.
    """

    return (
        os.environ.get("CONFORTO_TESTING") == "1"
        and os.environ.get("DB_NAME") == "conforto_termico_teste"
        and bool(os.environ.get("DATABASE_URL") or os.environ.get("DB_HOST"))
    )


def _aplicar_migracoes_uma_vez() -> None:
    global _migracoes_aplicadas
    if _migracoes_aplicadas:
        return

    from alembic import command
    from alembic.config import Config

    config = Config(str(_RAIZ_PROJETO / "alembic.ini"))
    config.set_main_option("script_location", str(_RAIZ_PROJETO / "migrations"))
    command.upgrade(config, "head")
    _migracoes_aplicadas = True


def _tabelas_das_schemas_de_teste(conn) -> list[tuple[str, str]]:
    linhas = conn.execute(
        """
        SELECT table_schema, table_name
        FROM information_schema.tables
        WHERE table_schema IN ('historico', 'dados_entrada')
          AND table_type = 'BASE TABLE'
        """
    ).fetchall()
    return [(linha["table_schema"], linha["table_name"]) for linha in linhas]


def limpar_banco_teste() -> None:
    """Esvazia todas as tabelas do PostgreSQL de teste configurado no
    ambiente de teste explicitamente identificado."""

    if not banco_teste_configurado():
        raise RuntimeError(
            "Recusado TRUNCATE fora do PostgreSQL descartável: defina "
            "CONFORTO_TESTING=1 e DB_NAME=conforto_termico_teste."
        )

    conn = db_backend.abrir_conexao_postgres("historico")
    try:
        tabelas = _tabelas_das_schemas_de_teste(conn)
        if not tabelas:
            return
        alvo = ", ".join(f'"{schema}"."{tabela}"' for schema, tabela in tabelas)
        conn.execute(f"TRUNCATE TABLE {alvo} RESTART IDENTITY CASCADE")
        conn.commit()
    finally:
        conn.close()


class TestCasePostgres(unittest.TestCase):
    """`TestCase` base para testes que exercem persistência real em
    PostgreSQL descartável.

    Requer `DB_HOST`/`DB_PASSWORD_FILE` (ou `DATABASE_URL`) apontando para
    uma instância de teste -- ver `compose.test.yaml`. Quando ausente, os
    testes são pulados com uma mensagem explicando como configurar, em vez
    de caírem silenciosamente de volta para SQLite.
    """

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        if not banco_teste_configurado():
            raise unittest.SkipTest(
                "PostgreSQL de teste não configurado com segurança. Use o serviço "
                "`test` de `compose.test.yaml`, que define CONFORTO_TESTING=1 e "
                "DB_NAME=conforto_termico_teste."
            )
        if not db_backend.postgres_ativo():
            raise unittest.SkipTest(
                "DATABASE_URL/DB_HOST presente mas não resolveu para "
                "PostgreSQL; confira a configuração do ambiente de teste."
            )
        _aplicar_migracoes_uma_vez()

    def setUp(self) -> None:
        super().setUp()
        limpar_banco_teste()
        # Ambos são no-ops sob PostgreSQL (o schema já existe via Alembic);
        # mantidos para paridade de chamada com o restante do código, que
        # sempre inicializa o banco antes de usá-lo.
        db.iniciar_banco()
        dados_entrada_db.iniciar_banco()
