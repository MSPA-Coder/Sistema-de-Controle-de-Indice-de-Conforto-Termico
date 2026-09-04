"""Senha redefinida por administrador vale ate o primeiro acesso.

Quando um administrador redefine a senha de alguem, essa senha passa a ser
conhecida por duas pessoas. A obrigacao de trocar existe para encurtar essa
janela -- e so vale se for verificada em TODA requisicao. Aplicar o desvio
apenas no login e a falha silenciosa que este arquivo mede: a marca fica
ligada, a tela some da frente, e a pessoa segue usando a senha que o
administrador conhece.

A suite nao tem banco (ver `conftest.py`), entao a camada de persistencia e
substituida; o que se exercita aqui e a decisao do portao e das rotas.
"""

from __future__ import annotations

import pytest
from sharedauth.session import marca_de_sessao

from app.seguranca import auth

#: Hash fixo para o carregamento da sessao conferir a marca sem tocar o banco.
HASH_EM_VIGOR = "hash-de-teste"


def _usuario(*, perfil: str = "administrador", trocar: bool = False) -> dict:
    return {
        "id": 1,
        "nome": "Fulano",
        "login": "fulano",
        "perfil": perfil,
        "ativo": True,
        "trocar_senha": trocar,
    }


@pytest.fixture
def entrar(app, client, monkeypatch):
    """Sessao valida, com ou sem troca pendente, sem tocar o banco."""

    def logar(*, perfil: str = "administrador", trocar: bool = False):
        monkeypatch.setattr(
            auth.db, "obter_usuario", lambda _id: _usuario(perfil=perfil, trocar=trocar)
        )
        monkeypatch.setattr(auth.db, "obter_hash_de_senha", lambda _id: HASH_EM_VIGOR)
        with client.session_transaction() as sessao:
            sessao["usuario_id"] = 1
            sessao[auth.CHAVE_MARCA_DE_SENHA] = marca_de_sessao(
                HASH_EM_VIGOR, chave_secreta=app.secret_key
            )
        return client

    return logar


# --- o portao ------------------------------------------------------------


def test_marca_ligada_desvia_qualquer_rota_para_a_troca(entrar):
    cliente = entrar(trocar=True)

    resposta = cliente.get("/usuarios/", follow_redirects=False)

    assert resposta.status_code == 302
    assert resposta.headers["Location"] == "/minha-senha"


def test_marca_desligada_nao_atrapalha(entrar):
    cliente = entrar(trocar=False)

    # `comum.index` e a casca da SPA, aberta a qualquer perfil e sem consulta
    # ao banco -- serve para provar que o portao deixou passar.
    assert cliente.get("/").status_code == 200


def test_a_tela_de_troca_nao_entra_em_laco(entrar):
    # A tela que existe para sair da situacao nao pode redirecionar para si
    # mesma. `sharedauth.access` isenta `endpoint_troca` automaticamente.
    cliente = entrar(trocar=True)

    assert cliente.get("/minha-senha").status_code == 200


def test_logout_funciona_de_dentro_da_trava(app, entrar):
    # Sem isto a pessoa fica presa dentro do aplicativo: todo destino devolve
    # para a tela de troca, inclusive a saida.
    app.config["WTF_CSRF_ENABLED"] = False
    cliente = entrar(trocar=True)

    resposta = cliente.post("/logout", follow_redirects=False)

    assert resposta.status_code == 302
    assert "/login" in resposta.headers["Location"]


@pytest.mark.parametrize(
    "rota",
    ["/static/css/style.css", "/sharedauth/ui/sharedauth-ui.css", "/favicon.ico"],
)
def test_estaticos_ficam_isentos(entrar, rota):
    # Sem eles a tela de troca chega sem CSS e sem o componente de aviso.
    cliente = entrar(trocar=True)

    resposta = cliente.get(rota)

    assert resposta.status_code != 302, f"{rota} foi desviada para a troca"


def test_rota_de_api_com_marca_ligada_responde_403_json(entrar):
    # 403 e nao 401: a sessao vale, a identidade esta estabelecida -- entrar de
    # novo nao resolveria. A chave "erro" e a convencao deste app.
    cliente = entrar(trocar=True)

    resposta = cliente.get("/api/zonas")

    assert resposta.status_code == 403
    assert resposta.get_json() == {"erro": "Troca de senha obrigatória."}


