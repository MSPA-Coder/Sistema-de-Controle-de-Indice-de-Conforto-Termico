"""Leases e publicação com transações concorrentes em PostgreSQL real."""

import time
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from test_geracao_integridade_postgres import ambiente as ambiente
from test_geracao_integridade_postgres import configurar, parametros

from app import database as db
from app.dados_entrada import db as dados
from app.dados_entrada import gerador_dados as g


def gerar():
    zona, _ = configurar()
    return g.gerar(parametros(), [zona])["execucao_id"]


def estado(execucao_id, status, lease="2000-01-01T00:00:00+00:00"):
    with dados._conexao() as conn:
        conn.execute("UPDATE execucoes SET status=?, lease_until=? WHERE id=?", (status, lease, execucao_id))


@pytest.mark.parametrize("status", ["processando", "falhou"])
def test_csv_e_publicacao_nao_expoem_staging_incompleto(ambiente, status):
    eid = gerar()
    estado(eid, status)
    assert list(dados.iterar_medicoes_csv(eid, tamanho_lote=1)[1]) == []
    assert list(dados.iterar_medicoes_csv(tamanho_lote=1)[1]) == []
    with pytest.raises(dados.ConfiguracaoDadosEntradaError):
        dados.copiar_medicoes_para_historico(eid)
    assert db.contar_leituras() == 0


def test_recuperar_abandono_descarta_staging_e_impede_publicacao_tardia(ambiente):
    eid = gerar()
    estado(eid, "processando")
    assert dados.recuperar_execucoes_expiradas() == [eid]
    assert dados.recuperar_execucoes_expiradas() == []
    assert dados.obter_execucao(eid)["status"] == "falhou"
    assert not dados.heartbeat_execucao(eid)
    with pytest.raises(dados.ConfiguracaoDadosEntradaError):
        dados.concluir_execucao(eid, 24)
    with dados._conexao(escrita=False) as conn:
        assert conn.execute("SELECT count(*) FROM medicoes WHERE execucao_id=?", (eid,)).fetchone()[0] == 0
    assert db.contar_leituras() == 0
    assert gerar() != eid  # O abandono não impede uma execução posterior.


@pytest.mark.parametrize("finalizar", [False, True])
def test_recuperacao_aguarda_renovacao_ou_conclusao_em_curso_sem_apagar_amostras(ambiente, finalizar):
    eid = gerar()
    estado(eid, "processando")
    with ThreadPoolExecutor(max_workers=1) as pool:
        with dados._conexao() as escritor:
            pid = escritor.execute("SELECT pg_backend_pid()").fetchone()[0]
            # A execução ainda parece expirada aos outros processos, mas o
            # gerador já está renovando/publicando na sua própria transação.
            if finalizar:
                escritor.execute("UPDATE execucoes SET status='concluida', lease_until=NULL WHERE id=?", (eid,))
            else:
                assert dados.heartbeat_execucao(eid, conn=escritor)
            escritor.execute("SELECT id FROM medicoes WHERE execucao_id=? FOR UPDATE", (eid,)).fetchall()
            futuro = pool.submit(dados.recuperar_execucoes_expiradas)
            bloqueada = False
            limite = time.monotonic() + 10
            while time.monotonic() < limite:
                with dados._conexao(escrita=False) as observador:
                    bloqueada = observador.execute(
                        "SELECT EXISTS (SELECT 1 FROM pg_stat_activity WHERE ? = ANY(pg_blocking_pids(pid)))", (pid,)
                    ).fetchone()[0]
                if bloqueada:
                    break
                time.sleep(0.02)
        recuperadas = futuro.result(timeout=10)
    assert bloqueada, "O ensaio precisa observar uma espera real de lock no PostgreSQL."
    with dados._conexao(escrita=False) as conn:
        total = conn.execute("SELECT count(*) FROM medicoes WHERE execucao_id=?", (eid,)).fetchone()[0]
    assert (recuperadas, dados.obter_execucao(eid)["status"], total) == (
        [], "concluida" if finalizar else "processando", 24)
    if not finalizar:
        dados.concluir_execucao(eid, 24)
    assert len(list(dados.iterar_medicoes_csv(eid, tamanho_lote=7)[1])) == 24
    assert dados.copiar_medicoes_para_historico(eid)["novas_copiadas"] == 24


def test_duas_publicacoes_simultaneas_preservam_exatamente_uma_copia(ambiente):
    eid = gerar()
    barreira = Barrier(2)

    def publicar():
        barreira.wait(timeout=10)
        return dados.copiar_medicoes_para_historico(eid)["novas_copiadas"]

    with ThreadPoolExecutor(max_workers=2) as pool:
        futuros = [pool.submit(publicar) for _ in range(2)]
        assert sorted(f.result(timeout=15) for f in futuros) == [0, 24]
    assert db.contar_leituras() == 24
    with dados._conexao(escrita=False) as conn:
        assert conn.execute("SELECT count(*) FROM historico_exportado").fetchone()[0] == 24
