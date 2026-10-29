"""Travas de banco: cada teste segura a trava em outra transação.

Padrão: a "primeira operação" fica aberta (já tomou a trava e mudou o estado, sem confirmar) e a
operação testada precisa esperar por ela e então enxergar o estado confirmado. Sem a trava, a
operação testada decide com o estado antigo e o resultado final é errado. Não depende de sorte de
tempo: a primeira operação só libera quando a segunda já esperou ou terminou.
"""

import json
from concurrent.futures import ThreadPoolExecutor, wait
from threading import Event

import pytest

from app import database as db
from app.database import configuracoes, leituras, usuarios, zonas
from app.database.comum import conexao


def _chave(conn, texto):
    conn.execute("SELECT pg_advisory_xact_lock(hashtext(?))", (texto,))


def _com_primeira_operacao_aberta(testada, trava, mexer_no_estado):
    """Roda `testada` enquanto `mexer_no_estado(conn)` segura `trava(conn)`; devolve (resultado, erro) da testada."""
    preparada, liberar = Event(), Event()

    def primeira():
        with conexao() as conn:
            trava(conn)
            mexer_no_estado(conn)
            preparada.set()
            assert liberar.wait(timeout=10)

    def segunda():
        try:
            return testada(), None
        except Exception as erro:  # noqa: BLE001 - o teste confere o tipo
            return None, erro

    with ThreadPoolExecutor(max_workers=2) as pool:
        a = pool.submit(primeira)
        assert preparada.wait(timeout=10)
        b = pool.submit(segunda)
        # Com a trava a segunda continua esperando; sem ela já terminou.
        wait([b], timeout=1.5)
        liberar.set()
        a.result(timeout=10)
        resultado = b.result(timeout=10)
    return resultado if isinstance(resultado, tuple) else (resultado, None)


# --- último administrador (database/usuarios.py) ------------------------------------------------------------


@pytest.fixture
def dois_administradores(banco):
    with conexao() as conn:
        conn.execute("TRUNCATE usuarios RESTART IDENTITY CASCADE")
    return [
        db.criar_usuario(
            {"nome": f"Admin {i}", "login": f"admin-{i}", "perfil": "administrador", "senha_hash": "hash-sintetico"},
            exigir_troca=False,
        )["id"]
        for i in (1, 2)
    ]


def _perfil(usuario_id):
    with conexao(escrita=False) as conn:
        return conn.execute("SELECT perfil FROM usuarios WHERE id = ?", (usuario_id,)).fetchone()["perfil"]


def test_rebaixar_o_ultimo_administrador_espera_e_e_recusado(dois_administradores):
    primeiro, segundo = dois_administradores

    def rebaixar_o_segundo():
        return db.atualizar_usuario(
            segundo, {"nome": "Admin 2", "login": "admin-2", "perfil": "operador", "ativo": True}
        )

    _, erro = _com_primeira_operacao_aberta(
        rebaixar_o_segundo,
        usuarios._bloquear_administradores,
        lambda conn: conn.execute("UPDATE usuarios SET perfil = 'operador' WHERE id = ?", (primeiro,)),
    )

    assert isinstance(erro, usuarios.UltimoAdministradorError)
    assert _perfil(segundo) == "administrador"


def test_excluir_o_ultimo_administrador_espera_e_e_recusado(dois_administradores):
    primeiro, segundo = dois_administradores

    _, erro = _com_primeira_operacao_aberta(
        lambda: db.excluir_usuario(segundo),
        usuarios._bloquear_administradores,
        lambda conn: conn.execute("UPDATE usuarios SET perfil = 'operador' WHERE id = ?", (primeiro,)),
    )

    assert isinstance(erro, usuarios.UltimoAdministradorError)
    assert _perfil(segundo) == "administrador"


# --- configurações (database/configuracoes.py) --------------------------------------------------------------


def test_salvar_configuracoes_espera_a_outra_gravacao_e_nao_perde_o_que_ela_gravou(banco):
    with conexao() as conn:
        conn.execute("TRUNCATE configuracoes")

    def gravar_altitude(conn):
        conn.execute(
            "INSERT INTO configuracoes (chave, valor, atualizado_em) VALUES ('altitudeMetros', ?, '2026-10-29T00:00:00') "
            "ON CONFLICT (chave) DO UPDATE SET valor = excluded.valor",
            (json.dumps(100),),
        )

    _com_primeira_operacao_aberta(
        lambda: configuracoes.salvar_configuracoes({"limiteUmidadeNebulizador": 75}),
        lambda conn: _chave(conn, "conforto:configuracoes"),
        gravar_altitude,
    )

    salvas = configuracoes.obter_configuracoes(usar_cache=False)
    assert salvas["altitudeMetros"] == 100
    assert salvas["limiteUmidadeNebulizador"] == 75


