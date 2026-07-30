"""
auth.py
========
Autenticacao e controle de acesso por pessoa nas rotas publicas do ICT.
Este modulo e o unico lugar do sistema que:

- Sabe como transformar uma senha em texto puro num hash (`werkzeug.security`,
  scrypt por padrao nesta versao do Werkzeug) e como conferir uma senha
  digitada contra esse hash. `database.py` guarda `senha_hash` como uma
  string opaca e nunca ve a senha real.
- Decide, a partir do PERFIL de uma sessao, quais AREAS da interface (que
  mapeiam 1:1 aos grupos de abas em `templates/index.html` -- ver
  README.md, secao "Organizacao das abas por papel de uso") esse perfil
  pode acessar.
- Registra os dois hooks `before_request` que aplicam essa decisao a TODA
  rota do app (`registrar_autenticacao`), inclusive a pagina inicial.

A separacao de areas e so a metade "isso e permitido" da decisao. A outra
metade -- "o template so MOSTRA o botao/aba que a pessoa pode usar" -- fica
em `templates/index.html` (`areas_permitidas`, injetado por
`rotas_comuns.index`). As duas metades tem que concordar, mas so a
metade AQUI e a que realmente impede uma chamada de API indevida: esconder
um botao no HTML nunca e controle de acesso de verdade.
"""

from __future__ import annotations

import contextlib
import hmac
import os
import re
import secrets
from pathlib import Path

