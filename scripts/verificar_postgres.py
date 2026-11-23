"""Smoke test do backend PostgreSQL sem deixar dados de teste persistidos."""

from __future__ import annotations

from app import database
from app.dados_entrada import db as dados_entrada_db
from app.models import agora_utc
from app.nucleo import db_backend


def main() -> int:
    if not db_backend.postgres_ativo():
        raise SystemExit("DATABASE_URL PostgreSQL não está ativa.")

    zonas = database.listar_zonas()
    usuarios = database.listar_usuarios()
    painel = database.obter_painel_zonas()
    execucoes = dados_entrada_db.listar_execucoes()
    if len(zonas) != len(painel):
        raise RuntimeError("Painel e cadastro de zonas estão divergentes.")

    if zonas:
        zona_id = zonas[0]["id"]
        historico = database.obter_historico_leituras(zona_id=zona_id, limite=3)
        if historico["total"] and not historico["leituras"]:
            raise RuntimeError("Paginação do histórico não retornou leituras.")

    if usuarios:
        login = usuarios[0]["login"]
        usuario = database.obter_usuario_por_login(login.swapcase())
        if not usuario or usuario["id"] != usuarios[0]["id"]:
            raise RuntimeError("Login PostgreSQL não está case-insensitive.")

    # Exercita geração de identidade e rollback na mesma conexão.
    with database._conexao(escrita=False) as conn:
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
                agora_utc(),
            ),
        )
        zona_teste_id = cursor.lastrowid
        if not zona_teste_id:
            raise RuntimeError("PostgreSQL não devolveu o ID gerado.")
    if database.obter_zona(zona_teste_id) is not None:
        raise RuntimeError("Rollback do PostgreSQL não foi respeitado.")

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
