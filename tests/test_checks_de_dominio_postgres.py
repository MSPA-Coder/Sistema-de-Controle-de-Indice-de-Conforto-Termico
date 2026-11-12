"""CHECK nos campos de domínio fechado (revisão 20261112, SQL-L3).

Cada teste usa um banco só dele, migrado até a revisão anterior, para provar o
que a revisão faz com linhas já gravadas e que ela pode rodar duas vezes.
"""

from __future__ import annotations

from uuid import uuid4

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from psycopg import sql
from sqlalchemy.engine import make_url

pytestmark = pytest.mark.usefixtures("banco")

ANTERIOR = "20261111_instantes_restantes"
USUARIO = (
    "INSERT INTO historico.usuarios (nome, login, senha_hash, perfil, ativo, criado_em, atualizado_em) "
    "VALUES ('QA', %s, 'x', %s, %s, '2026-11-12T00:00:00+00', '2026-11-12T00:00:00+00')"
)
ZONA = (
    "INSERT INTO historico.zonas (nome, especie, indice, ativa, criado_em) "
    "VALUES ('QA', 'frangos', 'ITU', %s, '2026-11-12T00:00:00+00')"
)


@pytest.fixture
def banco_anterior(banco_de_teste, monkeypatch):
    url = make_url(banco_de_teste)
    nome = f"{url.database}_chk_{uuid4().hex[:8]}"
    servidor = url.set(drivername="postgresql", database="postgres").render_as_string(
        hide_password=False
    )
    with psycopg.connect(servidor, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(nome)))
    monkeypatch.setenv("DATABASE_URL", url.set(database=nome).render_as_string(hide_password=False))
    command.upgrade(Config("alembic.ini"), ANTERIOR)
    conexao_pg = psycopg.connect(
        url.set(drivername="postgresql", database=nome).render_as_string(hide_password=False),
        autocommit=True,
    )
    try:
        yield conexao_pg
    finally:
        conexao_pg.close()
        with psycopg.connect(servidor, autocommit=True) as admin:
            admin.execute(
                sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(nome))
            )


def _constraints(banco) -> set[str]:
    return {
        linha[0]
        for linha in banco.execute(
            "SELECT conname FROM pg_constraint WHERE conname LIKE 'ck\\_%\\_0\\_1' "
            "OR conname IN ('ck_usuarios_perfil', 'ck_controle_zonas_modo', "
            "'ck_equipamentos_modo_conexao')"
        )
    }


def test_valor_fora_do_dominio_e_recusado_depois_da_revisao(banco_anterior):
    banco = banco_anterior
    command.upgrade(Config("alembic.ini"), "head")

    with pytest.raises(psycopg.errors.CheckViolation):
        banco.execute(USUARIO, ("a", "operador", 2))
    with pytest.raises(psycopg.errors.CheckViolation):
        banco.execute(USUARIO, ("b", "admin", 1))
    with pytest.raises(psycopg.errors.CheckViolation):
        banco.execute(ZONA, (5,))
    banco.execute(USUARIO, ("c", "administrador", 1))
    banco.execute(ZONA, (1,))


def test_modo_da_zona_e_aceito_so_nos_quatro_valores(banco_anterior):
    banco = banco_anterior
    command.upgrade(Config("alembic.ini"), "head")
    banco.execute(ZONA, (1,))
    zona_id = banco.execute("SELECT id FROM historico.zonas").fetchone()[0]
    inserir = (
        "INSERT INTO historico.controle_zonas (zona_id, modo, acionamento_habilitado, atualizado_em) "
        "VALUES (%s, %s, 0, '2026-11-12T00:00:00+00')"
    )
    with pytest.raises(psycopg.errors.CheckViolation):
        banco.execute(inserir, (zona_id, "ligado"))
    banco.execute(inserir, (zona_id, "automatico"))


def test_linha_ja_gravada_fora_do_dominio_aborta_a_revisao_sem_alterar_nada(banco_anterior):
    banco = banco_anterior
    banco.execute(USUARIO, ("velho", "operador", 2))

    with pytest.raises(Exception, match="ck_usuarios_ativo_0_1"):
        command.upgrade(Config("alembic.ini"), "head")

    assert _constraints(banco) == set()
    assert banco.execute("SELECT version_num FROM alembic_version").fetchone()[0] == ANTERIOR


def test_a_revisao_pode_rodar_duas_vezes(banco_anterior):
    banco = banco_anterior
    command.upgrade(Config("alembic.ini"), "head")
    antes = _constraints(banco)
    assert len(antes) == 14

    banco.execute("UPDATE alembic_version SET version_num = %s", (ANTERIOR,))
    command.upgrade(Config("alembic.ini"), "head")

    assert _constraints(banco) == antes


def test_downgrade_remove_as_regras(banco_anterior):
    banco = banco_anterior
    command.upgrade(Config("alembic.ini"), "head")
    command.downgrade(Config("alembic.ini"), ANTERIOR)

    assert _constraints(banco) == set()
