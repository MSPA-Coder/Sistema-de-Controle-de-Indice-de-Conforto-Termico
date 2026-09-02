"""
auth.py
========
Autenticacao e controle de acesso por pessoa nas rotas publicas do ICT.
Este modulo e o unico lugar do sistema que:

- Sabe como transformar uma senha em texto puro num hash (via
  `sharedauth.passwords`) e como conferir uma senha digitada contra esse
  hash. `database.py` guarda `senha_hash` como uma string opaca e nunca ve
  a senha real.
- Decide, a partir do PERFIL de uma sessao, quais AREAS da interface (que
  mapeiam 1:1 aos grupos de abas em `templates/index.html` -- ver
  README.md, secao "Organizacao das abas por papel de uso") esse perfil
  pode acessar.
- Registra os hooks `before_request` que carregam `g.usuario` e aplicam a
  decisao de area a TODA rota do app, inclusive a pagina inicial.

  "TODA rota" passou a ser verdade em 29/08/2026, e ate ali nao era: o hook
  so conferia endpoint presente em `AREA_POR_ENDPOINT` e liberava o resto,
  entao seis leituras respondiam a qualquer perfil autenticado. Hoje o que
  nao esta mapeado e negado, e o que pode ficar aberto esta escrito em
  `ENDPOINTS_ABERTOS_A_QUALQUER_PERFIL` com o motivo. Uma afirmacao dessas
  no docstring so vale acompanhada do teste que a mede -- ver
  `tests/test_autorizacao_por_area.py`.

Sessao, CSRF, o gate de "exige login" e o rate-limit do login vêm de
`sharedauth` (chamados em `app_factory.criar_app_ict`), compartilhados com
os outros apps Flask do mantenedor. Este módulo só decide o que é específico
deste app: os 6 perfis e o mapeamento perfil→área, que `sharedauth`
deliberadamente não decide.

A separacao de areas e so a metade "isso e permitido" da decisao. A outra
metade -- "o template so MOSTRA o botao/aba que a pessoa pode usar" -- fica
em `templates/index.html` (`areas_permitidas`, injetado por
`rotas_comuns.index`). As duas metades tem que concordar, mas so a
metade AQUI e a que realmente impede uma chamada de API indevida: esconder
um botao no HTML nunca e controle de acesso de verdade.
"""

from __future__ import annotations

import contextlib
import os
import secrets
from pathlib import Path
from typing import TYPE_CHECKING