def test_anonimo_continua_indo_para_o_login(client):
    # O portao da troca nao pode roubar o caso do anonimo: quem nao entrou nao
    # tem senha a trocar.
    resposta = client.get("/usuarios/", follow_redirects=False)

    assert resposta.status_code == 302
    assert "/login" in resposta.headers["Location"]


def test_a_trava_roda_antes_do_controle_de_area(entrar):
    # Um operador nao tem a area "usuarios". Com a senha vencida, o desvio para
    # a troca tem de vir ANTES da recusa por perfil: mandar essa pessoa para a
    # SPA esconderia a unica coisa que ela precisa fazer.
    cliente = entrar(perfil="operador", trocar=True)

    resposta = cliente.get("/usuarios/", follow_redirects=False)

    assert resposta.headers["Location"] == "/minha-senha"


def test_a_tela_de_troca_vale_para_qualquer_perfil(entrar):
    # Exigir a area "usuarios" aqui deixaria todo perfil que nao a tem preso na
    # trava, sem a tela que a resolve.
    assert "auth.trocar_senha" in auth.ENDPOINTS_ABERTOS_A_QUALQUER_PERFIL
    cliente = entrar(perfil="operador", trocar=True)

    assert cliente.get("/minha-senha").status_code == 200


# --- redefinicao pelo administrador --------------------------------------


def test_redefinir_gera_senha_temporaria_e_a_mostra_uma_vez(app, entrar, monkeypatch):
    app.config["WTF_CSRF_ENABLED"] = False
    gravado: dict = {}
    monkeypatch.setattr(
        auth.db,
        "redefinir_senha_usuario",
        lambda usuario_id, senha_hash: gravado.update(id=usuario_id, hash=senha_hash),
    )
    monkeypatch.setattr(auth.db, "listar_usuarios", lambda: [])
    cliente = entrar()

    resposta = cliente.post("/usuarios/2/redefinir-senha")
    corpo = resposta.get_data(as_text=True)

    assert resposta.status_code == 200
    assert "Senha temporária de fulano" in corpo
    assert gravado["id"] == 2
    # O hash foi gravado; a senha em texto claro so existe na resposta.
    assert gravado["hash"].startswith("scrypt:") or "$" in gravado["hash"]


def test_a_senha_temporaria_nao_e_a_gravada(app, entrar, monkeypatch):
    # O que vai para o banco e hash. Se um dia alguem gravar o valor "para
    # facilitar", este teste reprova.
    app.config["WTF_CSRF_ENABLED"] = False
    gravado: dict = {}
    monkeypatch.setattr(
        auth.db,
        "redefinir_senha_usuario",
        lambda usuario_id, senha_hash: gravado.update(hash=senha_hash),
    )
    monkeypatch.setattr(auth.db, "listar_usuarios", lambda: [])
    cliente = entrar()

    corpo = cliente.post("/usuarios/2/redefinir-senha").get_data(as_text=True)
    inicio = corpo.index('class="senha-temporaria-valor">') + len(
        'class="senha-temporaria-valor">'
    )
    senha = corpo[inicio : corpo.index("<", inicio)]

    assert senha and senha not in gravado["hash"]


def test_redefinir_exige_a_area_usuarios(app, entrar):
    # A acao continua sendo administracao de conta alheia.
    app.config["WTF_CSRF_ENABLED"] = False
    cliente = entrar(perfil="operador", trocar=False)

    resposta = cliente.post("/usuarios/2/redefinir-senha", follow_redirects=False)

    assert resposta.status_code == 302
    assert resposta.headers["Location"] == "/"


# --- troca feita pelo dono ------------------------------------------------


def _preparar_troca(monkeypatch, senha_atual: str, gravado: dict):
    monkeypatch.setattr(
        auth.db,
        "obter_usuario_por_login",
        lambda _login: {"id": 1, "senha_hash": auth.gerar_hash_senha(senha_atual)},
    )
    monkeypatch.setattr(
        auth.db,
        "trocar_senha_propria",
        lambda usuario_id, senha_hash: gravado.update(id=usuario_id, hash=senha_hash),
    )


