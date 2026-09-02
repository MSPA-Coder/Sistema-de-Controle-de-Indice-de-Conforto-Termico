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
from flask import url_for
from sharedauth.session import marca_de_sessao

from app import (
    auth,
    dados_entrada_rotas,
    database,
    database_configuracoes,
    database_zonas,
    rotas_comuns,
)


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


def test_area_dashboard_e_universal_e_so_de_leitura(app):
    """CT-05: "dashboard" equivale a "qualquer conta autenticada".

    A propriedade tem duas metades, e as duas precisam continuar valendo: (a)
    todo perfil tem "dashboard" -- um perfil novo sem ela quebraria a premissa
    silenciosamente; (b) nenhum endpoint mapeado nela é de escrita -- um POST
    ali ficaria aberto a qualquer pessoa logada, sem exceção nenhuma. Foi essa
    segunda metade, não verificada em lugar nenhum, que deixou `GET
    /api/zonas` (CT-01) passar despercebido por tanto tempo.
    """
    sem_dashboard = sorted(
        perfil for perfil, areas in auth.AREAS_POR_PERFIL.items() if "dashboard" not in areas
    )
    assert not sem_dashboard, (
        f"Perfis sem a área universal 'dashboard': {sem_dashboard}. Ou o perfil "
        "está errado, ou 'dashboard' deixou de ser universal e o comentário em "
        "AREAS_POR_PERFIL precisa mudar junto."
    )

    metodos_por_endpoint = {regra.endpoint: regra.methods for regra in app.url_map.iter_rules()}
    metodos_de_escrita = {"POST", "PUT", "PATCH", "DELETE"}
    endpoints_dashboard = [
        endpoint
        for endpoint, area in auth.AREA_POR_ENDPOINT.items()
        if area == "dashboard" or (isinstance(area, tuple) and "dashboard" in area)
    ]
    assert endpoints_dashboard, "'dashboard' parou de aparecer no mapa -- ajuste este teste"

    de_escrita = sorted(
        endpoint
        for endpoint in endpoints_dashboard
        if (metodos_por_endpoint.get(endpoint) or set()) & metodos_de_escrita
    )
    assert not de_escrita, (
        f"Endpoint(s) de escrita mapeados em 'dashboard': {de_escrita}. Isso "
        "abriria a ação para qualquer conta autenticada, sem exceção -- mova "
        "para uma área mais restrita."
    )


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
        # A sessao carrega tambem a marca da senha em vigor: sem ela, o
        # carregamento a recusa (ver `registrar_carregamento_usuario`). O hash
        # e substituido junto, para a marca ser calculavel sem banco.
        monkeypatch.setattr(auth.db, "obter_hash_de_senha", lambda _id: "hash-de-teste")
        with client.session_transaction() as sessao:
            sessao["usuario_id"] = 1
            sessao[auth.CHAVE_MARCA_DE_SENHA] = marca_de_sessao(
                "hash-de-teste", chave_secreta=app.secret_key
            )
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


# ---------------------------------------------------------------------------
# A CARGA tambem precisa caber na area que libera a rota
#
# O mapa de areas responde "quem entra". Ele nao responde "o que sai" -- e foi
# nessa distancia que `GET /api/zonas` ficou entregando a fiacao Modbus a todos
# os seis perfis: a rota esta corretamente mapeada em `dashboard`, e o problema
# era a carga nao caber nessa area.
# ---------------------------------------------------------------------------

#: O endereco do equipamento na rede industrial. Junto, e o bastante para falar
#: com ele sem passar por esta aplicacao.
FIACAO_MODBUS = frozenset(
    {
        "host",
        "porta",
        "porta_serial",
        "baud_rate",
        "unidade_id",
        "tipo_registrador",
        "endereco_registrador",
    }
)


def test_colunas_publicas_de_equipamento_nao_trazem_fiacao():
    """Invariante barata: ninguem acrescenta `host` a lista publica sem ver isto."""
    publicas = set(database_zonas.COLUNAS_EQUIPAMENTO_SEM_FIACAO)

    assert not publicas & FIACAO_MODBUS, (
        f"Campos de fiacao na lista publica de equipamento: "
        f"{sorted(publicas & FIACAO_MODBUS)}"
    )


