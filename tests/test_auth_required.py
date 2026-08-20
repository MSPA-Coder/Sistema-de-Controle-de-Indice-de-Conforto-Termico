"""A aplicacao nega por padrao, e a isencao e uma lista curta e explicita.

O gate de login vem de `sharedauth.access.requer_login` desde a Fase 4 da
migração (ver PLANO_UNIFICAR_AUTENTICACAO.md no repositório `_manutencao`) --
antes era um `before_request` próprio deste projeto. `criar_app_ict()` não
conecta ao banco na criação (ver conftest.py), então os testes abaixo usam
`app.test_client()` de verdade em vez de inspecionar código-fonte: o que se
protege é a mesma coisa (uma rota que deixa de exigir sessão continua
respondendo 200 e parecendo correta), mas agora é medido pela resposta HTTP,
não por `inspect.getsource`.
"""

from __future__ import annotations

import pytest

from app import auth, db_backend, secret_files


def test_isencao_de_login_e_curta_e_conhecida():
    # A lista e de endpoints publicos, nao de protegidos: um endpoint novo
    # nasce exigindo sessao. Acrescentar algo aqui deve ser decisao consciente,
    # e este teste e o que obriga a passar por ela.
    assert frozenset(
        {"auth.login", "comum.favicon", "health_ict", "static"}
    ) == auth.ENDPOINTS_ISENTOS_DE_LOGIN, f"isencoes inesperadas: {auth.ENDPOINTS_ISENTOS_DE_LOGIN}"


def test_rota_protegida_recusa_acesso_anonimo(client):
    resposta = client.get("/", follow_redirects=False)
    assert resposta.status_code == 302
    assert "/login" in resposta.headers["Location"]


def test_rota_protegida_de_api_recusa_acesso_anonimo_com_401(client):
    # A mensagem exata ("Autenticação necessária.") vem de
    # `sharedauth.access` -- a chave "erro" (não "error") é a convenção
    # deste app, configurada em `app_factory.criar_app_ict`.
    resposta = client.get("/api/zonas")
    assert resposta.status_code == 401
    assert resposta.get_json() == {"erro": "Autenticação necessária."}


def test_next_preserva_o_caminho_original(client):
    resposta = client.get("/", follow_redirects=False)
    assert resposta.headers["Location"] == "/login?next=/"


def test_login_e_publico(client):
    assert client.get("/login").status_code == 200


def test_sessao_apontando_para_usuario_removido_e_tratada_como_deslogada(client, monkeypatch):
    # Desativar um usuario precisa ter efeito imediato, nao so quando a
    # sessao dele vencer -- simula a sessao ja aberta apontando para um id
    # que nao existe mais (removido, ou desativado nesse meio-tempo).
    monkeypatch.setattr(auth.db, "obter_usuario", lambda usuario_id: None)
    with client.session_transaction() as sessao:
        sessao["usuario_id"] = 999999
    resposta = client.get("/", follow_redirects=False)
    assert resposta.status_code == 302
    assert "/login" in resposta.headers["Location"]
    with client.session_transaction() as sessao:
        assert "usuario_id" not in sessao


def test_todo_perfil_declara_suas_areas():
    # O modulo ja falha na importacao se divergirem; este teste torna o motivo
    # legivel quando isso acontecer.
    from app import database as db

    assert set(auth.AREAS_POR_PERFIL) == set(db.PERFIS_VALIDOS)


def test_nenhum_perfil_fica_sem_area():
    for perfil, areas in auth.AREAS_POR_PERFIL.items():
        assert areas, f"perfil '{perfil}' nao alcanca area nenhuma"


def test_area_por_endpoint_so_cita_areas_existentes():
    # Um endpoint pode exigir uma area ou qualquer uma de varias; um nome
    # errado aqui deixaria a rota inalcancavel para todo mundo, em silencio.
    conhecidas = set().union(*auth.AREAS_POR_PERFIL.values())
    for endpoint, exigida in auth.AREA_POR_ENDPOINT.items():
        areas = (exigida,) if isinstance(exigida, str) else exigida
        for area in areas:
            assert area in conhecidas, f"{endpoint} exige a area '{area}', que ninguem tem"