def test_troca_correta_grava_e_redireciona(app, entrar, monkeypatch):
    app.config["WTF_CSRF_ENABLED"] = False
    gravado: dict = {}
    _preparar_troca(monkeypatch, "senha-temporaria", gravado)
    cliente = entrar(trocar=True)

    resposta = cliente.post(
        "/minha-senha",
        data={
            "senha_atual": "senha-temporaria",
            "senha_nova": "minha-senha-1",
            "senha_confirmacao": "minha-senha-1",
        },
        follow_redirects=False,
    )

    assert resposta.status_code == 302
    assert resposta.headers["Location"] == "/"
    assert gravado["id"] == 1


def test_troca_sem_a_senha_atual_correta_nao_grava(app, entrar, monkeypatch):
    # Sem esta conferencia, uma sessao sequestrada vira tomada de conta.
    app.config["WTF_CSRF_ENABLED"] = False
    gravado: dict = {}
    _preparar_troca(monkeypatch, "senha-temporaria", gravado)
    cliente = entrar(trocar=True)

    resposta = cliente.post(
        "/minha-senha",
        data={
            "senha_atual": "chute-errado",
            "senha_nova": "minha-senha-1",
            "senha_confirmacao": "minha-senha-1",
        },
    )

    assert resposta.status_code == 200
    assert "Senha atual inválida." in resposta.get_data(as_text=True)
    assert gravado == {}


def test_redigitar_a_senha_temporaria_nao_conclui_a_troca(app, entrar, monkeypatch):
    # O caso que esvaziaria a obrigacao: a marca se apagaria e a senha que o
    # administrador conhece continuaria valendo.
    app.config["WTF_CSRF_ENABLED"] = False
    gravado: dict = {}
    _preparar_troca(monkeypatch, "senha-temporaria", gravado)
    cliente = entrar(trocar=True)

    resposta = cliente.post(
        "/minha-senha",
        data={
            "senha_atual": "senha-temporaria",
            "senha_nova": "senha-temporaria",
            "senha_confirmacao": "senha-temporaria",
        },
    )

    assert "A nova senha deve ser diferente da senha atual." in resposta.get_data(
        as_text=True
    )
    assert gravado == {}


def test_confirmacao_divergente_nao_grava(app, entrar, monkeypatch):
    app.config["WTF_CSRF_ENABLED"] = False
    gravado: dict = {}
    _preparar_troca(monkeypatch, "senha-temporaria", gravado)
    cliente = entrar(trocar=True)

    cliente.post(
        "/minha-senha",
        data={
            "senha_atual": "senha-temporaria",
            "senha_nova": "minha-senha-1",
            "senha_confirmacao": "outra-coisa-2",
        },
    )

    assert gravado == {}


def test_senha_curta_nao_grava(app, entrar, monkeypatch):
    app.config["WTF_CSRF_ENABLED"] = False
    gravado: dict = {}
    _preparar_troca(monkeypatch, "senha-temporaria", gravado)
    cliente = entrar(trocar=True)

    cliente.post(
        "/minha-senha",
        data={
            "senha_atual": "senha-temporaria",
            "senha_nova": "curta12",
            "senha_confirmacao": "curta12",
        },
    )

    assert gravado == {}


# --- persistencia: o que o SQL declara -----------------------------------


def test_criar_usuario_liga_a_marca_por_padrao():
    # Conta nova tem senha que quem administra escolheu e conhece: e o mesmo
    # caso da redefinicao. O padrao e ligar, para que a tela -- e qualquer
    # caminho novo -- nasca protegida.
    import inspect

    from app.database import usuarios as database_usuarios

    assinatura = inspect.signature(database_usuarios.criar_usuario)

    assert assinatura.parameters["exigir_troca"].default is True
    assert "trocar_senha" in inspect.getsource(database_usuarios.criar_usuario)


def test_bootstrap_por_cli_nao_liga_a_marca():
    # Quem roda o script tem shell no conteiner e escolheu a propria senha:
    # nao existe o terceiro que a criacao pela tela pressupoe. Obrigar a
    # trocar ali deixaria o primeiro acesso com um passo a mais sem ganho.
    import inspect

    from scripts import criar_usuario_admin

    fonte = inspect.getsource(criar_usuario_admin.main)

    assert "exigir_troca=False" in fonte


