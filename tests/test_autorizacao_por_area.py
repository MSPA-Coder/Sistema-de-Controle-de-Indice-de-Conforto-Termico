"""Toda rota decide area, e nenhuma decide por omissao.

Este arquivo existe por causa de um defeito concreto: `AREA_POR_ENDPOINT` era
consultado com `.get(endpoint)` e endpoint ausente LIBERAVA. Seis leituras
ficaram de fora do mapa -- as quatro da aba Historico e as duas da aba
Operacao. O template escondia a aba de quem nao tem a area, e as rotas
continuavam entregando os dados; a escrita da mesma aba, no mesmo arquivo,
sempre exigiu area.

A suite nao apanhou porque o teste que existia lia o CODIGO-FONTE do hook e
conferia se as palavras "AREA_POR_ENDPOINT", "area_permitida(" e
"_negar_acesso()" apareciam nele. Todas apareciam. Um teste que confere se a
verificacao esta escrita nao responde se ela alcanca as rotas -- e a diferenca
entre as duas perguntas era exatamente o defeito.

Por isso o que se mede aqui e comportamento e cobertura do mapa, nao texto.
"""

from __future__ import annotations

import pytest

from app import auth


def _endpoints_da_aplicacao(app) -> set[str]:
    return {regra.endpoint for regra in app.url_map.iter_rules()}


def _classificados() -> set[str]:
    return (
        set(auth.AREA_POR_ENDPOINT)
        | set(auth.ENDPOINTS_ISENTOS_DE_LOGIN)
        | set(auth.ENDPOINTS_ABERTOS_A_QUALQUER_PERFIL)
    )


def test_toda_rota_esta_classificada(app):
    """Rota nova nasce negada; este teste diz qual foi esquecida.

    Sem a varredura, esquecer o mapeamento vira uma rota que nao funciona e so
    aparece quando alguem usa aquela tela. Com ela, aparece na hora e com o
    nome do endpoint.
    """
    faltando = sorted(_endpoints_da_aplicacao(app) - _classificados())

    assert not faltando, (
        f"Endpoints sem area declarada: {faltando}. Mapeie a area em "
        "AREA_POR_ENDPOINT, ou declare em ENDPOINTS_ABERTOS_A_QUALQUER_PERFIL "
        "com o motivo escrito."
    )


def test_listas_de_excecao_nao_apodrecem(app):
    """Endpoint declarado que nao existe mais e ficcao; classificado duas
    vezes e ambiguidade sobre qual regra vale."""
    existentes = _endpoints_da_aplicacao(app)

    inexistentes = sorted(_classificados() - existentes)
    assert not inexistentes, f"Declarados mas inexistentes na aplicacao: {inexistentes}"

    duplicados = sorted(
        set(auth.AREA_POR_ENDPOINT) & set(auth.ENDPOINTS_ABERTOS_A_QUALQUER_PERFIL)
    )
    assert not duplicados, f"Classificados como abertos E com area: {duplicados}"


def test_toda_area_do_mapa_de_perfis_e_exigida_por_alguma_rota():
    """Area que nenhuma rota exige nao restringe nada.

    Ela continua aparecendo na tabela de perfis e no formulario de usuario
    como se fosse um controle: tira-la de um perfil nao muda nada no servidor.
    E o mesmo problema da permissao orfa no ControleBancario, na forma que
    este projeto tem.
    """
    exigidas: set[str] = set()
    for valor in auth.AREA_POR_ENDPOINT.values():
        exigidas |= {valor} if isinstance(valor, str) else set(valor)

    declaradas = set().union(*auth.AREAS_POR_PERFIL.values())

    orfas = sorted(declaradas - exigidas)
    assert not orfas, (
        f"Areas que nenhuma rota exige: {orfas}. Ligue-as a alguma rota ou "
        "remova-as da tabela de perfis."
    )

    inexistentes = sorted(exigidas - declaradas)
    assert not inexistentes, (
        f"Rotas exigem areas que perfil nenhum tem: {inexistentes}. Nenhum "
        "usuario alcancaria essas rotas."
    )


# ---------------------------------------------------------------------------
# Comportamento: a recusa acontece de verdade, com sessao de verdade.
# ---------------------------------------------------------------------------


@pytest.fixture
def entrar(app, client, monkeypatch):
    """Deixa a sessao valida com o perfil pedido, sem tocar o banco."""

    def logar(perfil: str):
        monkeypatch.setattr(
            auth.db,
            "obter_usuario",
            lambda _id: {"id": 1, "nome": "Fulano", "login": "fulano", "perfil": perfil, "ativo": True},
        )
        with client.session_transaction() as sessao:
            sessao["usuario_id"] = 1
        return client

    return logar


#: Rotas de leitura que ficaram abertas, com a area que passaram a exigir.
LEITURAS_QUE_FICARAM_ABERTAS = [
    ("/api/historico-leituras", "historico"),
    ("/api/zonas/1/historico", "historico"),
    ("/api/zonas/1/agregados-15min", "historico"),
    ("/api/zonas/1/resumo-horario", "historico"),
    ("/api/operacao/status", "operacao"),
    ("/api/operacao/eventos", "operacao"),
]


@pytest.mark.parametrize("caminho,area", LEITURAS_QUE_FICARAM_ABERTAS)
def test_perfil_sem_a_area_recebe_403_na_leitura(entrar, caminho, area):
    # "operador" nao tem "historico"; "gestor" nao tem "operacao".
    perfil = "operador" if area == "historico" else "gestor"
    assert not auth.area_permitida(perfil, area), (
        f"O teste pressupoe que {perfil} nao tem a area {area}"
    )

    resposta = entrar(perfil).get(caminho)

    assert resposta.status_code == 403, (
        f"{caminho} respondeu {resposta.status_code} para {perfil}, que nao tem a area {area}"
    )


@pytest.mark.parametrize("caminho,area", LEITURAS_QUE_FICARAM_ABERTAS)
def test_perfil_com_a_area_nao_e_barrado(entrar, caminho, area):
    # A contraprova: a correcao nao pode ter fechado a rota para quem a usa.
    # O administrador tem todas as areas; o que se mede e a ausencia do 403,
    # nao o corpo -- a consulta ao banco nao existe nesta suite.
    resposta = entrar("administrador").get(caminho)

    assert resposta.status_code != 403, f"{caminho} barrou o administrador"


def test_rota_nao_mapeada_e_negada(app, entrar, monkeypatch):
    """A negacao por padrao, medida diretamente.

    Uma rota registrada depois do mapa nao pode passar so por nao constar
    dele. Este teste registra uma rota de mentira e confere que ela e recusada
    ate para o administrador.
    """
    app.add_url_rule("/api/rota-inventada", endpoint="comum.rota_inventada", view_func=lambda: "oi")

    resposta = entrar("administrador").get("/api/rota-inventada")

    assert resposta.status_code == 403, (
        "Rota sem area declarada passou. O hook voltou a liberar por omissao."
    )
