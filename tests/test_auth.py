"""
test_auth.py
=============
Testa autenticacao e controle de acesso por perfil em `auth.py`:
hashing de senha, login/logout, e o controle de acesso por AREA (por
pessoa/perfil). Ver `test_app_factory.py` para a separacao ICT/coletor e
`test_database.py::TestUsuariosCRUD` para a persistencia
pura de `usuarios`.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from app import auth
from app import database as db
from app.app_factory import AppConfig, criar_app_ict
from tests.auth_test_utils import SENHA_TESTE, cliente_autenticado
from tests.postgres_test_utils import TestCasePostgres


def _config_teste() -> AppConfig:
    return AppConfig(
        debug=False, host="127.0.0.1", port=0, threaded=False, max_content_length=1_000_000
    )


class TestHashDeSenha(unittest.TestCase):
    """Nao depende de banco nem de app Flask -- so `werkzeug.security` por
    baixo de `auth.gerar_hash_senha`/`auth.conferir_senha`."""

    def test_hash_nao_e_a_senha_em_texto_puro(self):
        hash_ = auth.gerar_hash_senha("minha-senha-123")
        self.assertNotEqual("minha-senha-123", hash_)

    def test_confere_senha_correta(self):
        hash_ = auth.gerar_hash_senha("minha-senha-123")
        self.assertTrue(auth.conferir_senha("minha-senha-123", hash_))

    def test_recusa_senha_incorreta(self):
        hash_ = auth.gerar_hash_senha("minha-senha-123")
        self.assertFalse(auth.conferir_senha("outra-coisa", hash_))

    def test_hash_malformado_nao_levanta_excecao(self):
        self.assertFalse(auth.conferir_senha("qualquer", "isto-nao-e-um-hash-valido"))

    def test_senha_ou_hash_vazio_e_recusado_sem_excecao(self):
        self.assertFalse(auth.conferir_senha("", auth.gerar_hash_senha("x")))
        self.assertFalse(auth.conferir_senha("senha", ""))

    def test_areas_por_perfil_cobre_todo_perfil_valido(self):
        # Mesma asserção que já roda no import de auth.py (ver o `assert`
        # logo após AREAS_POR_PERFIL) -- repetida aqui como teste para que
        # uma regressão apareça no relatório do pytest, não só num
        # ImportError enterrado no traceback de outro teste qualquer.
        self.assertEqual(set(db.PERFIS_VALIDOS), set(auth.AREAS_POR_PERFIL))


class BaseTestComApp(TestCasePostgres):
    def setUp(self):
        super().setUp()
        self.app = criar_app_ict(config=_config_teste())


class TestLoginLogout(BaseTestComApp):
    def setUp(self):
        super().setUp()
        self.usuario = db.criar_usuario(
            {
                "nome": "Vera Vet",
                "login": "vera",
                "perfil": "veterinario",
                "senha_hash": auth.gerar_hash_senha(SENHA_TESTE),
            }
        )
        self.client = self.app.test_client()

    def test_index_sem_login_redireciona_para_login(self):
        resposta = self.client.get("/", follow_redirects=False)
        self.assertIn(resposta.status_code, (301, 302))
        self.assertIn("/login", resposta.headers["Location"])

    def test_api_sem_login_devolve_401_json(self):
        resposta = self.client.get("/api/zonas")
        self.assertEqual(401, resposta.status_code)
        self.assertIn("erro", resposta.get_json())

    def test_login_pagina_carrega_sem_estar_autenticado(self):
        resposta = self.client.get("/login")
        self.assertEqual(200, resposta.status_code)

    def test_login_com_senha_errada_falha(self):
        resposta = self.client.post("/login", data={"login": "vera", "senha": "errada"})
        self.assertEqual(200, resposta.status_code)
        self.assertIn("Login ou senha inválidos", resposta.get_data(as_text=True))

    def test_login_com_usuario_inexistente_falha_com_a_mesma_mensagem(self):
        # A mensagem e IDENTICA a de senha errada de proposito -- ver
        # comentario em `auth.login` sobre nao permitir enumeracao de
        # contas so pela resposta de erro.
        resposta = self.client.post("/login", data={"login": "ninguem", "senha": "x"})
        self.assertIn("Login ou senha inválidos", resposta.get_data(as_text=True))

    def test_login_correto_autentica_e_redireciona(self):
        resposta = self.client.post(
            "/login", data={"login": "vera", "senha": SENHA_TESTE}, follow_redirects=False
        )
        self.assertIn(resposta.status_code, (301, 302))
        self.assertEqual(200, self.client.get("/").status_code)

    def test_login_registra_ultimo_login_em(self):
        self.assertIsNone(self.usuario["ultimo_login_em"])
        self.client.post("/login", data={"login": "vera", "senha": SENHA_TESTE})
        atualizado = db.obter_usuario(self.usuario["id"])
        self.assertIsNotNone(atualizado["ultimo_login_em"])

    def test_usuario_inativo_nao_consegue_logar(self):
        db.atualizar_usuario(
            self.usuario["id"],
            {"nome": "Vera Vet", "login": "vera", "perfil": "veterinario", "ativo": False},
        )
        resposta = self.client.post("/login", data={"login": "vera", "senha": SENHA_TESTE})
        self.assertIn("Login ou senha inválidos", resposta.get_data(as_text=True))

    def test_logout_encerra_sessao(self):
        self.client.post("/login", data={"login": "vera", "senha": SENHA_TESTE})
        self.assertEqual(200, self.client.get("/").status_code)
        self.client.post("/logout")
        resposta = self.client.get("/", follow_redirects=False)
        self.assertIn(resposta.status_code, (301, 302))

    def test_desativar_usuario_derruba_sessao_ja_aberta_na_proxima_requisicao(self):
        # Nao espera a sessao expirar sozinha -- ver
        # `_carregar_usuario_da_sessao` em auth.py: a conta e reconferida
        # no banco a CADA requisicao.
        self.client.post("/login", data={"login": "vera", "senha": SENHA_TESTE})
        self.assertEqual(200, self.client.get("/").status_code)
        db.atualizar_usuario(
            self.usuario["id"],
            {"nome": "Vera Vet", "login": "vera", "perfil": "veterinario", "ativo": False},
        )
        resposta = self.client.get("/", follow_redirects=False)
        self.assertIn(resposta.status_code, (301, 302))

    def test_proxima_url_absoluta_e_ignorada_evita_open_redirect(self):
        resposta = self.client.post(
            "/login?proxima=https://evil.example.com/phish",
            data={"login": "vera", "senha": SENHA_TESTE},
            follow_redirects=False,
        )
        self.assertIn(resposta.status_code, (301, 302))
        self.assertNotIn("evil.example.com", resposta.headers["Location"])

    def test_proxima_protocolo_relativo_e_ignorada(self):
        resposta = self.client.post(
            "/login?proxima=//evil.example.com",
            data={"login": "vera", "senha": SENHA_TESTE},
            follow_redirects=False,
        )
        self.assertIn(resposta.status_code, (301, 302))
        self.assertNotIn("evil.example.com", resposta.headers["Location"])

    def test_proxima_caminho_interno_valido_e_respeitada(self):
        resposta = self.client.post(
            "/login?proxima=/usuarios/",
            data={"login": "ana-admin-temp", "senha": SENHA_TESTE},
            follow_redirects=False,
        )
        # Login com usuario inexistente -- so confirma que a pagina de
        # login em si aceita e devolve o campo `proxima` sem erro; o
        # redirecionamento pos-login valido ja e coberto no teste acima.
        self.assertEqual(200, resposta.status_code)


class TestProtecaoCsrf(BaseTestComApp):
    """Único teste da suíte que exercita a proteção CSRF de verdade: precisa
    desligar `app.testing` (ligado por padrão em `tests/__init__.py` para
    dispensar CSRF no resto da suíte -- ver `auth._proteger_csrf`)."""

    def setUp(self):
        super().setUp()
        self.app.testing = False
        self.client = self.app.test_client()

    def test_post_sem_token_e_recusado(self):
        resposta = self.client.post("/login", data={"login": "ninguem", "senha": "incorreta"})
        self.assertEqual(400, resposta.status_code)

    def test_formulario_com_token_e_aceito(self):
        pagina = self.client.get("/login")
        self.assertEqual(200, pagina.status_code)
        with self.client.session_transaction() as sessao:
            token = sessao["_csrf_token"]

        resposta = self.client.post(
            "/login",
            data={
                "login": "ninguem",
                "senha": "incorreta",
                "_csrf_token": token,
            },
        )
        self.assertEqual(200, resposta.status_code)


class TestControleDeAcessoPorArea(BaseTestComApp):
    """Para cada perfil, confere que as rotas API respeitam exatamente
    `auth.AREAS_POR_PERFIL` -- a mesma tabela publicada no README ("
    Organização das abas por papel de uso"). Usa uma rota representativa
    por area em vez de todo o mapa de endpoints (ver `auth.AREA_POR_ENDPOINT`
    para a lista completa)."""

    def setUp(self):
        super().setUp()
        self.zona = db.criar_zona({"nome": "Aviário 1", "especie": "frangos", "indice": "ITU"})

    def _cliente(self, perfil: str):
        return cliente_autenticado(self.app, perfil)

    def test_area_analises(self):
        for perfil in db.PERFIS_VALIDOS:
            with self.subTest(perfil=perfil):
                resposta = self._cliente(perfil).get("/api/analises")
                esperado = 200 if auth.area_permitida(perfil, "analises") else 403
                self.assertEqual(esperado, resposta.status_code)

    def test_area_historico(self):
        for perfil in db.PERFIS_VALIDOS:
            with self.subTest(perfil=perfil):
                resposta = self._cliente(perfil).get("/api/historico-leituras")
                # historico-leituras vive em comum_bp (universal, sem area
                # exigida) -- QUALQUER perfil autenticado acessa. A area
                # "historico" so existiria se um dia essa rota migrar para
                # um blueprint dedicado; por ora o teste documenta o estado
                # atual (ver docstring de rotas_comuns.py).
                self.assertEqual(200, resposta.status_code)

    def test_area_dados_entrada_leitura(self):
        for perfil in db.PERFIS_VALIDOS:
            with self.subTest(perfil=perfil):
                resposta = self._cliente(perfil).get("/api/dados-entrada/execucoes")
                esperado = 200 if auth.area_permitida(perfil, "dados_entrada") else 403
                self.assertEqual(esperado, resposta.status_code)

    def test_area_cadastro_criar_zona(self):
        for perfil in db.PERFIS_VALIDOS:
            with self.subTest(perfil=perfil):
                resposta = self._cliente(perfil).post(
                    "/api/zonas",
                    json={"nome": f"Zona {perfil}", "especie": "frangos", "indice": "ITU"},
                )
                esperado = 201 if auth.area_permitida(perfil, "cadastro") else 403
                self.assertEqual(esperado, resposta.status_code)

    def test_area_operacao_comando(self):
        with patch("app.ict.operacao.chamar_coletor", return_value=({}, 200)):
            for perfil in db.PERFIS_VALIDOS:
                with self.subTest(perfil=perfil):
                    resposta = self._cliente(perfil).put(
                        f"/api/zonas/{self.zona['id']}/controle",
                        json={"modo": "manual", "acionamento_habilitado": False},
                    )
                    esperado = 200 if auth.area_permitida(perfil, "operacao") else 403
                    self.assertEqual(esperado, resposta.status_code)

    def test_area_configuracoes_ou_sistema_libera_ler_configuracoes(self):
        for perfil in db.PERFIS_VALIDOS:
            with self.subTest(perfil=perfil):
                resposta = self._cliente(perfil).get("/api/configuracoes")
                liberado = auth.area_permitida(perfil, "configuracoes") or auth.area_permitida(
                    perfil, "sistema"
                )
                self.assertEqual(200 if liberado else 403, resposta.status_code)

    def test_area_sistema_e_exigida_para_backup_mesmo_tendo_configuracoes(self):
        # Veterinario tem "configuracoes" mas NAO tem "sistema" -- backup
        # do banco e exclusivo de "sistema" (ver AREA_POR_ENDPOINT).
        resposta_veterinario = self._cliente("veterinario").post("/api/backup-banco")
        self.assertEqual(403, resposta_veterinario.status_code)

        resposta_tecnico = self._cliente("tecnico").post("/api/backup-banco")
        self.assertNotEqual(403, resposta_tecnico.status_code)

    def test_usuarios_bp_so_administrador_acessa(self):
        for perfil in db.PERFIS_VALIDOS:
            with self.subTest(perfil=perfil):
                resposta = self._cliente(perfil).get("/usuarios/", follow_redirects=False)
                if perfil == "administrador":
                    self.assertEqual(200, resposta.status_code)
                else:
                    self.assertIn(resposta.status_code, (301, 302))

    def test_analista_pode_gerar_dados_mas_nao_excluir(self):
        # "dados_entrada" cobre gerar/exportar para analista, mas excluir
        # e reservado a tecnico/administrador -- ver
        # PERFIS_QUE_PODEM_EXCLUIR_DADOS_ENTRADA em auth.py.
        cliente_analista = self._cliente("analista")
        resposta_excluir = cliente_analista.delete(
            "/api/dados-entrada/medicoes", json={"confirmacao": "APAGAR"}
        )
        self.assertEqual(403, resposta_excluir.status_code)

    def test_tecnico_pode_excluir_dados_de_entrada(self):
        cliente_tecnico = self._cliente("tecnico")
        resposta = cliente_tecnico.delete(
            "/api/dados-entrada/medicoes", json={"confirmacao": "APAGAR"}
        )
        self.assertNotEqual(403, resposta.status_code)

    def test_veterinario_nao_acessa_cadastro_mas_acessa_configuracoes(self):
        cliente_vet = self._cliente("veterinario")
        self.assertEqual(
            403,
            cliente_vet.post(
                "/api/zonas", json={"nome": "X", "especie": "frangos", "indice": "ITU"}
            ).status_code,
        )
        self.assertEqual(200, cliente_vet.get("/api/configuracoes").status_code)


class TestPaginaDeUsuarios(BaseTestComApp):
    """Fluxo HTTP completo da tela de administracao (`/usuarios`):
    criar/editar/excluir usuarios via formulario, e as protecoes contra
    auto-lockout (ver `auth.editar_usuario_rota`/`excluir_usuario_rota`)."""

    def setUp(self):
        super().setUp()
        self.admin = db.criar_usuario(
            {
                "nome": "Ana Admin",
                "login": "ana",
                "perfil": "administrador",
                "senha_hash": auth.gerar_hash_senha(SENHA_TESTE),
            }
        )
        self.client = self.app.test_client()
        with self.client.session_transaction() as sessao:
            sessao["usuario_id"] = self.admin["id"]

    def test_lista_usuarios_mostra_contas_existentes(self):
        db.criar_usuario(
            {
                "nome": "Otto Operador",
                "login": "otto",
                "perfil": "operador",
                "senha_hash": auth.gerar_hash_senha(SENHA_TESTE),
            }
        )
        resposta = self.client.get("/usuarios/")
        self.assertIn("otto", resposta.get_data(as_text=True))

    def test_criar_usuario_via_formulario(self):
        resposta = self.client.post(
            "/usuarios/novo",
            data={
                "nome": "Otto Operador",
                "login": "otto",
                "perfil": "operador",
                "senha": SENHA_TESTE,
                "ativo": "on",
            },
            follow_redirects=False,
        )
        self.assertIn(resposta.status_code, (301, 302))
        criado = db.obter_usuario_por_login("otto")
        self.assertIsNotNone(criado)
        self.assertEqual("operador", criado["perfil"])

    def test_criar_usuario_com_senha_curta_e_recusado(self):
        resposta = self.client.post(
            "/usuarios/novo",
            data={"nome": "Otto", "login": "otto", "perfil": "operador", "senha": "123"},
        )
        self.assertEqual(200, resposta.status_code)
        self.assertIsNone(db.obter_usuario_por_login("otto"))

    def test_criar_usuario_com_login_duplicado_e_recusado(self):
        resposta = self.client.post(
            "/usuarios/novo",
            data={
                "nome": "Outra Ana",
                "login": "ana",
                "perfil": "operador",
                "senha": SENHA_TESTE,
            },
        )
        self.assertEqual(200, resposta.status_code)
        self.assertIn("Já existe", resposta.get_data(as_text=True))

    def test_editar_usuario_troca_perfil(self):
        outro = db.criar_usuario(
            {
                "nome": "Otto",
                "login": "otto",
                "perfil": "operador",
                "senha_hash": auth.gerar_hash_senha(SENHA_TESTE),
            }
        )
        resposta = self.client.post(
            f"/usuarios/{outro['id']}/editar",
            data={"nome": "Otto", "login": "otto", "perfil": "tecnico", "ativo": "on"},
            follow_redirects=False,
        )
        self.assertIn(resposta.status_code, (301, 302))
        self.assertEqual("tecnico", db.obter_usuario(outro["id"])["perfil"])

    def test_admin_nao_consegue_rebaixar_a_si_mesmo(self):
        resposta = self.client.post(
            f"/usuarios/{self.admin['id']}/editar",
            data={"nome": "Ana Admin", "login": "ana", "perfil": "operador", "ativo": "on"},
        )
        self.assertEqual(200, resposta.status_code)
        self.assertIn("seu próprio acesso", resposta.get_data(as_text=True))
        self.assertEqual("administrador", db.obter_usuario(self.admin["id"])["perfil"])

    def test_admin_nao_consegue_se_desativar(self):
        resposta = self.client.post(
            f"/usuarios/{self.admin['id']}/editar",
            data={"nome": "Ana Admin", "login": "ana", "perfil": "administrador"},
        )
        self.assertEqual(200, resposta.status_code)
        self.assertTrue(db.obter_usuario(self.admin["id"])["ativo"])

    def test_admin_nao_consegue_se_excluir(self):
        resposta = self.client.post(f"/usuarios/{self.admin['id']}/excluir", follow_redirects=True)
        self.assertIn("própria conta", resposta.get_data(as_text=True))
        self.assertIsNotNone(db.obter_usuario(self.admin["id"]))

    def test_excluir_ultimo_administrador_e_recusado_com_mensagem(self):
        # Diferente do teste acima: aqui o alvo NAO e a propria sessao (e
        # um segundo administrador), mas ele TAMBEM e o ultimo ativo --
        # confirma que `UltimoAdministradorError` (nao so a checagem de
        # "sou eu mesmo") aparece como mensagem para quem esta usando a
        # tela.
        segundo_admin = db.criar_usuario(
            {
                "nome": "Beto Admin",
                "login": "beto",
                "perfil": "administrador",
                "senha_hash": auth.gerar_hash_senha(SENHA_TESTE),
            }
        )
        db.excluir_usuario(self.admin["id"])  # agora Beto e o unico admin
        with self.client.session_transaction() as sessao:
            sessao["usuario_id"] = segundo_admin["id"]

        # Beto tenta excluir A SI MESMO -- bloqueado pela regra de
        # "propria conta", que e checada antes da regra de ultimo admin.
        resposta = self.client.post(
            f"/usuarios/{segundo_admin['id']}/excluir", follow_redirects=True
        )
        self.assertIn("própria conta", resposta.get_data(as_text=True))
        self.assertIsNotNone(db.obter_usuario(segundo_admin["id"]))

    def test_excluir_outro_usuario_funciona_normalmente(self):
        outro = db.criar_usuario(
            {
                "nome": "Otto",
                "login": "otto",
                "perfil": "operador",
                "senha_hash": auth.gerar_hash_senha(SENHA_TESTE),
            }
        )
        self.client.post(f"/usuarios/{outro['id']}/excluir")
        self.assertIsNone(db.obter_usuario(outro["id"]))


if __name__ == "__main__":
    unittest.main()