def test_chave_de_sessao_gerada_persiste_e_e_reutilizada(tmp_path, monkeypatch):
    """O reinício normal mantém a chave e, portanto, as sessões válidas."""
    from app import database as db

    monkeypatch.delenv("CONFORTO_SECRET_KEY", raising=False)
    monkeypatch.setattr(db, "INSTANCE_DIR", str(tmp_path))

    criada = auth.obter_ou_criar_chave_secreta()
    caminho = tmp_path / "secret_key.txt"

    assert caminho.is_file()
    assert caminho.read_text(encoding="utf-8") == criada
    assert auth.obter_ou_criar_chave_secreta() == criada


def test_chave_de_sessao_prioriza_ambiente_sem_persistir(tmp_path, monkeypatch):
    """Uma configuração explícita não cria nem substitui o arquivo do volume."""
    from app import database as db

    monkeypatch.setattr(db, "INSTANCE_DIR", str(tmp_path))
    monkeypatch.setenv("CONFORTO_SECRET_KEY", "chave-isolada-de-ambiente")

    assert auth.obter_ou_criar_chave_secreta() == "chave-isolada-de-ambiente"
    assert not (tmp_path / "secret_key.txt").exists()


def test_perda_da_chave_gera_recuperacao_persistida_e_invalida_sessoes(tmp_path, monkeypatch):
    """Modela o risco declarado na ADR 005 sem usar o volume ou segredo real."""
    from app import database as db

    monkeypatch.delenv("CONFORTO_SECRET_KEY", raising=False)
    monkeypatch.setattr(db, "INSTANCE_DIR", str(tmp_path))

    anterior = auth.obter_ou_criar_chave_secreta()
    (tmp_path / "secret_key.txt").unlink()
    recuperada = auth.obter_ou_criar_chave_secreta()

    assert recuperada != anterior
    assert auth.obter_ou_criar_chave_secreta() == recuperada


def test_token_interno_por_arquivo_falha_fechado_se_arquivo_nao_existe(tmp_path, monkeypatch):
    """Um token Docker secret ausente não pode cair em token persistido local."""
    monkeypatch.delenv("CONFORTO_INTERNO_TOKEN", raising=False)
    monkeypatch.setattr(secret_files, "DOCKER_SECRETS_DIR", tmp_path)
    monkeypatch.setenv("CONFORTO_INTERNO_TOKEN_FILE", str(tmp_path / "internal_token"))

    with pytest.raises(RuntimeError, match="CONFORTO_INTERNO_TOKEN_FILE"):
        auth.obter_ou_criar_token_interno()


def test_segredos_compose_recusam_caminho_fora_do_mount(tmp_path, monkeypatch):
    fora = tmp_path / "fora"
    fora.write_text("valor-sintetico", encoding="utf-8")
    monkeypatch.setenv("CONFORTO_INTERNO_TOKEN_FILE", str(fora))

    with pytest.raises(RuntimeError, match="deve apontar"):
        auth.obter_ou_criar_token_interno()


def test_segredos_compose_aceitam_arquivo_montado_esperado(tmp_path, monkeypatch):
    token = tmp_path / "internal_token"
    senha = tmp_path / "postgres_password"
    token.write_text("token-sintetico", encoding="utf-8")
    senha.write_text("senha-sintetica", encoding="utf-8")
    monkeypatch.setattr(secret_files, "DOCKER_SECRETS_DIR", tmp_path)
    monkeypatch.setenv("CONFORTO_INTERNO_TOKEN_FILE", str(token))
    monkeypatch.setenv("DB_PASSWORD_FILE", str(senha))

    assert auth.obter_ou_criar_token_interno() == "token-sintetico"
    assert db_backend._ler_segredo("DB_PASSWORD_FILE") == "senha-sintetica"


@pytest.mark.parametrize(
    "destino",
    [
        "//externo.test",
        "/\\externo.test",
        "/%5cexterno.test",
        "/%255cexterno.test",
        "/%2f%2fexterno.test",
        "/%252f%252fexterno.test",
        "https://externo.test",
    ],
)
def test_destino_pos_login_recusa_redirecionamento_externo(destino, monkeypatch):
    monkeypatch.setattr(auth, "url_for", lambda endpoint: "/")

    assert auth._destino_pos_login(destino) == "/"


def test_destino_pos_login_recusa_separador_aninhado_alem_de_tres_camadas(monkeypatch):
    monkeypatch.setattr(auth, "url_for", lambda endpoint: "/")
    destino = "/%5cexterno.test"
    for _ in range(6):
        destino = destino.replace("%", "%25")

    assert auth._destino_pos_login(destino) == "/"