from flask import (
    Blueprint,
    Flask,
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.security import check_password_hash, generate_password_hash

from . import database as db

# ---------------------------------------------------------------------------
# Perfis, areas e rotulos de exibicao
# ---------------------------------------------------------------------------

# Cada area corresponde a um grupo de abas da interface. "dashboard" e a
# unica presente em TODOS os perfis porque a aba Dashboard nunca tem uma
# acao de escrita -- e so exibicao, sem risco em liberar para qualquer
# pessoa autenticada.
AREAS_POR_PERFIL: dict[str, frozenset[str]] = {
    "operador": frozenset({"dashboard", "operacao"}),
    "tecnico": frozenset(
        {"dashboard", "operacao", "historico", "cadastro", "sistema", "dados_entrada"}
    ),
    "veterinario": frozenset({"dashboard", "analises", "historico", "configuracoes"}),
    "analista": frozenset({"dashboard", "analises", "historico", "dados_entrada"}),
    "gestor": frozenset({"dashboard", "analises", "historico"}),
    "administrador": frozenset(
        {
            "dashboard",
            "operacao",
            "analises",
            "historico",
            "cadastro",
            "configuracoes",
            "sistema",
            "dados_entrada",
            "usuarios",
        }
    ),
}

# Confere, na importacao do modulo, que todo perfil valido em `database.py`
# tem uma entrada aqui -- um perfil novo adicionado em PERFIS_VALIDOS sem
# vir acompanhado de uma entrada em AREAS_POR_PERFIL cairia silenciosamente
# em "nenhuma area liberada" (o mais restritivo possivel, mas ainda assim
# um bug). Falha cedo, no import, em vez de silenciosamente em producao.
assert set(AREAS_POR_PERFIL) == set(db.PERFIS_VALIDOS), (
    "AREAS_POR_PERFIL e PERFIS_VALIDOS divergiram -- todo perfil precisa "
    "de uma entrada de areas liberadas."
)

PERFIL_LABEL: dict[str, str] = {
    "operador": "Operador",
    "tecnico": "Técnico",
    "veterinario": "Veterinário",
    "analista": "Analista",
    "gestor": "Gestor",
    "administrador": "Administrador",
}

# Dentro da area "dados_entrada", excluir dados e uma acao irreversivel que
# afeta series inteiras de medicoes: mesmo que "analista" tenha acesso de
# escrita a area (gerar/exportar), excluir fica restrito a tecnico e
# administrador. Ver AREA_POR_ENDPOINT/PERFIS_EXTRA_POR_ENDPOINT abaixo.
PERFIS_QUE_PODEM_EXCLUIR_DADOS_ENTRADA = frozenset({"tecnico", "administrador"})

SENHA_TAMANHO_MINIMO = 8
METODOS_HTTP_SEGUROS = frozenset({"GET", "HEAD", "OPTIONS"})

# Limiter para rate limiting - inicializado uma vez e reutilizado
_limiter: Limiter | None = None


def obter_limiter() -> Limiter:
    """Obtem ou cria o limiter para rate limiting."""
    global _limiter
    if _limiter is None:
        _limiter = Limiter(
            key_func=get_remote_address,
            default_limits=["100 per hour", "20 per minute"],
            storage_uri="memory://",
        )
    return _limiter


def sanitizar_log(mensagem: str) -> str:
    """Sanitiza credenciais e dados sensíveis de logs."""
    # Remove senhas de strings de log
    mensagem = re.sub(r"senha[=:]\s*\S+", "senha=***", mensagem, flags=re.IGNORECASE)
    mensagem = re.sub(r"password[=:]\s*\S+", "password=***", mensagem, flags=re.IGNORECASE)
    mensagem = re.sub(r"secret[=:]\s*\S+", "secret=***", mensagem, flags=re.IGNORECASE)
    mensagem = re.sub(r"token[=:]\s*\S+", "token=***", mensagem, flags=re.IGNORECASE)
    return mensagem


def obter_token_csrf() -> str:
    token = session.get("_csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["_csrf_token"] = token
    return token


# ---------------------------------------------------------------------------
# Hash de senha -- unico lugar do sistema que importa werkzeug.security
# ---------------------------------------------------------------------------


def gerar_hash_senha(senha: str) -> str:
    return generate_password_hash(senha)


def conferir_senha(senha: str, hash_: str) -> bool:
    if not senha or not hash_:
        return False
    try:
        return check_password_hash(hash_, senha)
    except ValueError:
        # Hash malformado ou de um algoritmo que esta versao do Werkzeug
        # nao reconhece: trata como senha incorreta em vez de propagar a
        # excecao ate o cliente HTTP.
        return False


# ---------------------------------------------------------------------------
# Chave de sessao: variavel de ambiente tem precedencia; sem ela, gera uma
# vez e persiste em disco (para nao invalidar todas as sessoes a cada
# reinicio do servidor). Nunca versionada -- `instance/` ja esta no
# .gitignore do projeto.
# ---------------------------------------------------------------------------


def obter_ou_criar_chave_secreta() -> str:
    variavel_ambiente = os.environ.get("CONFORTO_SECRET_KEY")
    if variavel_ambiente:
        return variavel_ambiente

    # Deliberadamente `os.path.dirname(db.DB_PATH)` (avaliado agora, na
    # CHAMADA) em vez de `db.INSTANCE_DIR` (fixo, resolvido na importacao
    # do modulo): em producao os dois caminhos coincidem, mas os testes
    # sobrescrevem `db.DB_PATH` para um diretorio temporario isolado por
    # teste -- usar o caminho fixo faria toda chave de sessao de teste ser
    # lida/gravada no `instance/` REAL do projeto (poluindo o repositorio
    # local a cada execucao da suite) em vez de ficar isolada no tempdir do
    # proprio teste, junto do `historico.db` que ela protege.
    caminho = Path(os.path.dirname(db.DB_PATH)) / "secret_key.txt"
    try:
        chave_existente = caminho.read_text(encoding="utf-8").strip()
        if chave_existente:
            return chave_existente
    except OSError:
        pass

    nova_chave = secrets.token_hex(32)
    try:
        caminho.parent.mkdir(parents=True, exist_ok=True)
        caminho.write_text(nova_chave, encoding="utf-8")
        with contextlib.suppress(OSError):
            os.chmod(caminho, 0o600)  # Windows nao suporta esse modo -- nao e fatal.
    except OSError:
        pass  # Sem permissao de escrita: a chave vale so para este processo.
    return nova_chave


def obter_ou_criar_token_interno() -> str:
    """Segredo compartilhado entre ICT e coletor para toda a API interna.

    O navegador nunca ve nem envia este token; ele nao e uma credencial
    de pessoa.

    Mesmo padrao de `obter_ou_criar_chave_secreta` acima, incluindo a
    precedencia da variavel de ambiente: instalacoes em que coletor e
    "outra parte" rodam em MAQUINAS diferentes (nao compartilham
    `instance/`) precisam definir `CONFORTO_INTERNO_TOKEN` explicitamente
    e IGUAL nos dois processos -- sem isso, cada lado geraria e
    persistiria um token diferente e a chamada interna sempre falharia
    com 403. Essa limitacao acompanha a mesma premissa ja documentada no
    README para o proprio banco SQLite (arquitetura pensada para as duas
    partes no MESMO host)."""
    variavel_ambiente = os.environ.get("CONFORTO_INTERNO_TOKEN")
    if variavel_ambiente:
        return variavel_ambiente
    arquivo_segredo = os.environ.get("CONFORTO_INTERNO_TOKEN_FILE")
    if arquivo_segredo:
        try:
            token = Path(arquivo_segredo).read_text(encoding="utf-8").strip()
        except OSError as erro:
            raise RuntimeError("Não foi possível ler CONFORTO_INTERNO_TOKEN_FILE.") from erro
        if not token:
            raise RuntimeError("CONFORTO_INTERNO_TOKEN_FILE está vazio.")
        return token

    caminho = Path(os.path.dirname(db.DB_PATH)) / "interno_token.txt"
    try:
        token_existente = caminho.read_text(encoding="utf-8").strip()
        if token_existente:
            return token_existente
    except OSError:
        pass

    novo_token = secrets.token_hex(32)
    try:
        caminho.parent.mkdir(parents=True, exist_ok=True)
        caminho.write_text(novo_token, encoding="utf-8")
        with contextlib.suppress(OSError):
            os.chmod(caminho, 0o600)
    except OSError:
        pass
    return novo_token


# ---------------------------------------------------------------------------
# Autorizacao por endpoint. Ver o modulo docstring: esta e a metade que
# realmente impede uma chamada indevida (a outra metade, visual, fica no
# template). Mapeado por NOME DE ENDPOINT do Flask ("blueprint.funcao"),
# nao por caminho de URL -- assim GET e POST na mesma URL (ex.: /api/zonas)
# podem exigir areas diferentes quando vem de blueprints diferentes.
# ---------------------------------------------------------------------------

ENDPOINTS_ISENTOS_DE_LOGIN = frozenset(
    {
        "auth.login",
        "comum.favicon",
        "health_ict",
    }
)

# Um valor pode ser uma unica area (string) ou uma tupla de areas -- neste
# ultimo caso, BASTA o perfil ter qualquer uma delas. Usado por
# obter/salvar configuracoes, cujo payload unico atende tanto a aba
# Configuracoes (veterinario) quanto a aba Sistema (tecnico) -- ver
# README.md.
AREA_POR_ENDPOINT: dict[str, str | tuple[str, ...]] = {
    # --- ict_bp (aba Analises) ---------------------------------------
    "ict.obter_analises": "analises",
    "ict.obter_painel_executivo": "analises",
    # --- dados_entrada_leitura_bp + dados_entrada_bp (aba Dados de entrada) --
    "dados_entrada_leitura.obter_configuracoes": "dados_entrada",
    "dados_entrada_leitura.obter_referencias": "dados_entrada",
    "dados_entrada_leitura.listar_execucoes": "dados_entrada",
    "dados_entrada_leitura.exportar_csv": "dados_entrada",
    "dados_entrada.salvar_configuracoes": "dados_entrada",
    "dados_entrada.gerar_dados": "dados_entrada",
    "dados_entrada.excluir_medicoes": "dados_entrada",
    "dados_entrada.copiar_para_historico": "dados_entrada",
    "dados_entrada.apagar_historico": "dados_entrada",
    # "Limpar historico" (botao btn-limpar, hoje na aba Sistema > Banco de
    # dados): apaga TODAS as leituras de TODAS as zonas de uma vez, por
    # isso fica em "sistema" (tecnico/administrador) e nao em "operacao".
    "administracao.reset": "sistema",
    # --- administracao_bp: Configuracoes + Sistema ---------------------
    # (nao toca Modbus -- ver docstring de ict/administracao.py
    # sobre por que essas rotas saíram de coletor_bp)
    "administracao.obter_configuracoes": ("configuracoes", "sistema"),
    "administracao.salvar_configuracoes": ("configuracoes", "sistema"),
    "administracao.backup_banco": "sistema",
    # --- administracao_bp: Cadastro (zonas/equipamentos, fiacao Modbus) -
    "administracao.criar_zona": "cadastro",
    "administracao.obter_zona": "cadastro",
    "administracao.atualizar_zona": "cadastro",
    "administracao.excluir_zona": "cadastro",
    "administracao.criar_equipamento": "cadastro",
    "administracao.atualizar_equipamento": "cadastro",
    "administracao.excluir_equipamento": "cadastro",
    "administracao.testar_conexao_equipamento": "cadastro",
    # --- operacao_bp: o ICT autoriza e encaminha ao coletor privado ---
    "operacao.calcular_zona": "operacao",
    "operacao.alterar_controle_zona": "operacao",
    "operacao.comandar_atuador_zona": "operacao",
    # --- usuarios_bp (pagina de administracao, fora da SPA) -----------
    "usuarios.pagina_usuarios": "usuarios",
    "usuarios.criar_usuario_rota": "usuarios",
    "usuarios.editar_usuario_rota": "usuarios",
    "usuarios.excluir_usuario_rota": "usuarios",
}

# Restricao ADICIONAL: mesmo com a area liberada, so os perfis listados
# podem chamar o endpoint. Ver comentario de PERFIS_QUE_PODEM_EXCLUIR_DADOS_ENTRADA.
PERFIS_EXTRA_POR_ENDPOINT: dict[str, frozenset[str]] = {
    "dados_entrada.excluir_medicoes": PERFIS_QUE_PODEM_EXCLUIR_DADOS_ENTRADA,
    "dados_entrada.apagar_historico": PERFIS_QUE_PODEM_EXCLUIR_DADOS_ENTRADA,
}


def area_permitida(perfil: str, area: str) -> bool:
    return area in AREAS_POR_PERFIL.get(perfil, frozenset())


def usuario_atual() -> dict | None:
    """Le `g.usuario`, carregado pelo hook `_carregar_usuario_da_sessao`
    (ver `registrar_autenticacao`). Fora do ciclo de requisicao (ex.: um
    teste chamando isto diretamente sem passar por uma rota), devolve
    `None` em vez de levantar `RuntimeError` por falta de contexto."""
    return getattr(g, "usuario", None)


def _negar_acesso():
    if request.path.startswith("/api/"):
        return jsonify({"erro": "Seu perfil não tem acesso a esta função."}), 403
    return redirect(url_for("comum.index"))


def registrar_autenticacao(app: Flask) -> None:
    """Registra os hooks que exigem login em QUALQUER rota (inclusive a
    pagina inicial) e que conferem a area exigida por endpoint, quando houver
    uma em AREA_POR_ENDPOINT/PERFIS_EXTRA_POR_ENDPOINT."""

    app.jinja_env.globals["csrf_token"] = obter_token_csrf

    @app.before_request
    def _proteger_csrf():
        # A suíte usa clientes Flask isolados e testa autorização
        # separadamente. Um teste dedicado cobre esta proteção com TESTING
        # desabilitado.
        if (
            not app.config.get("CSRF_PROTECTION_ENABLED", True)
            or app.testing
            or request.method in METODOS_HTTP_SEGUROS
        ):
            return None
        esperado = session.get("_csrf_token", "")
        recebido = request.headers.get("X-CSRF-Token", "") or request.form.get("_csrf_token", "")
        if esperado and recebido and hmac.compare_digest(esperado, recebido):
            return None
        if request.path.startswith("/api/"):
            return jsonify({"erro": "Token CSRF inválido ou ausente."}), 400
        return "Token CSRF inválido ou ausente.", 400

    @app.before_request
    def _carregar_usuario_da_sessao():
        g.usuario = None
        usuario_id = session.get("usuario_id")
        if usuario_id is None:
            return None
        usuario = db.obter_usuario(usuario_id)
        # A sessao aponta pra um id que nao existe mais, ou a conta foi
        # desativada nesse meio-tempo por um administrador: trata como
        # deslogado JA NESTA REQUISICAO, sem esperar a sessao expirar por
        # conta propria -- e o que torna a desativacao de um usuario
        # efetiva de imediato, nao so na proxima vez que a sessao vencer.
        if usuario is None or not usuario["ativo"]:
            session.clear()
            return None
        g.usuario = usuario
        return None

    @app.before_request
    def _exigir_login_e_area():
        endpoint = request.endpoint or ""
        if (
            endpoint in ENDPOINTS_ISENTOS_DE_LOGIN
            or endpoint.startswith("static")
            or endpoint == "static"
        ):
            return None

        if g.usuario is None:
            if request.path.startswith("/api/"):
                return jsonify({"erro": "Sessão expirada. Faça login novamente."}), 401
            return redirect(url_for("auth.login", proxima=request.path))

        area_requerida = AREA_POR_ENDPOINT.get(endpoint)
        if area_requerida is not None:
            areas_aceitas = (area_requerida,) if isinstance(area_requerida, str) else area_requerida
            if not any(area_permitida(g.usuario["perfil"], area) for area in areas_aceitas):
                return _negar_acesso()

        perfis_extra = PERFIS_EXTRA_POR_ENDPOINT.get(endpoint)
        if perfis_extra is not None and g.usuario["perfil"] not in perfis_extra:
            return _negar_acesso()

        return None


# ---------------------------------------------------------------------------
# auth_bp: login/logout. Formulario classico (POST + redirect), sem
# depender de app.js -- a pagina de login precisa funcionar mesmo antes de
# qualquer chamada de API ser permitida.
# ---------------------------------------------------------------------------

auth_bp = Blueprint("auth", __name__)


def _destino_pos_login(bruto: str) -> str:
    """So aceita caminhos relativos internos ('/algo'), nunca uma URL
    absoluta ('//evil.com' ou 'https://evil.com') -- do contrario o
    parametro `proxima` vindo da querystring vira um open redirect: um
    link malicioso apontando para /login?proxima=https://... redirecionaria
    a vitima, ja autenticada, para um site externo logo depois do login."""
    if bruto and bruto.startswith("/") and not bruto.startswith("//"):
        return bruto
    return url_for("comum.index")


@auth_bp.route("/login", methods=["GET", "POST"])
@obter_limiter().limit("5 per minute")
def login():
    from .audit_log import log_login_falha, log_login_sucesso

    if g.usuario is not None:
        return redirect(url_for("comum.index"))

    erro = None
    proxima = request.values.get("proxima", "")

    if request.method == "POST":
        login_digitado = str(request.form.get("login", "")).strip()
        senha_digitada = request.form.get("senha", "")

        # Sanitizar dados sensíveis antes de qualquer log potencial
        sanitizar_log(login_digitado)

        usuario = db.obter_usuario_por_login(login_digitado)

        # Mensagem identica para "login inexistente" e "senha incorreta"
        # de proposito: diferenciar os dois casos permitiria a quem tenta
        # senhas ao acaso descobrir, so pela mensagem, quais logins
        # existem de verdade (enumeracao de contas).
        if (
            usuario is None
            or not usuario["ativo"]
            or not conferir_senha(senha_digitada, usuario["senha_hash"])
        ):
            motivo = "usuario_inexistente" if usuario is None else "credenciais_invalidas"
            if usuario and not usuario["ativo"]:
                motivo = "usuario_inativo"

            log_login_falha(login_digitado, motivo)
            erro = "Login ou senha inválidos."
        else:
            session.clear()
            session["usuario_id"] = usuario["id"]
            session.permanent = True
            db.registrar_login_usuario(usuario["id"])
            log_login_sucesso(usuario["id"], login_digitado)
            return redirect(_destino_pos_login(proxima))

    return render_template("login.html", erro=erro, proxima=proxima)


@auth_bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("auth.login"))


# ---------------------------------------------------------------------------
# usuarios_bp: administracao de contas (so area "usuarios" -- hoje somente
# o perfil administrador). Paginas HTML classicas (Jinja + POST/redirect),
# deliberadamente fora da SPA em app.js: um formulario server-rendered e
# muito mais simples de manter correto (sem estado de fetch/sessao
# duplicado em JS) para uma tela usada raramente, por pouquissimas
# pessoas.
# ---------------------------------------------------------------------------

usuarios_bp = Blueprint("usuarios", __name__, url_prefix="/usuarios")


@usuarios_bp.route("/", methods=["GET"])
def pagina_usuarios():
    return render_template(
        "usuarios.html",
        usuarios=db.listar_usuarios(),
        perfis=db.PERFIS_VALIDOS,
        perfil_label=PERFIL_LABEL,
        usuario_atual=g.usuario,
    )


@usuarios_bp.route("/novo", methods=["GET", "POST"])
def criar_usuario_rota():
    erro = None
    valores = {"nome": "", "login": "", "perfil": "operador", "ativo": True}

    if request.method == "POST":
        valores = {
            "nome": request.form.get("nome", ""),
            "login": request.form.get("login", ""),
            "perfil": request.form.get("perfil", ""),
            "ativo": bool(request.form.get("ativo")),
        }
        senha = request.form.get("senha", "")
        if len(senha) < SENHA_TAMANHO_MINIMO:
            erro = f"A senha precisa ter pelo menos {SENHA_TAMANHO_MINIMO} caracteres."
        else:
            try:
                db.criar_usuario({**valores, "senha_hash": gerar_hash_senha(senha)})
                return redirect(url_for("usuarios.pagina_usuarios"))
            except db.UsuarioInvalidoError as erro_validacao:
                erro = str(erro_validacao)

    return render_template(
        "usuario_form.html",
        modo="criar",
        usuario=valores,
        perfis=db.PERFIS_VALIDOS,
        perfil_label=PERFIL_LABEL,
        senha_tamanho_minimo=SENHA_TAMANHO_MINIMO,
        erro=erro,
    )


@usuarios_bp.route("/<int:usuario_id>/editar", methods=["GET", "POST"])
def editar_usuario_rota(usuario_id: int):
    usuario = db.obter_usuario(usuario_id)
    if usuario is None:
        return redirect(url_for("usuarios.pagina_usuarios"))

    erro = None
    if request.method == "POST":
        editando_a_si_mesmo = usuario_id == g.usuario["id"]
        perfil_novo = request.form.get("perfil", "")
        ativo_novo = bool(request.form.get("ativo"))

        # Uma pessoa administradora nao pode remover o proprio acesso de
        # administrador (nem se desativar) enquanto esta logada como essa
        # conta -- evita um auto-lockout confuso mesmo quando OUTRO
        # administrador ainda existe (o que passaria pela trava de
        # "ultimo administrador" em database.py sem ser barrado).
        if editando_a_si_mesmo and (perfil_novo != "administrador" or not ativo_novo):
            erro = (
                "Você não pode remover seu próprio acesso de administrador "
                "enquanto estiver logado. Peça para outro administrador "
                "fazer essa alteração."
            )
        else:
            valores = {
                "nome": request.form.get("nome", ""),
                "login": request.form.get("login", ""),
                "perfil": perfil_novo,
                "ativo": ativo_novo,
            }
            senha = request.form.get("senha", "")
            if senha:
                if len(senha) < SENHA_TAMANHO_MINIMO:
                    erro = f"A senha precisa ter pelo menos {SENHA_TAMANHO_MINIMO} caracteres."
                else:
                    valores["senha_hash"] = gerar_hash_senha(senha)
            if erro is None:
                try:
                    db.atualizar_usuario(usuario_id, valores)
                    return redirect(url_for("usuarios.pagina_usuarios"))
                except db.UsuarioInvalidoError as erro_validacao:
                    erro = str(erro_validacao)
            usuario = {**usuario, **valores}

    return render_template(
        "usuario_form.html",
        modo="editar",
        usuario=usuario,
        perfis=db.PERFIS_VALIDOS,
        perfil_label=PERFIL_LABEL,
        senha_tamanho_minimo=SENHA_TAMANHO_MINIMO,
        erro=erro,
    )


@usuarios_bp.route("/<int:usuario_id>/excluir", methods=["POST"])
def excluir_usuario_rota(usuario_id: int):
    if usuario_id == g.usuario["id"]:
        # Mesma logica do bloqueio em editar_usuario_rota: excluir a
        # propria conta enquanto logado nela e sempre um auto-lockout,
        # mesmo quando outro administrador existe.
        flash("Você não pode excluir sua própria conta enquanto estiver logado.", "erro")
        return redirect(url_for("usuarios.pagina_usuarios"))
    try:
        db.excluir_usuario(usuario_id)
    except db.UltimoAdministradorError as erro:
        flash(str(erro), "erro")
    return redirect(url_for("usuarios.pagina_usuarios"))
