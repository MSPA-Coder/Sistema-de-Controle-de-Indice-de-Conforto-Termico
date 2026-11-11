"""Instantes são `timestamptz`: a revisão converte os três formatos antigos de texto.

Até 11/11/2026 o banco guardava hora local sem offset, UTC sem offset e UTC com
`+00:00` em colunas TEXT, e as consultas usavam `::timestamp` (que descarta o
offset). Aqui a revisão `20261111_instantes_com_fuso` roda sobre linhas montadas
nos formatos antigos, e o código novo grava e lê instantes sem mudar o que as
telas e as APIs mostram.
"""

from __future__ import annotations

import ast
import datetime
import importlib.util
import pathlib
from uuid import uuid4

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from psycopg import sql
from sqlalchemy.engine import make_url

from app import models
from app.dados_entrada import db as dados_db
from app.database import leituras, operacao, usuarios, zonas
from app.database.comum import conexao

pytestmark = pytest.mark.usefixtures("banco")

ANTERIOR = "20261111_auditoria_so_insercao"
UTC = datetime.UTC


@pytest.fixture
def banco_antigo(banco_de_teste, monkeypatch):
    """Um banco só para este teste, migrado até a revisão anterior à conversão."""
    url = make_url(banco_de_teste)
    nome = f"{url.database}_fuso_{uuid4().hex[:8]}"
    servidor = url.set(drivername="postgresql", database="postgres").render_as_string(
        hide_password=False
    )
    with psycopg.connect(servidor, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(nome)))
    alvo = url.set(database=nome).render_as_string(hide_password=False)
    monkeypatch.setenv("DATABASE_URL", alvo)
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


def _preencher(banco, tabela: str, **valores) -> None:
    """INSERT com os NOT NULL sem DEFAULT preenchidos por tipo; `valores` manda."""
    esquema, nome = tabela.split(".")
    colunas = banco.execute(
        "SELECT column_name, data_type FROM information_schema.columns "
        "WHERE table_schema=%s AND table_name=%s AND is_nullable='NO' "
        "AND column_default IS NULL AND is_identity='NO'",
        (esquema, nome),
    ).fetchall()
    padrao = {"text": "x", "USER-DEFINED": "x", "integer": 1, "bigint": 1,
              "double precision": 1.0, "jsonb": "{}"}
    dados = {c: padrao[t] for c, t in colunas}
    dados.update(valores)
    nomes = list(dados)
    banco.execute(
        sql.SQL("INSERT INTO {}.{} ({}) VALUES ({})").format(
            sql.Identifier(esquema), sql.Identifier(nome),
            sql.SQL(",").join(map(sql.Identifier, nomes)),
            sql.SQL(",").join(sql.Placeholder() for _ in nomes),
        ),
        [dados[n] for n in nomes],
    )


def _um(banco, consulta: str):
    return banco.execute(consulta).fetchone()[0]


def _montar_formatos_antigos(banco) -> None:
    banco.execute("SET TIME ZONE 'UTC'")
    _preencher(banco, "historico.zonas", id=1, criado_em="2026-11-11T10:00:00")
    # Os três formatos, na mesma coluna e em colunas diferentes.
    _preencher(banco, "historico.usuarios", id=1, login="a",
               criado_em="2026-11-11T10:00:00",            # local sem offset
               atualizado_em="2026-11-11T10:00:00+00:00",  # UTC com offset
               ultimo_login_em="")                         # vazio, coluna aceita NULL
    _preencher(banco, "historico.usuarios", id=2, login="b",
               criado_em="2026-11-11T10:00:00-03:00",      # offset diferente de UTC
               atualizado_em="2026-11-11 10:00:00.250000+00:00")
    _preencher(banco, "historico.leituras", id=1, zona_id=1,
               criado_em="2026-11-11T10:00+00:00", timestamp_utc="2026-11-11T10:05:00")  # UTC naive
    _preencher(banco, "historico.agregados_15min", zona_id=1, indice="ITU",
               janela_inicio="2026-11-11T10:15:00", criado_em="2026-11-11T10:30:00+00:00")
    _preencher(banco, "historico.sessoes_revogadas", sid="s", expira_em="2026-11-11T10:00:00+00:00")
    _preencher(banco, "historico.estado_coletor", id=1, status="online",
               heartbeat_em="2026-11-11T10:00:00")
    _preencher(banco, "dados_entrada.execucoes", id=1, data_inicio="2026-11-01",
               data_fim="2026-11-10", criado_em="2026-11-11T10:00:00+00:00",
               lease_until="2026-11-11T10:05:00+00:00")
    _preencher(banco, "dados_entrada.medicoes", id=1, execucao_id=1, zona_id=1,
               timestamp_utc="2026-11-11T10:00+00:00", timestamp_local="2026-11-11T07:00-03:00",
               fuso_horario="America/Sao_Paulo")


