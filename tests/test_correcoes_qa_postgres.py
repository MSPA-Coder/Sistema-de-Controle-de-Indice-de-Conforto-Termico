"""Correções da rodada de testes de 21/10/2026 que só o PostgreSQL mostra.

ACL das leituras agregadas, revogação de sessão no logout, trilha de auditoria
com autor e eventos de conta, e as recusas de cadastro que apontam o campo.
Mesmo padrão de `test_acl_zonas_http_postgres.py`: aplicação, coletor e banco
de verdade, sem mocks.
"""

from __future__ import annotations

import re
from uuid import uuid4

import pytest
from test_cadastro_http_postgres import acesso as acesso
from test_cadastro_http_postgres import equipamento, zona
from test_operacao_http_postgres import ponte as ponte

from app import database as db
from app.seguranca import auth

pytestmark = pytest.mark.usefixtures("banco")

SENHA = "Senha-sintetica-conta-2026!"
ENTRADAS = {"entradas": {"tbs": 30, "tbu": 22}}


def _token(cliente, caminho="/preferencias") -> str:
    html = cliente.get(caminho).get_data(as_text=True)
    return re.search(r'name="_csrf_token"[^>]*value="([^"]+)"', html).group(1)


def _entrar(app, login, senha=SENHA):
    cliente = app.test_client()
    resposta = cliente.post(
        "/login", data={"login": login, "senha": senha, "_csrf_token": _token(cliente, "/login")}
    )
    assert resposta.status_code == 302
    return cliente, {"X-CSRF-Token": _token(cliente)}


@pytest.fixture
def criar_conta(ponte, banco):
    """(admin, cabeçalhos do admin, criar) -- `criar(perfil, zonas)` devolve uma conta logada."""
    (admin, headers), _, _ = ponte
    criados: list[int] = []

    def criar(perfil: str, zonas=()):
        login = f"qa-{perfil}-{uuid4().hex[:8]}"
        usuario = db.criar_usuario(
            {
                "nome": f"QA {perfil}",
                "login": login,
                "perfil": perfil,
                "senha_hash": auth.gerar_hash_senha(SENHA),
            },
            exigir_troca=False,
        )
        criados.append(usuario["id"])
        for zona_id in zonas:
            db.conceder_acesso_zona(usuario["id"], zona_id)
        cliente, cabecalhos = _entrar(admin.application, login)
        return cliente, cabecalhos, usuario["id"], login

    yield admin, headers, criar
    with banco() as conn:
        for uid in criados:
            conn.execute("DELETE FROM usuarios WHERE id=?", (uid,))


def _duas_zonas_com_leitura(admin, headers):
    a = db.criar_zona(zona("QA A"))["id"]
    b = db.criar_zona(zona("QA B"))["id"]
    for zona_id in (a, b):
        resposta = admin.post(f"/api/zonas/{zona_id}/calcular", json=ENTRADAS, headers=headers)
        assert resposta.status_code == 200
    return a, b


# ---------------------------------------------------------------------------
# Defeito 1: a ACL de zona vale nas leituras que listam várias zonas
# ---------------------------------------------------------------------------


def test_leituras_agregadas_so_mostram_as_zonas_liberadas(criar_conta):
    admin, headers, criar = criar_conta
    a, b = _duas_zonas_com_leitura(admin, headers)
    gestor, _, _, _ = criar("gestor", zonas=[a])
    sem_zona, _, _, _ = criar("gestor")

    assert {z["id"] for z in admin.get("/api/zonas").json} == {a, b}
    assert [z["id"] for z in gestor.get("/api/zonas").json] == [a]
    assert sem_zona.get("/api/zonas").json == []

    assert set(gestor.get("/api/zonas/historicos-recentes").json) == {str(a)}
    assert sem_zona.get("/api/zonas/historicos-recentes").json == {}

    historico = gestor.get("/api/historico-leituras?limite=50").json
    assert historico["total"] == 1
    assert {leitura["zona_id"] for leitura in historico["leituras"]} == {a}
    assert gestor.get(f"/api/historico-leituras?zona_id={b}").status_code == 403
    assert sem_zona.get("/api/historico-leituras").json["total"] == 0
    assert admin.get("/api/historico-leituras?limite=50").json["total"] == 2

    assert [z["zona_id"] for z in gestor.get("/api/analises").json] == [a]
    assert [z["zona_id"] for z in gestor.get("/api/analises/painel-executivo").json] == [a]
    assert sem_zona.get("/api/analises").json == []
    assert sem_zona.get("/api/analises/painel-executivo").json == []
    assert {z["zona_id"] for z in admin.get("/api/analises").json} == {a, b}


