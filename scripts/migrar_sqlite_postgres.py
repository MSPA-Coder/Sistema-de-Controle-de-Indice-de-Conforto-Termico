# -*- coding: utf-8 -*-
"""Migra os dois bancos SQLite legados para os schemas PostgreSQL.

O comando é deliberadamente explícito porque limpa apenas as tabelas dos
schemas ``historico`` e ``dados_entrada`` antes de recarregar os dados. Os
arquivos SQLite são abertos somente para leitura e nunca são modificados.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path

from sqlalchemy import MetaData, Table, create_engine, inspect, text


TABELAS = {
    "historico": [
        "configuracoes",
        "usuarios",
        "zonas",
        "leituras",
        "equipamentos",
        "estado_equipamentos",
        "controle_zonas",
        "estado_coletor",
        "eventos_operacao",
        "leituras_recentes_zona",
        "agregados_15min",
        "resumos_horarios",
    ],
    "dados_entrada": [
        "configuracoes_zona",
        "execucoes",
        "medicoes",
        "cache_clima",
        "historico_exportado",
    ],
}


def argumentos() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--sqlite-dir",
        type=Path,
        default=Path("instance"),
        help="Diretório que contém historico.db e dados_entrada.db.",
    )
    parser.add_argument(
        "--database-url",
        default=os.environ.get("DATABASE_URL", ""),
    )
    parser.add_argument(
        "--confirm-reset-postgres",
        action="store_true",
        help="Confirma a limpeza dos dois schemas antes da importação.",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("migration_report.json"),
    )
    return parser.parse_args()


def validar_sqlite(caminho: Path) -> None:
    if not caminho.is_file():
        raise FileNotFoundError(caminho)
    uri = f"file:{caminho.resolve().as_posix()}?mode=ro&immutable=1"
    with sqlite3.connect(uri, uri=True) as conn:
        resultado = conn.execute("PRAGMA integrity_check").fetchone()[0]
        if resultado != "ok":
            raise RuntimeError(f"Integridade inválida em {caminho}: {resultado}")


def linhas_em_lotes(conn: sqlite3.Connection, tabela: str, tamanho: int = 2000):
    cursor = conn.execute(f'SELECT * FROM "{tabela}"')
    colunas = [item[0] for item in cursor.description]
    while True:
        lote = cursor.fetchmany(tamanho)
        if not lote:
            return
        yield [dict(zip(colunas, linha, strict=True)) for linha in lote]


def migrar_schema(connection, sqlite_path: Path, schema: str) -> dict[str, dict]:
    metadata = MetaData()
    inspector = inspect(connection)
    existentes = set(inspector.get_table_names(schema=schema))
    esperadas = TABELAS[schema]
    faltantes = set(esperadas) - existentes
    if faltantes:
        raise RuntimeError(
            f"Tabelas ausentes no schema {schema}: {sorted(faltantes)}"
        )

    nomes = ", ".join(f'"{schema}"."{nome}"' for nome in reversed(esperadas))
    connection.execute(text(f"TRUNCATE {nomes} RESTART IDENTITY CASCADE"))

    relatorio: dict[str, dict] = {}
    uri = f"file:{sqlite_path.resolve().as_posix()}?mode=ro&immutable=1"
    with sqlite3.connect(uri, uri=True) as origem:
        tabelas_origem = {
            row[0]
            for row in origem.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        for nome in esperadas:
            if nome not in tabelas_origem:
                relatorio[nome] = {
                    "sqlite": 0,
                    "postgres": 0,
                    "status": "ausente_no_sqlite",
                }
                continue
            tabela = Table(nome, metadata, schema=schema, autoload_with=connection)
            total_sqlite = int(
                origem.execute(f'SELECT COUNT(*) FROM "{nome}"').fetchone()[0]
            )
            inseridos = 0
            for lote in linhas_em_lotes(origem, nome):
                connection.execute(tabela.insert(), lote)
                inseridos += len(lote)

            if "id" in tabela.c and tabela.c.id.autoincrement:
                connection.execute(
                    text(
                        f"""
                        SELECT setval(
                            pg_get_serial_sequence('"{schema}"."{nome}"', 'id'),
                            COALESCE(MAX(id), 1),
                            MAX(id) IS NOT NULL
                        )
                        FROM "{schema}"."{nome}"
                        """
                    )
                )
            total_postgres = int(
                connection.execute(
                    text(f'SELECT COUNT(*) FROM "{schema}"."{nome}"')
                ).scalar_one()
            )
            if total_sqlite != total_postgres or inseridos != total_postgres:
                raise RuntimeError(
                    f"Contagem divergente em {schema}.{nome}: "
                    f"SQLite={total_sqlite}, PostgreSQL={total_postgres}"
                )
            relatorio[nome] = {
                "sqlite": total_sqlite,
                "postgres": total_postgres,
                "status": "ok",
            }
    return relatorio


def main() -> int:
    args = argumentos()
    if not args.confirm_reset_postgres:
        raise SystemExit(
            "Use --confirm-reset-postgres para confirmar a recarga dos schemas."
        )
    if not args.database_url.lower().startswith(("postgresql://", "postgresql+")):
        raise SystemExit("DATABASE_URL PostgreSQL não foi informada.")

    arquivos = {
        "historico": args.sqlite_dir / "historico.db",
        "dados_entrada": args.sqlite_dir / "dados_entrada.db",
    }
    for caminho in arquivos.values():
        validar_sqlite(caminho)

    engine = create_engine(args.database_url, pool_pre_ping=True)
    relatorio = {
        "inicio": datetime.now().astimezone().isoformat(),
        "origem": {schema: str(path) for schema, path in arquivos.items()},
        "schemas": {},
    }
    with engine.begin() as connection:
        for schema, caminho in arquivos.items():
            relatorio["schemas"][schema] = migrar_schema(
                connection, caminho, schema
            )
    relatorio["fim"] = datetime.now().astimezone().isoformat()
    args.report.write_text(
        json.dumps(relatorio, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(relatorio["schemas"], ensure_ascii=False, indent=2))
    print(f"Relatório salvo em {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