def test_revisao_converte_os_tres_formatos_antigos_para_o_instante_certo(banco_antigo):
    banco = banco_antigo
    _montar_formatos_antigos(banco)

    command.upgrade(Config("alembic.ini"), "head")

    def instante(tabela, coluna, onde="TRUE"):
        valor = _um(banco, f"SELECT {coluna} FROM {tabela} WHERE {onde}")
        return None if valor is None else valor.astimezone(UTC).replace(tzinfo=None).isoformat()

    # Hora local sem offset: 10:00 em Brasília é 13:00 UTC.
    assert instante("historico.usuarios", "criado_em", "id=1") == "2026-11-11T13:00:00"
    assert instante("historico.zonas", "criado_em") == "2026-11-11T13:00:00"
    assert instante("historico.estado_coletor", "heartbeat_em") == "2026-11-11T13:00:00"
    # UTC com offset vale como está, inclusive com fração e separador de espaço.
    assert instante("historico.usuarios", "atualizado_em", "id=1") == "2026-11-11T10:00:00"
    assert instante("historico.usuarios", "atualizado_em", "id=2") == "2026-11-11T10:00:00.250000"
    assert instante("historico.leituras", "criado_em") == "2026-11-11T10:00:00"
    # O offset do próprio texto manda, também numa coluna "local".
    assert instante("historico.usuarios", "criado_em", "id=2") == "2026-11-11T13:00:00"
    # UTC sem offset (janelas, e `leituras.timestamp_utc` legado).
    assert instante("historico.agregados_15min", "janela_inicio") == "2026-11-11T10:15:00"
    assert instante("historico.leituras", "timestamp_utc") == "2026-11-11T10:05:00"
    # Vazio numa coluna que aceita NULL vira NULL, nunca uma data inventada.
    assert instante("historico.usuarios", "ultimo_login_em", "id=1") is None
    # `timestamp_local` sempre teve offset; o mesmo instante que `timestamp_utc`.
    assert instante("dados_entrada.medicoes", "timestamp_local") == "2026-11-11T10:00:00"
    # Dias do calendário viram `date`.
    assert _um(banco, "SELECT data_inicio FROM dados_entrada.execucoes") == datetime.date(2026, 11, 1)


def test_revisao_falha_inteira_com_texto_invalido_em_coluna_obrigatoria(banco_antigo):
    banco = banco_antigo
    _montar_formatos_antigos(banco)
    banco.execute("UPDATE historico.usuarios SET criado_em = 'ontem' WHERE id = 2")

    with pytest.raises(RuntimeError, match=r"usuarios\.criado_em.*NULL"):
        command.upgrade(Config("alembic.ini"), "head")

    # Nada ficou pela metade: a primeira coluna da lista continua texto.
    assert _um(
        banco,
        "SELECT data_type FROM information_schema.columns WHERE table_schema='historico' "
        "AND table_name='configuracoes' AND column_name='atualizado_em'",
    ) == "text"


def test_revisao_recusa_texto_sem_offset_em_timestamp_local(banco_antigo):
    banco = banco_antigo
    _montar_formatos_antigos(banco)
    banco.execute("UPDATE dados_entrada.medicoes SET timestamp_local = '2026-11-11T07:00:00'")

    with pytest.raises(RuntimeError, match=r"medicoes\.timestamp_local"):
        command.upgrade(Config("alembic.ini"), "head")