def test_operacao_so_mostra_as_zonas_liberadas(criar_conta):
    admin, headers, criar = criar_conta
    a = db.criar_zona(zona("QA A"))["id"]
    b = db.criar_zona(zona("QA B"))["id"]
    db.registrar_evento_operacao("comando", "ventilador_ligado", zona_id=a)
    db.registrar_evento_operacao("comando", "ventilador_ligado", zona_id=b)
    operador, _, _, _ = criar("operador", zonas=[a])

    assert [z["zona_id"] for z in operador.get("/api/operacao/status").json["zonas"]] == [a]
    assert {e["zona_id"] for e in operador.get("/api/operacao/eventos").json} == {a}
    assert operador.get(f"/api/operacao/eventos?zona_id={b}").status_code == 403
    assert {e["zona_id"] for e in admin.get("/api/operacao/eventos").json} == {a, b}


def test_dados_de_entrada_so_mostram_as_zonas_liberadas(criar_conta):
    admin, _, criar = criar_conta
    a = db.criar_zona(zona("QA A"))["id"]
    b = db.criar_zona(zona("QA B"))["id"]
    analista, _, _, _ = criar("analista", zonas=[a])
    sem_zona, _, _, _ = criar("analista")

    assert {c["zona_id"] for c in admin.get("/api/dados-entrada/configuracoes").json} == {a, b}
    assert [c["zona_id"] for c in analista.get("/api/dados-entrada/configuracoes").json] == [a]
    assert sem_zona.get("/api/dados-entrada/configuracoes").json == []


# ---------------------------------------------------------------------------
# Defeito 8 e 11: datas nos extremos e tetos de `limite`
# ---------------------------------------------------------------------------


def test_data_fim_no_extremo_do_calendario_responde_200(criar_conta):
    admin, headers, _ = criar_conta
    a, _ = _duas_zonas_com_leitura(admin, headers)
    assert admin.get("/api/historico-leituras?data_fim=9999-12-31").status_code == 200
    assert admin.get(f"/api/zonas/{a}/resumo-horario?data_fim=9999-12-31").status_code == 200
    assert admin.get("/api/historico-leituras?data_inicio=0001-01-01").status_code == 200


def test_limite_sem_teto_e_reduzido(criar_conta):
    admin, headers, _ = criar_conta
    a, _ = _duas_zonas_com_leitura(admin, headers)
    assert admin.get("/api/historico-leituras?limite=999999").json["limite"] == 200
    assert admin.get(f"/api/zonas/{a}/agregados-15min?limite=999999").status_code == 200
    assert admin.get(f"/api/zonas/{a}/resumo-horario?limite=-5").status_code == 200


def test_paginacao_devolve_o_deslocamento_real_da_janela(criar_conta):
    """O servidor ancora a ultima janela no fim: quem pagina usa o `deslocamento` devolvido."""
    admin, headers, _ = criar_conta
    _duas_zonas_com_leitura(admin, headers)
    pagina = admin.get("/api/historico-leituras?limite=1&deslocamento=999").json
    assert pagina["total"] == 2
    assert pagina["deslocamento"] == 1 and len(pagina["leituras"]) == 1


# ---------------------------------------------------------------------------
# Defeito 9, 10 e U2: recusas de cadastro apontam o campo
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "corpo,campo",
    [
        ({"nome": None, "especie": "frangos", "indice": "ITU"}, "nome"),
        ({"nome": "a\u0000b", "especie": "frangos", "indice": "ITU"}, "nome"),
        ({"nome": "QA", "especie": "frangos", "indice": "ITU", "ativa": "talvez"}, "ativa"),
    ],
)
def test_zona_invalida_responde_400_com_campo_e_mensagem(criar_conta, corpo, campo):
    admin, headers, _ = criar_conta
    resposta = admin.post("/api/zonas", json=corpo, headers=headers)
    assert resposta.status_code == 400
    assert resposta.json["campo"] == campo
    assert resposta.json["erro"] != "Os dados da zona são inválidos."