@pytest.mark.parametrize(
    "perfil,espera_fiacao",
    [
        ("operador", False),
        ("gestor", False),
        ("veterinario", False),
        ("analista", False),
        ("tecnico", True),
        ("administrador", True),
    ],
)
def test_listagem_de_zonas_so_traz_fiacao_para_quem_tem_cadastro(
    entrar, monkeypatch, perfil, espera_fiacao
):
    """`GET /api/zonas` e liberada por `dashboard`, que os seis perfis tem.

    A fiacao pertence a `cadastro` -- e o que `administracao.obter_zona`
    restringe a tecnico e administrador. Ate 01/09/2026 a rota de TODAS as
    zonas entregava exatamente o que a rota de UMA protegia.
    """
    assert auth.area_permitida(perfil, "dashboard"), (
        f"O teste pressupoe que {perfil} alcanca a rota"
    )
    assert auth.area_permitida(perfil, "cadastro") is espera_fiacao, (
        f"O teste pressupoe que {perfil} {'tem' if espera_fiacao else 'nao tem'} `cadastro`"
    )

    pedidos: list[dict] = []

    def _listar_zonas(**argumentos):
        pedidos.append(argumentos)
        return []

    monkeypatch.setattr(rotas_comuns.db, "listar_zonas", _listar_zonas)

    resposta = entrar(perfil).get("/api/zonas")

    assert resposta.status_code == 200
    assert pedidos == [{"com_fiacao": espera_fiacao}], (
        f"{perfil} recebeu com_fiacao={pedidos}"
    )


# ---------------------------------------------------------------------------
# A mesma pergunta, agora em TODOS os endpoints do mapa -- nao so /api/zonas
#
# O teste acima fixa o CONTRATO exato de uma rota (chama com `com_fiacao=`
# tal). O que falta, e o que a recomendacao P1 e a issue 2 pedem, e a rede
# generica: percorrer CADA endpoint GET de AREA_POR_ENDPOINT com CADA um dos
# seis perfis e afirmar sobre as CHAVES devolvidas, nao so sobre o status.
#
# A lista de endpoints vem do PROPRIO AREA_POR_ENDPOINT (parametrize le o
# dict no momento da coleta dos testes) -- um endpoint novo mapeado entra
# aqui sozinho, sem editar nada neste arquivo.
# ---------------------------------------------------------------------------

#: Equipamento com a fiacao Modbus completa -- o mesmo formato que
#: `obter_zona`/`listar_zonas(com_fiacao=True)` devolvem de verdade. Usado
#: para popular os dois unicos pontos de leitura que realmente tocam a
#: tabela `equipamentos`; os demais mocks abaixo devolvem colecao vazia
#: porque a tabela que consultam de verdade (leituras, eventos, auditoria,
#: configuracoes) nao tem essas colunas -- nao ha o que vazar por ali.
_EQUIPAMENTO_COM_FIACAO = {
    "id": 1,
    "zona_id": 1,
    "tipo": "ventilador",
    "nome": "Equipamento de teste",
    "campo_medido": None,
    "modo_conexao": "tcp",
    "host": "10.0.0.5",
    "porta": 502,
    "porta_serial": None,
    "baud_rate": None,
    "unidade_id": 1,
    "tipo_registrador": "holding",
    "endereco_registrador": 10,
}


def _fake_listar_zonas(*, apenas_ativas=False, com_fiacao=False):
    # Mesmo contrato da funcao real (database_zonas.listar_zonas): so traz
    # fiacao quando pedida explicitamente. E o comportamento deste `if` que
    # protege /api/zonas, e e ele que este fake precisa reproduzir para o
    # teste continuar significativo.
    equipamento = dict(_EQUIPAMENTO_COM_FIACAO)
    if not com_fiacao:
        equipamento = {
            campo: equipamento[campo] for campo in database_zonas.COLUNAS_EQUIPAMENTO_SEM_FIACAO
        }
    return [{"id": 1, "nome": "Zona de teste", "equipamentos": [equipamento]}]


def _fake_obter_zona(zona_id):
    # Ao contrario de `listar_zonas`, a funcao real NUNCA filtra a fiacao
    # aqui -- quem restringe e a area `cadastro` do endpoint, nao a funcao.
    return {"id": zona_id, "nome": "Zona de teste", "equipamentos": [dict(_EQUIPAMENTO_COM_FIACAO)]}


