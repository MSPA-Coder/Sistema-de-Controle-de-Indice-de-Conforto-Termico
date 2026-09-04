"""Regressões das prioridades CT-05, CT-07 e CT-09 da auditoria funcional."""

from __future__ import annotations

import datetime
import inspect
from contextlib import contextmanager
from pathlib import Path

import app
from app.dados_entrada import rotas as dados_entrada_rotas
from app.database import zonas as database_zonas


class _ConexaoEstadoFalsa:
    def __init__(self, linhas):
        self._linhas = linhas

    def execute(self, _sql):
        linhas = self._linhas

        class _Resultado:
            def fetchall(self):
                return linhas

        return _Resultado()


def test_estado_operacional_marca_leitura_antiga_como_desatualizada(monkeypatch):
    antigo = (datetime.datetime.now() - datetime.timedelta(hours=1)).replace(
        microsecond=0
    )
    zona = {
        "id": 7,
        "nome": "Teste",
        "ativa": True,
        "controle": {"modo": "automatico", "acionamento_habilitado": True},
    }

    @contextmanager
    def conexao_falsa(*, escrita=False):
        assert escrita is False
        yield _ConexaoEstadoFalsa(
            [
                {
                    "zona_id": 7,
                    "falhas": "[]",
                    "qualidade": "boa",
                    "ultimo_ciclo_em": antigo.isoformat(),
                    "ventilador_desejado": True,
                    "nebulizador_desejado": False,
                    "ventilador_confirmado": True,
                    "nebulizador_confirmado": False,
                    "intensidade": "media",
                }
            ]
        )

    monkeypatch.setattr(database_zonas, "listar_zonas", lambda: [zona])
    monkeypatch.setattr(database_zonas, "_conexao", conexao_falsa)
    monkeypatch.setattr(
        database_zonas,
        "obter_configuracoes",
        lambda: {"intervaloLeituraSegundos": 60},
    )

    (estado,) = database_zonas.obter_estado_operacional_zonas()

    assert estado["leitura_atual"] is False
    assert estado["qualidade"] == "desatualizada"
    assert estado["qualidade_original"] == "boa"
    assert estado["idade_leitura_segundos"] >= 3599


def test_estado_operacional_preserva_sem_leitura_quando_nunca_houve_ciclo(monkeypatch):
    zona = {
        "id": 8,
        "nome": "Sem leitura",
        "ativa": True,
        "controle": {"modo": "manual", "acionamento_habilitado": True},
    }

    @contextmanager
    def conexao_falsa(*, escrita=False):
        assert escrita is False
        yield _ConexaoEstadoFalsa([])

    monkeypatch.setattr(database_zonas, "listar_zonas", lambda: [zona])
    monkeypatch.setattr(database_zonas, "_conexao", conexao_falsa)
    monkeypatch.setattr(
        database_zonas,
        "obter_configuracoes",
        lambda: {"intervaloLeituraSegundos": 60},
    )

    (estado,) = database_zonas.obter_estado_operacional_zonas()

    assert estado["leitura_atual"] is False
    assert estado["qualidade"] == "sem_leitura"
    assert estado["idade_leitura_segundos"] is None


def test_estado_operacional_respeita_ciclos_de_expiracao_por_zona(monkeypatch):
    recente = (datetime.datetime.now() - datetime.timedelta(seconds=150)).replace(microsecond=0)
    zonas = [
        {"id": 9, "nome": "Dois ciclos", "ativa": True, "ciclos_expiracao_leitura": 2,
         "controle": {"modo": "automatico", "acionamento_habilitado": True}},
        {"id": 10, "nome": "Três ciclos", "ativa": True, "ciclos_expiracao_leitura": 3,
         "controle": {"modo": "automatico", "acionamento_habilitado": True}},
    ]

    @contextmanager
    def conexao_falsa(*, escrita=False):
        assert escrita is False
        yield _ConexaoEstadoFalsa(
            [
                {"zona_id": zona["id"], "falhas": "[]", "qualidade": "boa",
                 "ultimo_ciclo_em": recente.isoformat(), "ventilador_desejado": False,
                 "nebulizador_desejado": False, "ventilador_confirmado": False,
                 "nebulizador_confirmado": False, "intensidade": None}
                for zona in zonas
            ]
        )

    monkeypatch.setattr(database_zonas, "listar_zonas", lambda: zonas)
    monkeypatch.setattr(database_zonas, "_conexao", conexao_falsa)
    monkeypatch.setattr(database_zonas, "obter_configuracoes", lambda: {"intervaloLeituraSegundos": 60})

    dois_ciclos, tres_ciclos = database_zonas.obter_estado_operacional_zonas()

    assert dois_ciclos["leitura_atual"] is False
    assert dois_ciclos["limite_atualidade_segundos"] == 120
    assert tres_ciclos["leitura_atual"] is True
    assert tres_ciclos["limite_atualidade_segundos"] == 180


def test_exportacao_csv_e_incremental(app, monkeypatch):
    consumidas = []

    def linhas():
        for numero in range(10_000):
            consumidas.append(numero)
            yield (numero, f"zona-{numero}")

    monkeypatch.setattr(
        dados_entrada_rotas.dados_db,
        "iterar_medicoes_csv",
        lambda _execucao_id: (["id", "zona"], linhas()),
    )

    with app.test_request_context("/api/dados-entrada/exportar.csv"):
        resposta = dados_entrada_rotas.exportar_csv()
        assert resposta.is_streamed
        assert consumidas == []
        corpo = resposta.get_data(as_text=True)

    assert corpo.startswith("\ufeffid,zona\r\n0,zona-0\r\n")
    assert corpo.endswith("9999,zona-9999\r\n")
    assert len(consumidas) == 10_000


def test_salvar_zona_nao_empilha_confirmacao_sobre_dialogo_modal():
    fonte = inspect.getsource(dados_entrada_rotas).replace("\r\n", "\n")
    assert "stream_with_context(gerar_csv())" in fonte

    # Ancorado no pacote `app`, nao no modulo de persistencia: o caminho do
    # arquivo estatico nao tem relacao com onde `zonas.py` mora.
    caminho = Path(app.__file__).parent / "static/js/features/cadastro-zonas.js"
    with open(caminho, encoding="utf-8") as arquivo:
        javascript = arquivo.read()
    salvar_zona = javascript.split("async function salvarZona", 1)[1].split(
        "async function excluirZona", 1
    )[0]
    assert "await confirm" not in salvar_zona
    assert "await fetch" in salvar_zona