@pytest.mark.parametrize(
    "host", ["http://evil/", "999.999.999.999", "192.168.11.3.1", "a b", "x" * 5000, ""]
)
def test_equipamento_com_host_invalido_e_recusado(criar_conta, host):
    admin, headers, _ = criar_conta
    zona_id = db.criar_zona(zona())["id"]
    resposta = admin.post(
        f"/api/zonas/{zona_id}/equipamentos", json=equipamento(host=host), headers=headers
    )
    assert resposta.status_code == 400
    assert resposta.json["campo"] == "host"
    assert db.obter_zona(zona_id)["equipamentos"] == []


def test_equipamento_com_host_valido_e_aceito(criar_conta):
    admin, headers, _ = criar_conta
    zona_id = db.criar_zona(zona())["id"]
    for host in ("192.168.0.10", "clp-galpao1", "plc.local"):
        resposta = admin.post(
            f"/api/zonas/{zona_id}/equipamentos", json=equipamento(host=host), headers=headers
        )
        assert resposta.status_code == 201, host


def test_gerar_dados_diz_o_que_corrigir(criar_conta):
    admin, headers, _ = criar_conta
    resposta = admin.post("/api/dados-entrada/gerar", json={}, headers=headers)
    assert resposta.status_code == 400
    assert "zona" in resposta.json["erro"].lower()


# ---------------------------------------------------------------------------
# Defeito 5: o logout encerra a sessão no servidor
# ---------------------------------------------------------------------------


def test_cookie_guardado_antes_do_logout_deixa_de_valer(criar_conta):
    admin, _, criar = criar_conta
    cliente, cabecalhos, _, _ = criar("gestor")
    nome_cookie = admin.application.config["SESSION_COOKIE_NAME"]
    copia = cliente.get_cookie(nome_cookie).value

    outro = admin.application.test_client()
    outro.set_cookie(nome_cookie, copia)
    assert outro.get("/preferencias").status_code == 200  # a cópia funciona enquanto há sessão

    assert cliente.post("/logout", headers=cabecalhos).status_code == 302

    reutilizado = admin.application.test_client()
    reutilizado.set_cookie(nome_cookie, copia)
    resposta = reutilizado.get("/preferencias")
    assert resposta.status_code == 302 and "/login" in resposta.location


def test_logout_de_uma_sessao_nao_derruba_as_outras_da_mesma_conta(criar_conta):
    admin, _, criar = criar_conta
    primeira, cabecalhos, _, login = criar("gestor")
    segunda, _ = _entrar(admin.application, login)

    assert primeira.post("/logout", headers=cabecalhos).status_code == 302
    assert segunda.get("/preferencias").status_code == 200


# ---------------------------------------------------------------------------
# Defeito 4: a trilha de auditoria tem autor e cobre as ações de conta e de dados
# ---------------------------------------------------------------------------


def _eventos(**filtros):
    achados = db.listar_eventos_auditoria(500)
    return [
        e for e in achados if all(e.get(chave) == valor for chave, valor in filtros.items())
    ]


def test_trilha_grava_o_autor_real_das_acoes(criar_conta):
    admin, headers, criar = criar_conta
    cliente, cabecalhos, uid, login = criar("gestor")

    entrada = _eventos(evento="LOGIN_SUCESSO", ator_login=login)
    assert entrada and entrada[0]["ator_perfil"] == "gestor" and entrada[0]["ator_id"] == uid

    zona_id = admin.post("/api/zonas", json=zona("QA auditada"), headers=headers).json["id"]
    criada = [e for e in _eventos(evento="ZONA_CRIADA") if e["detalhes"].get("zona_id") == zona_id]
    assert criada, "a criação de zona precisa estar na trilha"
    assert criada[0]["ator_perfil"] == "administrador"
    assert criada[0]["ator_login"] not in {"unknown", "anonymous"}

    assert cliente.post("/logout", headers=cabecalhos).status_code == 302
    assert _eventos(evento="LOGOUT", ator_login=login)


def test_trilha_registra_falha_de_login_sem_vazar_a_senha(criar_conta):
    admin, _, criar = criar_conta
    _, _, _, login = criar("gestor")
    anonimo = admin.application.test_client()
    resposta = anonimo.post(
        "/login",
        data={"login": login, "senha": "senha-errada-123", "_csrf_token": _token(anonimo, "/login")},
    )
    assert resposta.status_code == 200
    falhas = [e for e in _eventos(evento="LOGIN_FALHA") if e["detalhes"].get("login") == login]
    assert falhas and falhas[0]["sucesso"] is False
    assert "senha-errada-123" not in str(falhas[0])