def test_downgrade_devolve_texto_iso_no_formato_que_cada_coluna_tinha(banco_antigo):
    banco = banco_antigo
    _montar_formatos_antigos(banco)
    command.upgrade(Config("alembic.ini"), "head")

    command.downgrade(Config("alembic.ini"), ANTERIOR)

    assert _um(banco, "SELECT criado_em FROM historico.usuarios WHERE id=1") == "2026-11-11T10:00:00"
    # `usuarios.atualizado_em` era hora local: 10:00 UTC volta como 07:00 de Brasília.
    assert _um(banco, "SELECT atualizado_em FROM historico.usuarios WHERE id=2") == "2026-11-11T07:00:00"
    assert _um(banco, "SELECT expira_em FROM historico.sessoes_revogadas") == "2026-11-11T10:00:00+00:00"
    assert _um(banco, "SELECT janela_inicio FROM historico.agregados_15min") == "2026-11-11T10:15:00"
    assert _um(banco, "SELECT criado_em FROM historico.leituras") == "2026-11-11T10:00:00+00:00"
    assert _um(banco, "SELECT timestamp_local FROM dados_entrada.medicoes") == "2026-11-11T07:00-03:00"
    assert _um(banco, "SELECT timestamp_utc FROM dados_entrada.medicoes") == "2026-11-11T10:00+00:00"
    assert _um(banco, "SELECT data_fim FROM dados_entrada.execucoes") == "2026-11-10"


# --- O código novo, pela porta pública --------------------------------------


def _colunas_da_revisao() -> list[tuple]:
    caminho = pathlib.Path(__file__).resolve().parent.parent / "migrations/versions"
    spec = importlib.util.spec_from_file_location(
        "revisao_instantes", caminho / "20261111_instantes_com_fuso.py"
    )
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo.COLUNAS


def test_nenhuma_coluna_de_instante_continua_texto(banco):
    texto = []
    for esquema, tabela, coluna, *_ in _colunas_da_revisao():
        with conexao() as conn:
            tipo = conn.execute(
                "SELECT data_type FROM information_schema.columns WHERE table_schema=? "
                "AND table_name=? AND column_name=?",
                (esquema, tabela, coluna),
            ).fetchone()[0]
        if tipo != "timestamp with time zone":
            texto.append(f"{esquema}.{tabela}.{coluna}")
    assert texto == []


@pytest.fixture
def fuso_de_brasilia(monkeypatch):
    monkeypatch.setenv("TZ", "America/Sao_Paulo")


def test_cadastro_grava_o_instante_e_a_api_continua_com_a_hora_local(
    banco, fuso_de_brasilia, monkeypatch
):
    monkeypatch.setattr(usuarios, "agora_utc", lambda: datetime.datetime(2026, 11, 11, 13, 0, tzinfo=UTC))

    criado = usuarios.criar_usuario(
        {"nome": "Ana", "login": "ana", "perfil": "operador", "senha_hash": "h"}
    )

    # O que a tela e a API sempre mostraram: hora local, sem offset.
    assert criado["criado_em"] == "2026-11-11T10:00:00"
    assert usuarios.obter_usuario(criado["id"])["criado_em"] == "2026-11-11T10:00:00"
    # O que o banco guarda: o instante, com fuso.
    with conexao() as conn:
        bruto = conn.execute("SELECT criado_em FROM usuarios WHERE id=?", (criado["id"],)).fetchone()[0]
    assert bruto == "2026-11-11T13:00:00+00:00"


def test_status_do_coletor_mostra_hora_local_e_online_por_instante(
    banco, fuso_de_brasilia, monkeypatch
):
    agora = models.agora_utc()
    monkeypatch.setattr(operacao, "agora_utc", lambda: agora)

    operacao.salvar_status_coletor("online", proximo_ciclo_em=agora + datetime.timedelta(seconds=5))
    status = operacao.obter_status_coletor()

    esperado = agora.astimezone(models.fuso_local()).replace(tzinfo=None).isoformat(timespec="seconds")
    assert status["heartbeat_em"] == esperado
    assert status["online"] is True


