"""Adota, de modo verificável, o baseline Alembic em banco já existente.

Uso administrativo (sempre dentro do contêiner):
``python -m scripts.adotar_baseline_alembic --adotar``.
Sem ``--adotar`` o comando apenas verifica e mostra o estado, sem escrita.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from sqlalchemy import text

from app.database import criar_backup_banco
from app.db_backend import database_url

BASELINE = "20260803_0001_baseline"
REVISAO_ANTERIOR = "0003_jsonb_nativo"
TABELAS = {
    "dados_entrada": {"cache_clima", "configuracoes_zona", "execucoes", "historico_exportado", "medicoes"},
    "historico": {"agregados_15min", "configuracoes", "controle_zonas", "equipamentos", "estado_coletor", "estado_equipamentos", "eventos_operacao", "leituras", "leituras_recentes_zona", "resumos_horarios", "usuarios", "zonas"},
}
INDICES = {
    "idx_zonas_ativa", "idx_leituras_especie_indice_id", "idx_leituras_zona_indice_id",
    "idx_leituras_zona_indice_criado_em", "idx_leituras_criado_em_id", "idx_equipamentos_zona_id",
    "idx_eventos_operacao_zona_id", "idx_leituras_recentes_zona_id", "idx_agregados_15min_zona",
    "idx_resumos_horarios_zona", "idx_medicoes_execucao_zona_data",
}
JSONB = {
    ("historico", "leituras", "entradas"), ("historico", "estado_equipamentos", "falhas"),
    ("historico", "eventos_operacao", "detalhes"), ("historico", "leituras_recentes_zona", "entradas"),
    ("historico", "agregados_15min", "entradas_medias"), ("dados_entrada", "medicoes", "origem_variaveis"),
    ("dados_entrada", "medicoes", "entradas_indice"), ("dados_entrada", "cache_clima", "resposta_json"),
}


def estado() -> dict[str, object]:
    from sqlalchemy import create_engine

    engine = create_engine(database_url(), pool_pre_ping=True)
    with engine.connect() as conn:
        revisao = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        tabelas = conn.execute(text("""
            SELECT table_schema, table_name FROM information_schema.tables
            WHERE table_schema IN ('historico', 'dados_entrada') AND table_type = 'BASE TABLE'
        """)).all()
        encontradas = {schema: set() for schema in TABELAS}
        for schema, tabela in tabelas:
            encontradas[schema].add(tabela)
        if encontradas != TABELAS:
            raise RuntimeError(f"Schema não corresponde ao baseline: {encontradas!r}")
        indices = {linha[0] for linha in conn.execute(text("""
            SELECT indexname FROM pg_indexes
            WHERE schemaname IN ('historico', 'dados_entrada')
        """))}
        ausentes = INDICES - indices
        if ausentes:
            raise RuntimeError(f"Índices obrigatórios ausentes: {sorted(ausentes)}")
        tipos = {(a, b, c) for a, b, c in conn.execute(text("""
            SELECT table_schema, table_name, column_name
            FROM information_schema.columns
            WHERE data_type = 'jsonb' AND table_schema IN ('historico', 'dados_entrada')
        """))}
        if not JSONB.issubset(tipos):
            raise RuntimeError(f"Colunas JSONB obrigatórias ausentes: {sorted(JSONB - tipos)}")
        contagens = dict(conn.execute(text("""
            SELECT schemaname || '.' || relname, n_live_tup::bigint
            FROM pg_stat_user_tables WHERE schemaname IN ('historico', 'dados_entrada')
            ORDER BY 1
        """)).all())
    engine.dispose()
    return {"revisao": revisao, "contagens": contagens}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adotar", action="store_true", help="faz backup validado e executa alembic stamp")
    args = parser.parse_args()
    antes = estado()
    if not args.adotar:
        print(json.dumps(antes, indent=2, sort_keys=True))
        return
    if antes["revisao"] != REVISAO_ANTERIOR:
        raise RuntimeError(f"Adoção só aceita {REVISAO_ANTERIOR}; encontrada {antes['revisao']!r}")
    backup = criar_backup_banco()
    arquivo = Path(str(backup["caminho"]))
    subprocess.run(["pg_restore", "--list", str(arquivo)], check=True, stdout=subprocess.DEVNULL)
    # ``--purge`` remove exclusivamente o marcador legado, que já não existe
    # no diretório de revisões consolidado; não executa DDL nem toca em dados.
    subprocess.run(["alembic", "stamp", "--purge", BASELINE], check=True)
    depois = estado()
    if depois["revisao"] != BASELINE or depois["contagens"] != antes["contagens"]:
        raise RuntimeError("Adoção não preservou estado esperado; restaure o backup antes de continuar.")
    print(json.dumps({"antes": antes, "backup": backup, "depois": depois}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
