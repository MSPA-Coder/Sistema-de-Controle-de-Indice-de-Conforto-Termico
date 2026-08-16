"""A aplicacao nega por padrao, e a isencao e uma lista curta e explicita.

Como o factory deste projeto conecta ao banco, a afirmacao e sobre as
estruturas que decidem o acesso e sobre a fiacao dos hooks -- nao sobre uma
resposta HTTP. O que se protege e o mesmo: uma rota que deixa de exigir sessao
continua respondendo 200 e parecendo correta.
"""

from __future__ import annotations

import inspect

import pytest

from app import auth, db_backend, secret_files


def test_isencao_de_login_e_curta_e_conhecida():
    # A lista e de endpoints publicos, nao de protegidos: um endpoint novo
    # nasce exigindo sessao. Acrescentar algo aqui deve ser decisao consciente,
    # e este teste e o que obriga a passar por ela.
    assert frozenset(
        {"auth.login", "comum.favicon", "health_ict"}
    ) == auth.ENDPOINTS_ISENTOS_DE_LOGIN, f"isencoes inesperadas: {auth.ENDPOINTS_ISENTOS_DE_LOGIN}"


def test_hook_de_login_exige_sessao_em_toda_rota():
    fonte = inspect.getsource(auth.registrar_autenticacao)
    # O hook precisa continuar sendo `before_request` global. Trocar por
    # decorators por rota devolveria o problema de a rota nova nascer aberta.
    assert "@app.before_request" in fonte
    assert "ENDPOINTS_ISENTOS_DE_LOGIN" in fonte
    assert "g.usuario is None" in fonte


def test_criar_app_ict_liga_o_hook_de_autenticacao():
    # O teste acima garante que o hook em si nega por padrao -- mas nada
    # garantia que `criar_app_ict()` de fato o registra. Essa suite e
    # caixa-branca e nao instancia a app (o factory conecta a banco), entao
    # remover `auth.registrar_autenticacao(app)` do factory deixaria toda
    # rota efetivamente sem autenticacao, respondendo 200 e parecendo
    # correta, sem que nenhum teste ate agora pegasse isso.
    from app import app_factory

    fonte = inspect.getsource(app_factory.criar_app_ict)
    assert "auth.registrar_autenticacao(app)" in fonte


def test_sessao_apontando_para_usuario_removido_e_tratada_como_deslogada():
    fonte = inspect.getsource(auth.registrar_autenticacao)
    # Desativar um usuario precisa ter efeito imediato, nao so quando a sessao
    # dele vencer.
    assert "session.clear()" in fonte


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
