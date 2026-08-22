"""GET nao escreve, e `escrita=False` significa alguma coisa.

`GET /api/dados-entrada/configuracoes` chamava `sincronizar_zonas`, que faz
INSERT/UPDATE em `configuracoes_zona`. Qualquer prefetch de navegador, robo ou
sonda de monitoracao escrevia no banco so por passar ali. O efeito era
idempotente -- nao havia perda de dado --, entao nada quebrava e nada
denunciava: e contrato de HTTP quebrado, do tipo que so cobra o preco quando
alguem constroi em cima.

Junto vinha um segundo caso: `_conexao(escrita=False)` commitava igual. Cinco
chamadores pediam leitura e recebiam uma conexao que gravava.

Sem banco, como o resto desta suite: a conexao e substituida por uma que
registra o SQL e conta commit e rollback. E o suficiente, porque o que se mede
aqui e QUAL comando sai e se ele e confirmado -- nao o que o PostgreSQL faz
com ele.
"""

from __future__ import annotations

import pytest

from app import dados_entrada_db


class _Resultado:
    def __init__(self, linhas):
        self._linhas = linhas

    def fetchall(self):
        return list(self._linhas)

    def fetchone(self):
        return self._linhas[0] if self._linhas else None


class _ConexaoFalsa:
    def __init__(self, linhas):
        self._linhas = linhas
        self.comandos: list[str] = []
        self.commits = 0
        self.rollbacks = 0

    def execute(self, sql, parametros=None):
        self.comandos.append(" ".join(sql.split()))
        return _Resultado(self._linhas)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        pass


def _grava(comando: str) -> bool:
    inicio = comando.strip().upper()
    return inicio.startswith(("INSERT", "UPDATE", "DELETE", "TRUNCATE"))


@pytest.fixture
def conexao(monkeypatch):
    falsa = _ConexaoFalsa([])
    monkeypatch.setattr(
        dados_entrada_db.db_backend, "abrir_conexao_postgres", lambda _schema: falsa
    )
    return falsa


ZONAS = [
    {"id": 2, "nome": "Galpão B", "especie": "aves"},
    {"id": 1, "nome": "Galpão A", "especie": "bovinos"},
]


def test_listar_configuracoes_nao_emite_comando_de_escrita(conexao):
    dados_entrada_db.listar_configuracoes(ZONAS)

    assert conexao.comandos, "o teste precisa ter exercitado alguma consulta"
    assert not [c for c in conexao.comandos if _grava(c)]


def test_listar_configuracoes_descarta_a_transacao(conexao):
    dados_entrada_db.listar_configuracoes(ZONAS)

    # Nao basta nao ter INSERT: `escrita=False` precisa nao confirmar nada.
    # Era exatamente aqui que o parametro mentia.
    assert conexao.commits == 0
    assert conexao.rollbacks == 1


def test_sincronizar_zonas_continua_gravando(conexao):
    # Controle positivo. Sem ele, os testes acima passariam tambem se a
    # materializacao tivesse sido perdida junto -- e ela e o que faz a zona
    # nova ganhar linha quando o usuario salva ou gera dados.
    dados_entrada_db.sincronizar_zonas(ZONAS)

    assert [c for c in conexao.comandos if _grava(c)]
    assert conexao.commits == 1


def test_zona_sem_linha_gravada_aparece_como_nao_configurada(conexao):
    configuracoes = dados_entrada_db.listar_configuracoes(ZONAS)

    assert [c["zona_id"] for c in configuracoes] == [1, 2], "ordem por zona_id"
    assert all(c["configurada"] is False for c in configuracoes)
    # Os DEFAULT do DDL precisam aparecer, senao a tela mostraria vazio onde a
    # linha recem-criada mostrava valor.
    assert all(c["fuso_horario"] == "America/Sao_Paulo" for c in configuracoes)
    assert all(c["densidade_categoria"] == "media" for c in configuracoes)


def test_rotulo_vem_da_zona_viva_e_nao_da_copia_gravada(monkeypatch):
    # Antes, renomear uma zona so refletia aqui porque o proprio GET regravava
    # o rotulo. Sem a escrita, a leitura precisa sobrepor -- senao a mudanca
    # seria uma regressao visivel na tela.
    antiga = {
        "zona_id": 1,
        "zona_nome": "Nome Antigo",
        "especie": "aves",
        **dados_entrada_db._CONFIG_PADRAO,
    }
    falsa = _ConexaoFalsa([antiga])
    monkeypatch.setattr(
        dados_entrada_db.db_backend, "abrir_conexao_postgres", lambda _schema: falsa
    )

    (config,) = dados_entrada_db.listar_configuracoes(
        [{"id": 1, "nome": "Galpão A", "especie": "bovinos"}]
    )

    assert config["zona_nome"] == "Galpão A"
    assert config["especie"] == "bovinos"
    assert not [c for c in falsa.comandos if _grava(c)]