def test_trilha_cobre_conta_zonas_senha_e_exclusao(criar_conta):
    admin, headers, criar = criar_conta
    zona_id = db.criar_zona(zona("QA conta"))["id"]
    _, _, uid, login = criar("operador")

    resposta = admin.post(
        f"/usuarios/{uid}/zonas", data={"zona": [str(zona_id)]}, headers=headers
    )
    assert resposta.status_code == 302
    assert db.usuario_tem_acesso_zona(uid, zona_id)
    alteradas = [e for e in _eventos(evento="ZONAS_DA_CONTA_ALTERADAS") if e["detalhes"].get("login") == login]
    assert alteradas and alteradas[0]["detalhes"]["concedidas"] == [zona_id]

    assert admin.post(f"/usuarios/{uid}/redefinir-senha", headers=headers).status_code == 200
    assert [e for e in _eventos(evento="SENHA_REDEFINIDA") if e["detalhes"].get("login") == login]

    assert admin.post(f"/usuarios/{uid}/excluir", headers=headers).status_code == 302
    assert [e for e in _eventos(evento="USUARIO_EXCLUIDO") if e["detalhes"].get("usuario_id") == uid]


def test_trilha_cobre_criacao_e_edicao_de_conta(criar_conta):
    admin, headers, _ = criar_conta
    login = "qa-novo-" + uuid4().hex[:8]
    resposta = admin.post(
        "/usuarios/novo",
        data={"nome": "QA Novo", "login": login, "perfil": "gestor", "senha": SENHA, "ativo": "on"},
        headers=headers,
    )
    assert resposta.status_code == 302
    try:
        assert [e for e in _eventos(evento="USUARIO_CRIADO") if e["detalhes"].get("login") == login]
        uid = db.obter_usuario_por_login(login)["id"]
        resposta = admin.post(
            f"/usuarios/{uid}/editar",
            data={"nome": "QA Novo", "login": login, "perfil": "analista", "ativo": "on"},
            headers=headers,
        )
        assert resposta.status_code == 302
        atualizados = [e for e in _eventos(evento="USUARIO_ATUALIZADO") if e["detalhes"].get("login") == login]
        assert atualizados and atualizados[0]["detalhes"]["perfil"] == "analista"
    finally:
        usuario = db.obter_usuario_por_login(login)
        if usuario:
            db.excluir_usuario(usuario["id"])


# ---------------------------------------------------------------------------
# U1: a tela de zonas da conta
# ---------------------------------------------------------------------------


def test_tela_de_zonas_da_conta_concede_e_revoga(criar_conta):
    admin, headers, criar = criar_conta
    a = db.criar_zona(zona("QA A"))["id"]
    b = db.criar_zona(zona("QA B"))["id"]
    _, _, uid, _ = criar("operador", zonas=[a])

    pagina = admin.get(f"/usuarios/{uid}/zonas").get_data(as_text=True)
    assert "QA A" in pagina and "QA B" in pagina
    assert re.search(rf'value="{a}"\s+checked', pagina)
    assert not re.search(rf'value="{b}"\s+checked', pagina)

    assert admin.post(f"/usuarios/{uid}/zonas", data={"zona": [str(b)]}, headers=headers).status_code == 302
    assert [z["id"] for z in db.listar_zonas_do_usuario(uid)] == [b]
    assert admin.post(f"/usuarios/{uid}/zonas", data={}, headers=headers).status_code == 302
    assert db.listar_zonas_do_usuario(uid) == []
    # id inventado no formulário não cria vínculo
    admin.post(f"/usuarios/{uid}/zonas", data={"zona": ["2147483647", "abc"]}, headers=headers)
    assert db.listar_zonas_do_usuario(uid) == []


def test_lista_de_usuarios_mostra_quantas_zonas_cada_conta_tem(criar_conta):
    admin, _, criar = criar_conta
    a = db.criar_zona(zona("QA A"))["id"]
    db.criar_zona(zona("QA B"))
    _, _, _, com_zona = criar("operador", zonas=[a])
    _, _, _, sem_zona = criar("operador")

    pagina = admin.get("/usuarios/").get_data(as_text=True)
    linha = lambda login: re.search(rf"<tr>(?:(?!</tr>).)*{login}(?:(?!</tr>).)*</tr>", pagina, re.S).group(0)  # noqa: E731
    assert "1 de 2" in linha(com_zona)
    assert "Nenhuma" in linha(sem_zona)
    assert "Todas" in re.sub(r"\s+", " ", pagina)  # o administrador logado
