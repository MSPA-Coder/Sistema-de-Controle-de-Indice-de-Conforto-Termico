"""Duas rotas apagam toda a série temporal de todas as zonas de uma vez --
`leituras`, `leituras_recentes_zona`, `agregados_15min` e `resumos_horarios`
(ver `app.database.leituras.limpar_historico`): `/api/dados-entrada/apagar-
historico` e `/api/reset`. Até este teste nascer, só a primeira validava a
confirmação no servidor -- `/api/reset` confiava inteiramente no
`confirm()` do navegador, que não impede nada contra uma chamada direta
(curl, clique repetido, script) com sessão válida.

`app_factory.confirmacao_de_exclusao_valida` é agora o mecanismo
compartilhado pelas duas rotas -- exatamente o que a suíte abaixo mede:
que `/api/reset` passou a exigi-lo, e que a rota irmã continua exigindo
também (nenhuma das duas regrediu na extração).

Chama as views diretamente dentro de `app.test_request_context(...)`, sem
passar pelo `test_client()`: a suíte não tem PostgreSQL por desenho (ver
`conftest.py`), e as duas rotas em teste tocam o banco só depois da
validação -- por isso `db.limpar_historico` é substituído por um espião
antes de cada chamada, em vez de precisar de sessão autenticada e token
CSRF de verdade para um POST/DELETE completo.
"""

from __future__ import annotations

from app.app_factory import confirmacao_de_exclusao_valida
from app.dados_entrada import rotas as dados_entrada_rotas
from app.ict import administracao


def test_confirmacao_aceita_apagar_maiusculo_sem_espacos():
    assert confirmacao_de_exclusao_valida({"confirmacao": "APAGAR"}) is True


def test_confirmacao_aceita_minusculas_e_espacos_nas_bordas():
    # O front nao normaliza o que a pessoa digita -- quem faz isso e o
    # servidor, entao "apagar" minusculo e com espaco nas bordas tem de valer
    # tanto quanto o texto exato do placeholder.
    assert confirmacao_de_exclusao_valida({"confirmacao": "  apagar  "}) is True


def test_confirmacao_recusa_texto_errado():
    assert confirmacao_de_exclusao_valida({"confirmacao": "apagar tudo"}) is False


def test_confirmacao_recusa_campo_ausente():
    assert confirmacao_de_exclusao_valida({}) is False


def test_reset_sem_confirmacao_e_recusado_e_nao_toca_no_banco(app, monkeypatch):
    chamadas = []
    monkeypatch.setattr(administracao.db, "limpar_historico", lambda: chamadas.append("limpou"))

    with app.test_request_context("/api/reset", method="POST", json={}):
        resposta, status = administracao.reset()

    assert status == 400
    assert resposta.get_json() == {"erro": "Digite APAGAR para confirmar a exclusão."}
    assert chamadas == []


def test_reset_com_texto_errado_e_recusado_e_nao_toca_no_banco(app, monkeypatch):
    chamadas = []
    monkeypatch.setattr(administracao.db, "limpar_historico", lambda: chamadas.append("limpou"))

    with app.test_request_context("/api/reset", method="POST", json={"confirmacao": "sim"}):
        resposta, status = administracao.reset()

    assert status == 400
    assert chamadas == []


def test_reset_com_confirmacao_correta_apaga_o_historico(app, monkeypatch):
    chamadas = []
    monkeypatch.setattr(administracao.db, "limpar_historico", lambda: chamadas.append("limpou"))

    with app.test_request_context("/api/reset", method="POST", json={"confirmacao": "APAGAR"}):
        resposta = administracao.reset()

    assert resposta.get_json() == {"ok": True}
    assert chamadas == ["limpou"]


def test_apagar_historico_dados_entrada_continua_exigindo_confirmacao(app, monkeypatch):
    """Regressão: a extração do helper não pode ter afrouxado a rota irmã."""
    chamadas = []
    monkeypatch.setattr(dados_entrada_rotas.db, "contar_leituras", lambda: 10)
    monkeypatch.setattr(
        dados_entrada_rotas.db, "limpar_historico", lambda: chamadas.append("limpou")
    )

    with app.test_request_context(
        "/api/dados-entrada/apagar-historico", method="DELETE", json={}
    ):
        resposta, status = dados_entrada_rotas.apagar_historico()

    assert status == 400
    assert chamadas == []