def test_edicao_de_usuario_com_senha_tambem_liga_a_marca():
    # A tela nao expoe mais esse campo, mas a funcao continua aceitando-o: um
    # caminho que deixasse a senha alheia valendo para sempre seria uma porta
    # dos fundos silenciosa.
    import inspect

    from app.database import usuarios as database_usuarios

    fonte = inspect.getsource(database_usuarios.atualizar_usuario)

    assert "senha_hash = ?, trocar_senha = 1" in fonte


# --- a sessao deixa de valer quando a senha muda -------------------------


def test_sessao_com_a_marca_antiga_e_recusada(app, client, monkeypatch):
    # O caso que a mudanca existe para resolver: alguem entrou com a senha
    # antiga, o dono trocou, e a sessao daquele alguem tem de cair.
    monkeypatch.setattr(auth.db, "obter_usuario", lambda _id: _usuario())
    monkeypatch.setattr(auth.db, "obter_hash_de_senha", lambda _id: "hash-NOVO")
    with client.session_transaction() as sessao:
        sessao["usuario_id"] = 1
        sessao[auth.CHAVE_MARCA_DE_SENHA] = marca_de_sessao(
            "hash-ANTIGO", chave_secreta=app.secret_key
        )

    resposta = client.get("/usuarios/", follow_redirects=False)

    assert resposta.status_code == 302
    assert "/login" in resposta.headers["Location"]


def test_sessao_com_a_marca_atual_continua_valendo(app, client, monkeypatch):
    monkeypatch.setattr(auth.db, "obter_usuario", lambda _id: _usuario())
    monkeypatch.setattr(auth.db, "obter_hash_de_senha", lambda _id: HASH_EM_VIGOR)
    with client.session_transaction() as sessao:
        sessao["usuario_id"] = 1
        sessao[auth.CHAVE_MARCA_DE_SENHA] = marca_de_sessao(
            HASH_EM_VIGOR, chave_secreta=app.secret_key
        )

    assert client.get("/").status_code == 200


def test_sessao_sem_marca_e_recusada(app, client, monkeypatch):
    # Sessao de antes desta mudanca. Cair uma vez, no primeiro acesso depois do
    # deploy, e o comportamento desejado -- recusar e o lado seguro.
    monkeypatch.setattr(auth.db, "obter_usuario", lambda _id: _usuario())
    monkeypatch.setattr(auth.db, "obter_hash_de_senha", lambda _id: HASH_EM_VIGOR)
    with client.session_transaction() as sessao:
        sessao["usuario_id"] = 1

    resposta = client.get("/usuarios/", follow_redirects=False)

    assert "/login" in resposta.headers["Location"]


def test_o_login_grava_a_marca_na_sessao(app, client, monkeypatch):
    app.config["WTF_CSRF_ENABLED"] = False
    monkeypatch.setattr(
        auth.db,
        "obter_usuario_por_login",
        lambda login: {"id": 7, "ativo": True, "senha_hash": HASH_EM_VIGOR},
    )
    monkeypatch.setattr(auth, "conferir_senha", lambda senha, hash_: True)
    monkeypatch.setattr(auth.db, "registrar_login_usuario", lambda usuario_id: None)

    client.post("/login", data={"login": "admin", "senha": "senha-valida"})

    with client.session_transaction() as sessao:
        assert sessao[auth.CHAVE_MARCA_DE_SENHA] == marca_de_sessao(
            HASH_EM_VIGOR, chave_secreta=app.secret_key
        )


def test_trocar_a_propria_senha_nao_derruba_quem_trocou(app, entrar, monkeypatch):
    # O efeito que se quer e derrubar as OUTRAS sessoes, nao esta.
    app.config["WTF_CSRF_ENABLED"] = False
    gravado: dict = {}
    _preparar_troca(monkeypatch, "senha-atual-1", gravado)
    cliente = entrar()

    cliente.post(
        "/minha-senha",
        data={
            "senha_atual": "senha-atual-1",
            "senha_nova": "minha-senha-1",
            "senha_confirmacao": "minha-senha-1",
        },
    )

    with cliente.session_transaction() as sessao:
        assert sessao[auth.CHAVE_MARCA_DE_SENHA] == marca_de_sessao(
            gravado["hash"], chave_secreta=app.secret_key
        )