def test_leituras_e_agregados_saem_em_utc_com_offset(banco, fuso_de_brasilia):
    zona = zonas.criar_zona({"nome": "Galpão", "especie": "frangos", "indice": "ITU"})
    with conexao() as conn:
        conn.execute(
            "INSERT INTO leituras (especie, indice, valor, status, entradas, criado_em, zona_id) "
            "VALUES ('frangos', 'ITU', 70, 'Conforto', '{}', ?, ?)",
            (datetime.datetime(2026, 9, 24, 1, 30, tzinfo=UTC), zona["id"]),
        )

    (janela,) = leituras.janelas_15min_pendentes(zona["id"], "ITU")
    leituras.agregar_janela_15min(zona["id"], "frangos", "ITU", janela)

    assert janela == "2026-09-24T01:30:00+00:00"
    assert leituras.obter_historico_leituras()["leituras"][0]["criado_em"] == "2026-09-24T01:30:00+00:00"
    assert leituras.obter_agregados_15min(zona["id"])[0]["janela_inicio"] == "2026-09-24T01:30:00+00:00"


def test_csv_de_medicoes_mantem_o_formato_de_instante_do_contrato(banco):
    medicao = {
        "execucao_id": 1, "zona_id": 1, "zona_nome": "Z", "especie": "frangos", "indice": "ITU",
        "timestamp_utc": datetime.datetime(2026, 11, 11, 10, 0, tzinfo=UTC),
        "timestamp_local": datetime.datetime(2026, 11, 11, 10, 0, tzinfo=UTC),
        "fuso_horario": "America/Sao_Paulo",
        "origem_variaveis": "{}", "entradas_indice": {}, "status_termico": "Conforto",
        "indicador_qualidade": "q", "densidade_categoria": "media",
        "atividade_predominante": "x",
    }
    for coluna in dados_db._COLUNAS_MEDICAO:
        medicao.setdefault(coluna, 1)
    with dados_db._conexao() as conn:
        conn.execute("TRUNCATE execucoes CASCADE")
        conn.execute(
            "INSERT INTO execucoes (id, data_inicio, data_fim, dias, intervalo_minutos, semente, "
            "fonte_clima, total_zonas, status, criado_em) "
            "VALUES (1, '2026-11-10', '2026-11-11', 1, 15, 1, 'x', 1, 'concluida', ?)",
            (models.agora_utc(),),
        )
    dados_db.inserir_medicoes([medicao])

    colunas, linhas = dados_db.iterar_medicoes_csv()
    (linha,) = list(linhas)
    por_nome = dict(zip(colunas, linha, strict=True))

    assert por_nome["timestamp_utc"] == "2026-11-11T10:00+00:00"
    assert por_nome["timestamp_local"] == "2026-11-11T07:00-03:00"


# --- Uma única fonte de "agora" ----------------------------------------------


def test_so_models_py_pergunta_que_horas_sao():
    """Varredura de política (T3): `datetime.now()` e `date.today()` ficam em `models.py`.

    Eram 22 usos com três semânticas (local sem fuso, UTC com offset, UTC sem
    fuso); o `TZ` do contêiner era a única amarra entre eles.
    """
    raiz = pathlib.Path(__file__).resolve().parent.parent / "app"
    achados = []
    for arquivo in raiz.rglob("*.py"):
        if arquivo.name == "models.py" and arquivo.parent == raiz:
            continue
        for no in ast.walk(ast.parse(arquivo.read_text(encoding="utf-8"))):
            if (
                isinstance(no, ast.Call)
                and isinstance(no.func, ast.Attribute)
                and no.func.attr in {"now", "today", "utcnow"}
            ):
                achados.append(f"{arquivo.relative_to(raiz.parent)}:{no.lineno}")
    assert achados == [], "use app.models.agora_utc()/agora_local()/hoje_local(): " + ", ".join(achados)