# --- leituras (database/leituras.py) ------------------------------------------------------------------------


@pytest.fixture
def zona(banco):
    return zonas.criar_zona({"nome": "Galpão das travas", "especie": "frangos", "indice": "ITU"})


def _inserir_leitura(conn, zona, instante: str, valor: float = 70.0):
    conn.execute(
        "INSERT INTO leituras (especie, indice, valor, status, entradas, criado_em, zona_id, timestamp_utc, amostra_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("frangos", "ITU", valor, "conforto", json.dumps({"tbs": 25.0}), instante, zona["id"], instante, f"a-{instante}"),
    )


def test_salvar_leitura_dentro_do_intervalo_espera_a_outra_e_e_recusada(zona):
    agora = leituras.agora_utc().isoformat(timespec="seconds")

    gravada, _ = _com_primeira_operacao_aberta(
        lambda: leituras.salvar_leitura(
            "frangos", "ITU", 71.0, "conforto", {"tbs": 25.0}, 60, zona_id=zona["id"], amostra_id="b-1"
        ),
        lambda conn: _chave(conn, f"conforto:leitura:{zona['id']}:ITU"),
        lambda conn: _inserir_leitura(conn, zona, agora),
    )

    assert gravada is False
    assert len(leituras.obter_historico_por_zona(zona["id"])) == 1


def test_agregar_janela_espera_a_publicacao_e_inclui_a_leitura_dela(zona):
    janela = "2026-09-24T01:00:00"
    with conexao() as conn:
        _inserir_leitura(conn, zona, "2026-09-24T01:05:00")

    resultado, _ = _com_primeira_operacao_aberta(
        lambda: leituras.agregar_janela_15min(zona["id"], "frangos", "ITU", janela),
        lambda conn: _chave(conn, f"conforto:agregacao:{zona['id']}:ITU"),
        lambda conn: _inserir_leitura(conn, zona, "2026-09-24T01:10:00"),
    )

    assert resultado["amostras"] == 2


def test_consolidar_hora_espera_a_publicacao_e_inclui_a_leitura_dela(zona):
    hora = "2026-09-24T01:00:00"
    with conexao() as conn:
        _inserir_leitura(conn, zona, "2026-09-24T01:05:00")

    resultado, _ = _com_primeira_operacao_aberta(
        lambda: leituras.consolidar_resumo_horario(zona["id"], "frangos", "ITU", hora),
        lambda conn: _chave(conn, f"conforto:agregacao:{zona['id']}:ITU"),
        lambda conn: _inserir_leitura(conn, zona, "2026-09-24T01:40:00"),
    )

    assert resultado["amostras"] == 2


# --- equipamentos (database/equipamentos.py) -----------------------------------------------------------------


def _equipamento(**mudancas):
    return {"nome": "Sensor", "tipo": "sensor", "campo_medido": "tbs", "modo_conexao": "tcp",
            "host": "sensor.invalid", "tipo_registrador": "holding", "endereco_registrador": 7, **mudancas}


@pytest.mark.parametrize("com_zona", [False, True])
def test_atualizar_equipamento_espera_a_exclusao_em_andamento_e_devolve_nao_encontrado(zona, com_zona):
    sensor = db.criar_equipamento(zona["id"], _equipamento())

    resultado, erro = _com_primeira_operacao_aberta(
        lambda: db.atualizar_equipamento(
            sensor["id"], _equipamento(nome="Novo nome"), zona_id=zona["id"] if com_zona else None
        ),
        lambda conn: None,
        lambda conn: conn.execute("DELETE FROM equipamentos WHERE id = ?", (sensor["id"],)),
    )

    assert erro is None
    assert resultado is None
    assert db.obter_equipamento(sensor["id"]) is None


# --- fila de notificações (nucleo/notificacoes.py) -----------------------------------------------------------


def test_reivindicar_a_fila_pula_o_item_que_outra_transacao_ja_segura(banco):
    from app.nucleo import notificacoes as n

    with banco() as conn:
        conn.execute("TRUNCATE notificacoes_outbox RESTART IDENTITY")
    item_id = n._enfileirar_outbox("qa@example.invalid", "Calor", {"host": "smtp.invalid"})

    itens, erro = _com_primeira_operacao_aberta(
        n._reivindicar_outbox,
        lambda conn: None,
        lambda conn: conn.execute("SELECT id FROM notificacoes_outbox WHERE id = ? FOR UPDATE", (item_id,)).fetchall(),
    )

    assert erro is None
    assert itens == []
    with banco(escrita=False) as conn:
        linha = dict(conn.execute("SELECT status, tentativas FROM notificacoes_outbox WHERE id=?", (item_id,)).fetchone())
    assert linha == {"status": "pendente", "tentativas": 0}
