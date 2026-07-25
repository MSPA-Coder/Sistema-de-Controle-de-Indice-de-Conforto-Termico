# -*- coding: utf-8 -*-
"""Smoke test do backend PostgreSQL sem deixar dados de teste persistidos."""

from __future__ import annotations

import os
from datetime import datetime

from app import dados_entrada_db
from app import database
from app import db_backend


def main() -> int:
    if not db_backend.postgres_ativo():
        raise SystemExit("DATABASE_URL PostgreSQL não está ativa.")

    zonas = database.listar_zonas()
    usuarios = database.listar_usuarios()
    painel = database.obter_painel_zonas()
    execucoes = dados_entrada_db.listar_execucoes()
    if len(zonas) != len(painel):
        raise RuntimeError("Painel e cadastro de zonas estão divergentes.")
    if not zonas or not usuarios:
        raise RuntimeError("Dados essenciais migrados não foram encontrados.")

    zona_id = zonas[0]["id"]
    historico = database.obter_historico_leituras(zona_id=zona_id, limite=3)
    if historico["total"] and not historico["leituras"]:
        raise RuntimeError("Paginação do histórico não retornou leituras.")

    login = usuarios[0]["login"]
    usuario = database.obter_usuario_por_login(login.swapcase())
    if not usuario or usuario["id"] != usuarios[0]["id"]:
        raise RuntimeError("Login PostgreSQL não está case-insensitive.")

    # Exercita geração de identidade e rollback na mesma conexão.
    context = database._conexao()
    conn = context.__enter__()
    try:
        cursor = conn.execute(
            """
            INSERT INTO zonas (nome, especie, indice, ativa, criado_em)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                "__postgres_smoke_rollback__",
                "frangos",
                "ITU",
                1,
                datetime.now().isoformat(timespec="seconds"),
            ),
        )
        if not cursor.lastrowid:
            raise RuntimeError("PostgreSQL não devolveu o ID gerado.")
        conn.rollback()
    finally:
        context.__exit__(None, None, None)
    if any(z["nome"] == "__postgres_smoke_rollback__" for z in database.listar_zonas()):
        raise RuntimeError("Rollback do PostgreSQL não foi respeitado.")

    # Uma execução já exportada deve permanecer idempotente.
    concluidas = [item for item in execucoes if item["status"] == "concluida"]
    if concluidas:
        resultado = dados_entrada_db.copiar_medicoes_para_historico(
            concluidas[0]["id"]
        )
        if resultado["novas_copiadas"] != 0:
            raise RuntimeError("Exportação idempotente duplicaria medições.")

    print(
        "PostgreSQL OK:",
        f"zonas={len(zonas)}",
        f"usuarios={len(usuarios)}",
        f"leituras={database.contar_leituras()}",
        f"execucoes={len(execucoes)}",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