@pytest.fixture
def leituras_da_aplicacao(monkeypatch):
    """Troca toda funcao de leitura usada pelas rotas GET do mapa por um
    retorno minimo, para exercitar as rotas sem PostgreSQL (nao ha banco
    real nesta suite -- ver conftest.py).

    Patchear `database.<nome>` (o modulo, nao o alias `db` de cada arquivo
    de rotas) alcanca todo mundo: `rotas_comuns`, `ict/rotas`,
    `ict/administracao` e `dados_entrada_rotas` importam com
    `from . import database as db`, que so cria um APELIDO para o mesmo
    objeto de modulo -- o atributo consultado em `db.funcao()` e sempre o
    do modulo `database`, mesmo depois do patch.
    """
    monkeypatch.setattr(database, "listar_zonas", _fake_listar_zonas)
    monkeypatch.setattr(database, "obter_zona", _fake_obter_zona)
    monkeypatch.setattr(database, "obter_estatisticas_zonas", lambda: [])
    monkeypatch.setattr(database, "obter_painel_zonas", lambda: [])
    monkeypatch.setattr(
        database, "obter_configuracoes", lambda *a, **k: dict(database_configuracoes.CONFIGURACOES_PADRAO)
    )
    monkeypatch.setattr(database, "obter_status_coletor", lambda: {})
    monkeypatch.setattr(database, "obter_estado_operacional_zonas", lambda: [])
    monkeypatch.setattr(database, "listar_eventos_operacao", lambda *a, **k: [])
    monkeypatch.setattr(database, "obter_leituras_recentes_zona", lambda *a, **k: [])
    monkeypatch.setattr(database, "obter_historico_por_zona", lambda *a, **k: [])
    monkeypatch.setattr(database, "obter_historico_leituras", lambda *a, **k: {})
    monkeypatch.setattr(database, "obter_agregados_15min", lambda *a, **k: [])
    monkeypatch.setattr(database, "obter_resumos_horarios", lambda *a, **k: [])
    monkeypatch.setattr(database, "obter_historicos_recentes_zonas", lambda *a, **k: {})
    monkeypatch.setattr(database, "listar_eventos_auditoria", lambda *a, **k: [])
    monkeypatch.setattr(database, "listar_usuarios", lambda: [])
    monkeypatch.setattr(dados_entrada_rotas.dados_db, "listar_configuracoes", lambda *a, **k: [])
    monkeypatch.setattr(dados_entrada_rotas.dados_db, "listar_execucoes", lambda *a, **k: [])
    monkeypatch.setattr(
        dados_entrada_rotas.dados_db, "iterar_medicoes_csv", lambda *a, **k: (["execucao_id"], iter([]))
    )


def _chaves_recursivas(valor) -> set[str]:
    """Todas as chaves de dict encontradas em `valor`, em qualquer profundidade."""
    chaves: set[str] = set()
    if isinstance(valor, dict):
        chaves |= set(valor.keys())
        for sub in valor.values():
            chaves |= _chaves_recursivas(sub)
    elif isinstance(valor, list):
        for item in valor:
            chaves |= _chaves_recursivas(item)
    return chaves


@pytest.mark.parametrize("perfil", sorted(auth.AREAS_POR_PERFIL))
@pytest.mark.parametrize("endpoint", sorted(auth.AREA_POR_ENDPOINT))
def test_leitura_do_mapa_nao_vaza_campo_de_outra_area(
    app, entrar, leituras_da_aplicacao, endpoint, perfil
):
    """Para CADA endpoint GET do mapa e CADA perfil: quem entra, e o que sai.

    `entrar` e `leituras_da_aplicacao` sao independentes (a sessao nao muda
    o que o banco -- aqui, o mock -- devolve), entao a combinacao das duas
    fixtures cobre exatamente o que a issue 2 pediu: exercitar a rota de
    verdade, com sessao de verdade, sem precisar de PostgreSQL.
    """
    regra = next((r for r in app.url_map.iter_rules() if r.endpoint == endpoint), None)
    assert regra is not None, f"{endpoint} esta em AREA_POR_ENDPOINT mas nao tem rota registrada"
    if "GET" not in regra.methods:
        pytest.skip(f"{endpoint} nao aceita GET; fica para uma rede de mutacoes, se um dia existir")

    valores = dict.fromkeys(regra.arguments, 1)
    with app.test_request_context():
        url = url_for(endpoint, **valores)

    area_exigida = auth.AREA_POR_ENDPOINT[endpoint]
    areas_aceitas = (area_exigida,) if isinstance(area_exigida, str) else area_exigida
    tem_acesso = any(auth.area_permitida(perfil, area) for area in areas_aceitas)

    resposta = entrar(perfil).get(url)

    if not tem_acesso:
        # `_negar_acesso` (app/auth.py) responde diferente por FORMA da rota,
        # nao por area: 403 sob `/api/`, redirect nas paginas Jinja fora dela
        # (ex.: `usuarios.pagina_usuarios`). As duas recusam a mesma coisa; um
        # redirect nao carrega a pagina protegida no corpo, entao nao ha o que
        # escanear por campo vazado nesse caso.
        esperado = 403 if regra.rule.startswith("/api/") else 302
        assert resposta.status_code == esperado, (
            f"{endpoint} respondeu {resposta.status_code} para {perfil}, que nao tem "
            f"nenhuma das areas {areas_aceitas} (esperava {esperado})"
        )
        return

    assert resposta.status_code != 403, f"{endpoint} barrou {perfil}, que tem {areas_aceitas}"

    if not resposta.is_json:
        return  # Pagina HTML (usuarios.pagina_usuarios) ou CSV (exportar_csv).

    if auth.area_permitida(perfil, "cadastro"):
        # Tem o direito de ver fiacao onde ela existir de verdade (ex.:
        # administracao.obter_zona) -- nao ha o que proibir aqui.
        return

    vazadas = _chaves_recursivas(resposta.get_json()) & FIACAO_MODBUS
    assert not vazadas, (
        f"{endpoint} devolveu {sorted(vazadas)} para {perfil}, que nao tem a area 'cadastro'. "
        "Isso e exatamente o defeito de CT-01, agora por outra rota."
    )