from flask import (
    Blueprint,
    Flask,
    current_app,
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from sharedauth.access import url_proximo_seguro
from sharedauth.passwords import (
    MIN_PASSWORD_LENGTH,
    SenhaMuitoCurtaError,
    gerar_senha_temporaria,
    validar_tamanho,
    validar_troca,
)
from sharedauth.passwords import conferir_hash as _conferir_hash
from sharedauth.passwords import gerar_hash as _gerar_hash

# `sharedauth.secrets` (biblioteca), nao o `secrets` da stdlib importado acima
# -- este arquivo usa os dois, e sao coisas diferentes.
from sharedauth.secrets import DIRETORIO_SECRETS_COMPOSE, resolver_segredo
from sharedauth.session import marca_de_sessao, marcas_conferem

from . import database as db

if TYPE_CHECKING:
    from flask.typing import ResponseReturnValue

# ---------------------------------------------------------------------------
# Perfis, areas e rotulos de exibicao
# ---------------------------------------------------------------------------

# Cada area corresponde a um grupo de abas da interface. "dashboard" e a
# unica presente em TODOS os perfis porque a aba Dashboard nunca tem uma
# acao de escrita -- e so exibicao, sem risco em liberar para qualquer
# pessoa autenticada.
#
# Por isso "dashboard" NAO E UMA AREA COMO AS OUTRAS (CT-05): na pratica, ela
# equivale a "qualquer conta autenticada" -- e mapear um endpoint nela e o
# mesmo que declara-lo aberto a todo mundo que fez login, sem excecao nenhuma.
# Foi essa propriedade, nao documentada no ponto de uso, que deixou passar
# CT-01: a rota estava corretamente mapeada em "dashboard", e ninguem notou
# que a carga (fiacao Modbus) nao cabia em "qualquer conta autenticada".
# `test_area_dashboard_e_universal_e_so_de_leitura` fixa as duas metades desta
# garantia: todo perfil precisa ter "dashboard", e nenhum endpoint mapeado
# nela pode ser de escrita.
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
            "auditoria",
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

# Re-exportado de sharedauth.passwords: piso comum aos apps Flask do
# mantenedor, não mais uma constante própria deste projeto.
SENHA_TAMANHO_MINIMO = MIN_PASSWORD_LENGTH

#: Onde a marca da senha em vigor fica guardada na sessao. Ver
#: `registrar_carregamento_usuario`: e ela que faz a troca de senha derrubar as
#: sessoes abertas em outros lugares.
CHAVE_MARCA_DE_SENHA = "marca_senha"


def _marca_da_senha_em_vigor(usuario_id: int) -> str:
    """Marca calculada a partir do hash guardado hoje para esta conta."""
    return marca_de_sessao(
        db.obter_hash_de_senha(usuario_id),
        chave_secreta=current_app.secret_key,
    )


# ---------------------------------------------------------------------------
# Hash de senha -- sharedauth.passwords (Werkzeug por baixo, piso comum aos
# apps Flask do mantenedor).
# ---------------------------------------------------------------------------


def gerar_hash_senha(senha: str) -> str:
    return _gerar_hash(senha)


def conferir_senha(senha: str, hash_: str) -> bool:
    if not senha or not hash_:
        return False
    try:
        return _conferir_hash(hash_, senha)
    except ValueError:
        # Hash malformado ou de um algoritmo que esta versao do Werkzeug
        # nao reconhece: trata como senha incorreta em vez de propagar a
        # excecao ate o cliente HTTP.
        return False


# ---------------------------------------------------------------------------
# Chave de sessao
#
# Ordem: segredo do Compose, variavel de ambiente, e -- SO em desenvolvimento
# ou teste -- geracao persistida em `instance/`. Em producao, faltar a chave e
# erro que impede a aplicacao de subir.
#
# A geracao silenciosa fica restrita aos ambientes em que perder a chave e
# invalidar sessoes e aceitavel. Nos demais, uma configuracao incompleta precisa
# falhar na inicializacao em vez de depender do volume `app_instance`.
# ---------------------------------------------------------------------------


def _ambiente_permite_gerar_chave() -> bool:
    """Só desenvolvimento e teste podem gerar chave em vez de exigi-la.

    Usa as MESMAS variaveis que o resto do projeto ja usa para essa distincao
    (`app_factory` valida `CONFORTO_DEBUG` contra `CONFORTO_DEVELOPMENT`, e o
    `conftest` liga `CONFORTO_TESTING`), em vez de inventar um terceiro sinal
    de "isto nao e producao" -- que e como se acaba com tres definicoes
    discordantes de ambiente.
    """
    for nome in ("CONFORTO_DEVELOPMENT", "CONFORTO_TESTING"):
        valor = os.environ.get(nome, "").strip().lower()
        if valor in ("1", "true", "sim", "on"):
            return True
    return False


def obter_chave_secreta() -> str:
    # `aceitar_variavel=False`: a variável direta é tratada logo abaixo, com
    # semântica própria deste app. `caminho_esperado` mantém a checagem estrita
    # que já existia aqui -- sem ela, `*_FILE` deixaria de ser configuração de
    # implantação e viraria seletor arbitrário de arquivo.
    do_arquivo = resolver_segredo(
        "CONFORTO_SECRET_KEY",
        aceitar_variavel=False,
        caminho_esperado=DIRETORIO_SECRETS_COMPOSE / "secret_key",
    )
    if do_arquivo:
        return do_arquivo

    variavel_ambiente = os.environ.get("CONFORTO_SECRET_KEY")
    if variavel_ambiente:
        return variavel_ambiente

    if not _ambiente_permite_gerar_chave():
        raise RuntimeError(
            "Chave de sessão ausente. Em produção ela é obrigatória: defina "
            "CONFORTO_SECRET_KEY_FILE apontando para /run/secrets/secret_key "
            "(o Compose já monta esse segredo) ou CONFORTO_SECRET_KEY.\n"
            "Para gerar o arquivo: python scripts/configurar_segredos.py\n"
            "Gerar a chave sozinho faria a aplicação subir com uma "
            "configuração incompleta, e o estrago só apareceria quando o "
            "volume se perdesse — deslogando todo mundo sem explicação. "
            "Ver docs/adr/007-chave-sessao-como-segredo.md."
        )

    caminho = Path(db.INSTANCE_DIR) / "secret_key.txt"
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

    Mesmo padrao de `obter_chave_secreta` acima, incluindo a
    precedencia da variavel de ambiente e a mesma trava de geracao (CT-04,
    fechada em 02/09/2026: ate ali este caminho gerava e persistia um token
    em silencio fora de desenvolvimento, e a ausencia de configuracao virava
    uma indisponibilidade sem causa aparente em vez de um erro na
    inicializacao). Instalacoes em que coletor e "outra parte" rodam em
    MAQUINAS diferentes (nao compartilham `instance/`) precisam definir
    `CONFORTO_INTERNO_TOKEN` explicitamente e IGUAL nos dois processos --
    sem isso, cada lado geraria e persistiria um token diferente e a chamada
    interna sempre falharia com 403. Essa limitacao acompanha a mesma
    premissa ja documentada no README para a implantação em contêineres (as
    duas partes compartilham a mesma origem de segredo)."""
    variavel_ambiente = os.environ.get("CONFORTO_INTERNO_TOKEN")
    if variavel_ambiente:
        return variavel_ambiente
    token = resolver_segredo(
        "CONFORTO_INTERNO_TOKEN",
        aceitar_variavel=False,
        caminho_esperado=DIRETORIO_SECRETS_COMPOSE / "internal_token",
    )
    if token is not None:
        return token

    if not _ambiente_permite_gerar_chave():
        raise RuntimeError(
            "Token interno ausente. Em produção ele é obrigatório e precisa ser "
            "IGUAL nos dois processos: defina CONFORTO_INTERNO_TOKEN_FILE "
            "apontando para /run/secrets/internal_token (o Compose já monta "
            "esse segredo) ou CONFORTO_INTERNO_TOKEN. Gerar um token sozinho "
            "faria ICT e coletor discordarem, e a API interna recusaria tudo "
            "com 403 -- uma indisponibilidade sem causa aparente, em vez de "
            "um erro de inicialização que nomeia a variável que falta."
        )

    caminho = Path(db.INSTANCE_DIR) / "interno_token.txt"
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
        "static",
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
    "administracao.atualizar_agregados_historicos": "sistema",
    "administracao.listar_auditoria": "auditoria",
    "comum.atualizar_agregados_zona": "historico",
    # --- comum_bp: as LEITURAS das abas Historico e Operacao ------------
    # Estas seis ficaram fora do mapa ate 29/08/2026, e enquanto isso
    # respondiam a qualquer perfil autenticado. O template escondia a aba
    # Historico de quem nao tem a area, e as quatro leituras dela
    # continuavam entregando as medicoes; a ESCRITA da mesma aba
    # (`atualizar_agregados_zona`, logo acima) sempre exigiu area. Ou seja:
    # dentro do mesmo arquivo, o botao estava fechado e a porta ao lado,
    # aberta.
    "comum.historico_zona": "historico",
    "comum.historico_leituras": "historico",
    "comum.agregados_15min_zona": "historico",
    "comum.resumo_horario_zona": "historico",
    "comum.status_operacao": "operacao",
    "comum.eventos_operacao": "operacao",
    # "dashboard" equivale a "qualquer conta autenticada" (ver o comentario
    # em AREAS_POR_PERFIL, acima) -- exigi-la nao restringe ninguem hoje.
    # Vale declarar mesmo assim: e o que faz a area existir no mapa em vez de
    # so na tabela de perfis, e o que faz um perfil futuro sem "dashboard"
    # ser obedecido aqui em vez de silenciosamente ignorado. Por ser
    # universal, so pode ser exigida por LEITURA -- nunca por um endpoint de
    # escrita, que ficaria aberto a qualquer pessoa logada sem excecao.
    "comum.listar_zonas": "dashboard",
    "comum.historicos_recentes_zonas": "dashboard",
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
    "usuarios.redefinir_senha_rota": "usuarios",
}

# Endpoints que respondem a QUALQUER perfil autenticado. Estar aqui e uma
# decisao consciente com motivo escrito -- e o unico jeito de uma rota passar
# sem area, agora que `_exigir_area` nega o que nao esta mapeado.
ENDPOINTS_ABERTOS_A_QUALQUER_PERFIL: dict[str, str] = {
    "comum.index": (
        "a casca da SPA, e o destino de `_negar_acesso`. Exigir area aqui "
        "seria o laco: quem nao a tivesse seria recusado e mandado para a "
        "propria rota que acabou de recusa-lo. Ela nao entrega dado de "
        "zona -- so o HTML, que ja mostra apenas as abas do perfil."
    ),
    "comum.configuracao_interface": (
        "metadados termicos (nomes de especie, indice e campos) que a "
        "interface le antes de saber qual aba abrir. Nao ha leitura de "
        "sensor nem de zona: e o vocabulario da tela, igual para todo perfil."
    ),
    "auth.logout": "encerrar a sessao nao pode depender de area nenhuma",
    "auth.trocar_senha": (
        "trocar a propria senha e a conta de quem esta logado, nao "
        "administracao de conta alheia -- exigir a area 'usuarios' aqui "
        "deixaria todo perfil que nao a tem preso na trava de senha "
        "temporaria, sem a tela que a resolve."
    ),
    "sharedauth_ui.static": (
        "CSS e JS do componente comum de aviso, pedidos por `index.html`. "
        "Sao dois estaticos da biblioteca, sem dado do app."
    ),
}

# Restricao ADICIONAL: mesmo com a area liberada, so os perfis listados
# podem chamar o endpoint. Ver comentario de PERFIS_QUE_PODEM_EXCLUIR_DADOS_ENTRADA.
PERFIS_EXTRA_POR_ENDPOINT: dict[str, frozenset[str]] = {
    "dados_entrada.excluir_medicoes": PERFIS_QUE_PODEM_EXCLUIR_DADOS_ENTRADA,
    "dados_entrada.apagar_historico": PERFIS_QUE_PODEM_EXCLUIR_DADOS_ENTRADA,
}


def area_permitida(perfil: str, area: str) -> bool:
    return area in AREAS_POR_PERFIL.get(perfil, frozenset())


#: As abas na ordem em que `templates/index.html` as apresenta, cada uma com a
#: area que a libera. Serve para decidir qual delas abre.
ABAS_NA_ORDEM: tuple[tuple[str, str], ...] = (
    ("principal", "dashboard"),
    ("analises", "analises"),
    ("historico", "historico"),
    ("operacao", "operacao"),
    ("zonas", "cadastro"),
    ("configuracoes", "configuracoes"),
    ("sistema", "sistema"),
    ("auditoria", "auditoria"),
    ("dados-entrada", "dados_entrada"),
)


def primeira_aba_permitida(perfil: str) -> str | None:
    """A aba que abre para este perfil: a primeira que ele pode ver.

    Derivada, e nao fixa em "principal", pelo mesmo motivo que o destino do
    login do ControleBancario deixou de ser uma tela concreta: aba inicial
    fixa obriga a area dela a estar em todos os perfis, e essa obrigacao nao
    fica escrita em lugar nenhum -- some no dia em que alguem monta um perfil
    sem ela, e a tela abre vazia.
    """
    for aba, area in ABAS_NA_ORDEM:
        if area_permitida(perfil, area):
            return aba
    return None


def usuario_atual() -> dict | None:
    """Le `g.usuario`, carregado pelo hook `_carregar_usuario_da_sessao`
    (ver `registrar_autenticacao`). Fora do ciclo de requisicao (ex.: um
    teste chamando isto diretamente sem passar por uma rota), devolve
    `None` em vez de levantar `RuntimeError` por falta de contexto."""
    return getattr(g, "usuario", None)


def _negar_acesso() -> ResponseReturnValue:
    if request.path.startswith("/api/"):
        return jsonify({"erro": "Seu perfil não tem acesso a esta função."}), 403
    return redirect(url_for("comum.index"))


def registrar_carregamento_usuario(app: Flask) -> None:
    """Registra o hook que carrega `g.usuario` a partir da sessão.

    Precisa rodar ANTES do gate de login do `sharedauth.access` (que só
    decide "autenticado ou não" a partir de `g.usuario is not None`) e antes
    de `registrar_controle_de_area` (que consulta `g.usuario["perfil"]`).
    """

    @app.before_request
    def _carregar_usuario_da_sessao() -> None:
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
        # A senha mudou depois que esta sessao comecou: derruba. Sem isto,
        # trocar a senha nao expulsava quem tivesse entrado com a antiga --
        # exatamente o que quem troca por desconfiar de acesso indevido
        # acredita estar fazendo. Sessao sem marca (de antes desta mudanca)
        # tambem cai, uma vez so, no primeiro acesso depois do deploy.
        if not marcas_conferem(
            session.get(CHAVE_MARCA_DE_SENHA), _marca_da_senha_em_vigor(usuario_id)
        ):
            session.clear()
            return None
        g.usuario = usuario
        return None


def registrar_controle_de_area(app: Flask) -> None:
    """Registra o hook que confere a area exigida por endpoint.

    Nega por padrao: endpoint sem entrada em `AREA_POR_ENDPOINT` so passa se
    estiver declarado em `ENDPOINTS_ISENTOS_DE_LOGIN` (nem login exige) ou em
    `ENDPOINTS_ABERTOS_A_QUALQUER_PERFIL` (exige login, dispensa area).

    Precisa rodar DEPOIS do gate de login do `sharedauth.access`: por isso
    não repete a checagem de `g.usuario is None` -- se a requisição chegou
    até aqui, já passou pelo gate e `g.usuario` está garantidamente
    preenchido (exceto nos endpoints isentos de login, que também são
    isentos de área)."""

    @app.before_request
    def _exigir_area() -> ResponseReturnValue | None:
        # URL que nao casa com rota nenhuma: deixa o Flask responder 404, como
        # faz o gate de login do `sharedauth.access`. Nao ha o que autorizar.
        if request.endpoint is None:
            return None

        endpoint = request.endpoint
        if endpoint in ENDPOINTS_ISENTOS_DE_LOGIN:
            return None
        if endpoint in ENDPOINTS_ABERTOS_A_QUALQUER_PERFIL:
            return None

        area_requerida = AREA_POR_ENDPOINT.get(endpoint)
        if area_requerida is None:
            # Rota sem area declarada NEGA, e nao passa. Ate 29/08/2026 era o
            # contrario, e o preco foi seis leituras respondendo a quem o
            # template escondia a aba correspondente. Com a negacao por
            # padrao, esquecer o mapeamento vira uma rota que nao funciona --
            # visivel na hora, em vez de uma porta aberta que ninguem nota.
            return _negar_acesso()

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


@auth_bp.route("/login", methods=["GET", "POST"])
def login() -> ResponseReturnValue:
    from .audit_log import log_login_falha, log_login_sucesso

    if g.usuario is not None:
        return redirect(url_for("comum.index"))

    erro = None
    # Nome do parametro e "next", nao "proxima": sharedauth.access.requer_login
    # (que gera o redirect para ca quando a sessao expira) sempre usa "next".
    #
    # Ate 31/08/2026 este valor era so ecoado de volta no campo escondido do
    # formulario e NUNCA lido no sucesso -- o campo existia e nao servia para
    # nada, e havia teste registrando isso como decisao. Nao era: o destino
    # simplesmente nunca foi implementado, e a mesma checagem estava escrita
    # a mao em outros dois apps. Agora a decisao mora em
    # `sharedauth.access.url_proximo_seguro` e vale nos tres.
    #
    # `requer_login` so gera `next` para caminho de pagina: rota sob `/api/`
    # recebe 401 JSON, e nunca chega aqui.
    proximo = url_proximo_seguro(request.values.get("next"))

    if request.method == "POST":
        login_digitado = str(request.form.get("login", "")).strip()
        senha_digitada = request.form.get("senha", "")

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
            session[CHAVE_MARCA_DE_SENHA] = marca_de_sessao(
                usuario["senha_hash"], chave_secreta=current_app.secret_key
            )
            session.permanent = True
            db.registrar_login_usuario(usuario["id"])
            log_login_sucesso(usuario["id"], login_digitado)
            return redirect(proximo or url_for("comum.index"))

    return render_template("login.html", erro=erro, proxima=proximo or "")


@auth_bp.route("/logout", methods=["POST"])
def logout() -> ResponseReturnValue:
    session.clear()
    return redirect(url_for("auth.login"))


@auth_bp.route("/minha-senha", methods=["GET", "POST"])
def trocar_senha() -> ResponseReturnValue:
    """Troca da propria senha, obrigatoria ou voluntaria.

    Fica no `auth_bp`, e nao no `usuarios_bp`: aquele blueprint e a area
    "usuarios" (so administrador) e trata de contas alheias; isto e a conta de
    quem esta logado, e vale para qualquer perfil -- por isso o endpoint entra
    em `ENDPOINTS_ABERTOS_A_QUALQUER_PERFIL`.

    Quando `trocar_senha` esta ligado, `requer_troca_de_senha` (registrado em
    `app_factory`) prende a sessao aqui ate a troca acontecer. A diferenca
    entre os dois casos e so de apresentacao: sob obrigacao a tela nao oferece
    o caminho de volta, que o portao devolveria para ca de qualquer jeito.
    """
    obrigatoria = bool(g.usuario.get("trocar_senha"))
    erro = None

    if request.method == "POST":
        # `obter_usuario_por_login` traz a linha inteira; `g.usuario` vem de
        # `_linha_usuario_publica`, que remove o hash de proposito.
        completo = db.obter_usuario_por_login(g.usuario["login"])
        try:
            validar_troca(
                hash_atual=completo["senha_hash"] if completo else None,
                senha_atual=request.form.get("senha_atual", ""),
                senha_nova=request.form.get("senha_nova", ""),
                confirmacao=request.form.get("senha_confirmacao", ""),
            )
        except ValueError as recusa:
            # Todas as recusas de `validar_troca` sao `ValueError`, e a
            # mensagem de cada uma ja e adequada a pessoa.
            erro = str(recusa)
        else:
            novo_hash = gerar_hash_senha(request.form.get("senha_nova", ""))
            db.trocar_senha_propria(g.usuario["id"], novo_hash)
            # Renova a marca DESTA sessao. O efeito que se quer e derrubar as
            # OUTRAS; sem isto a pessoa seria deslogada pela propria troca, na
            # requisicao seguinte.
            session[CHAVE_MARCA_DE_SENHA] = marca_de_sessao(
                novo_hash, chave_secreta=current_app.secret_key
            )
            # Sem `flash()`: neste app so `usuarios.html` renderiza mensagem
            # de sessao, e o destino aqui e a SPA. Um aviso guardado agora
            # ficaria esperando ate alguem abrir a tela de usuarios, onde
            # apareceria fora de contexto -- e sem CSS, porque so a categoria
            # "erro" tem estilo.
            return redirect(url_for("comum.index"))

    return render_template(
        "trocar_senha.html",
        obrigatoria=obrigatoria,
        erro=erro,
        senha_tamanho_minimo=SENHA_TAMANHO_MINIMO,
    )


# ---------------------------------------------------------------------------
# usuarios_bp: administracao de contas (so area "usuarios" -- hoje somente
# o perfil administrador). Paginas HTML classicas (Jinja + POST/redirect),
# deliberadamente fora da SPA em app.js: um formulario server-rendered e
# muito mais simples de manter correto (sem estado de fetch/sessao
# duplicado em JS) para uma tela usada raramente, por pouquissimas
# pessoas.
# ---------------------------------------------------------------------------

usuarios_bp = Blueprint("usuarios", __name__, url_prefix="/usuarios")


def _render_usuarios(**extra) -> ResponseReturnValue:
    """Tela de usuarios. `extra` existe para a senha temporaria.

    Ela **nao pode ir por `flash()`**: o `flash` do Flask guarda a mensagem na
    sessao, e a sessao e um cookie assinado -- assinado nao e cifrado. Uma
    senha em texto claro ali sairia legivel no cabecalho da resposta. Vai como
    variavel de contexto, que morre no HTML desta resposta.
    """
    return render_template(
        "usuarios.html",
        usuarios=db.listar_usuarios(),
        perfis=db.PERFIS_VALIDOS,
        perfil_label=PERFIL_LABEL,
        usuario_atual=g.usuario,
        **extra,
    )


@usuarios_bp.route("/", methods=["GET"])
def pagina_usuarios() -> ResponseReturnValue:
    return _render_usuarios()


@usuarios_bp.route("/<int:usuario_id>/redefinir-senha", methods=["POST"])
def redefinir_senha_rota(usuario_id: int) -> ResponseReturnValue:
    """Redefine a senha de outra conta e mostra a senha temporaria gerada.

    Quem administra nao escolhe mais a senha de outra pessoa: uma senha
    escolhida por ele e uma senha que ele conhece e que tende a se repetir
    entre contas. O sistema sorteia, mostra uma vez, e o dono e obrigado a
    trocar no primeiro acesso.

    Responde **renderizando** a tela, e nao com redirect: um redirect perderia
    a unica copia em texto claro da senha no caminho.
    """
    usuario = db.obter_usuario(usuario_id)
    if usuario is None:
        return redirect(url_for("usuarios.pagina_usuarios"))

    senha_temporaria = gerar_senha_temporaria()
    try:
        db.redefinir_senha_usuario(usuario_id, gerar_hash_senha(senha_temporaria))
    except db.UsuarioInvalidoError as erro:
        flash(str(erro), "erro")
        return redirect(url_for("usuarios.pagina_usuarios"))

    return _render_usuarios(senha_temporaria=senha_temporaria, senha_de=usuario["login"])


@usuarios_bp.route("/novo", methods=["GET", "POST"])
def criar_usuario_rota() -> ResponseReturnValue:
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
        try:
            validar_tamanho(senha)
        except SenhaMuitoCurtaError as erro_senha:
            erro = str(erro_senha)
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
def editar_usuario_rota(usuario_id: int) -> ResponseReturnValue:
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
            # A edicao nao mexe mais em senha: quem precisa redefinir usa a
            # acao "Redefinir senha" da lista, que sorteia uma temporaria e
            # obriga a troca. Manter um campo de senha aqui seria o caminho
            # pelo qual um administrador continuaria escolhendo -- e sabendo
            # -- a senha de outra pessoa.
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
def excluir_usuario_rota(usuario_id: int) -> ResponseReturnValue:
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
