"""
Composição dos dois processos da aplicação.

O ICT é a única interface HTTP pública: serve todas as abas, autentica
pessoas, aplica permissões e persiste configurações de domínio. O coletor
é um serviço privado e contínuo: executa a malha de controle e expõe
somente uma API interna autenticada para ações que precisam do Modbus.

As fábricas são deliberadamente distintas. Criar o ICT nunca importa
``coletor.estado``, ``modbus_client`` ou ``ZonaService``; toda travessia
para o hardware ocorre pela API interna do coletor.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, cast

from flask import Flask, g, jsonify, request
from flask.json.provider import DefaultJSONProvider
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from sharedauth.access import requer_login
from sharedauth.csrf import iniciar_csrf
from sharedauth.health import registrar_health
from sharedauth.ratelimit import LIMITE_LOGIN_PADRAO
from sharedauth.security import CONTENT_SECURITY_POLICY as POLITICA_FECHADA
from sharedauth.security import SECURITY_HEADERS, registrar_cabecalhos
from sharedauth.session import configurar_sessao
from werkzeug.exceptions import HTTPException
from werkzeug.middleware.proxy_fix import ProxyFix

from . import auth, env_config
from . import database as db

if TYPE_CHECKING:
    from flask.sansio.app import App

# Útil para execução local. No Docker, as variáveis injetadas pelo Compose
# têm precedência e pertencem à implantação, não à interface ICT.
env_config.carregar()

MENSAGEM_ERRO_INTERNO = "Erro interno inesperado. Consulte o log do servidor para detalhes."
PROCESSOS_APP = ("ict", "coletor")
HOSTS_LOOPBACK = frozenset({"127.0.0.1", "::1", "localhost"})
PALAVRA_CONFIRMACAO_EXCLUSAO = "APAGAR"


def confirmacao_de_exclusao_valida(dados: dict) -> bool:
    """Confirmação server-side para apagar toda a série temporal de leituras.

    Mais de uma rota zera `leituras`/`leituras_recentes_zona`/
    `agregados_15min`/`resumos_horarios` de uma vez (dados de entrada e
    administração do ICT) -- ambas precisam desta mesma trava, porque um
    `confirm()` só existe no navegador: uma chamada direta (curl, clique
    repetido, script) com sessão válida passa reto se o servidor não checar
    nada. Compartilhada em vez de duplicada para as duas nunca divergirem de
    novo.
    """
    return str(dados.get("confirmacao", "")).strip().upper() == PALAVRA_CONFIRMACAO_EXCLUSAO

# Conjunto defensivo e CSP vem de `sharedauth.security` -- eram um dicionario
# e uma string mantidos iguais a mao aqui e no MegaSena, com o comentario
# "manter igual em todos" copiado junto, e mesmo assim as copias divergiram.
#
# Reexportados como nome de modulo, e nao usados so dentro do `after_request`,
# porque a suite minima afirma sobre a politica sem construir a aplicacao.
#
# A politica aqui e a fechada: `img-src 'self'`, sem `data:`. O `data:` que
# estava nesta constante era sobra -- nenhum template, CSS ou JS deste projeto
# usa URI `data:`; o favicon e arquivo servido por rota (`comum.favicon`), nao
# SVG embutido. Quem precisa da folga e o MegaSena, pelo favicon embutido no
# `<link rel=icon>`, e la ela e pedida explicitamente.
CABECALHOS_SEGURANCA = SECURITY_HEADERS
CONTENT_SECURITY_POLICY = POLITICA_FECHADA
CONFIG_SERVIDOR_PATH = Path(__file__).resolve().parents[1] / "config" / "servidor.json"


def _criar_limiter(app: Flask) -> Limiter:
    """Configura rate limiting para proteção contra brute-force e DoS."""
    limiter = Limiter(
        app=app,
        key_func=get_remote_address,
        default_limits=["100 per hour", "20 per minute"],
        storage_uri="memory://",
        strategy="fixed-window",
        enabled=not app.testing,
    )
    return limiter


def _ler_config_servidor(processo: str) -> dict:
    try:
        with CONFIG_SERVIDOR_PATH.open("r", encoding="utf-8") as arquivo:
            bruto = json.load(arquivo)
    except (OSError, json.JSONDecodeError):
        return {}

    if not isinstance(bruto, dict):
        return {}

    config = {}
    for chave in ("padrao", processo):
        valores = bruto.get(chave)
        if isinstance(valores, dict):
            config.update(valores)
    return config


def _coagir_bool(valor, padrao: bool) -> bool:
    if valor is None:
        return padrao
    if isinstance(valor, bool):
        return valor
    return str(valor).strip().lower() in ("1", "true", "sim", "on")


def _coagir_int(valor, padrao: int) -> int:
    if valor is None:
        return padrao
    try:
        return int(valor)
    except (TypeError, ValueError):
        return padrao


def _ler_bool_env(nome: str, padrao: bool) -> bool:
    return _coagir_bool(os.environ.get(nome), padrao)


def _ler_int_env(nome: str, padrao: int) -> int:
    return _coagir_int(os.environ.get(nome), padrao)


@dataclass(frozen=True)
class AppConfig:
    """Configuração HTTP de um dos processos."""

    debug: bool
    host: str
    port: int
    threaded: bool
    max_content_length: int
    development: bool = False

    @classmethod
    def from_env(cls, processo: str = "ict") -> AppConfig:
        if processo not in PROCESSOS_APP:
            raise ValueError(f"processo inválido: {processo!r} (esperado um de {PROCESSOS_APP})")

        config_arquivo = _ler_config_servidor(processo)
        config = cls(
            debug=_ler_bool_env("CONFORTO_DEBUG", _coagir_bool(config_arquivo.get("debug"), False)),
            host=os.environ.get("CONFORTO_HOST", str(config_arquivo.get("host") or "127.0.0.1")),
            port=_ler_int_env("CONFORTO_PORT", _coagir_int(config_arquivo.get("port"), 5000)),
            threaded=_ler_bool_env(
                "CONFORTO_THREADED",
                _coagir_bool(config_arquivo.get("threaded"), True),
            ),
            max_content_length=_ler_int_env(
                "CONFORTO_MAX_CONTENT_LENGTH",
                _coagir_int(config_arquivo.get("max_content_length"), 1_000_000),
            ),
            development=_ler_bool_env("CONFORTO_DEVELOPMENT", False),
        )
        _validar_debug(config)
        return config


def _validar_debug(config: AppConfig) -> None:
    """Impede debugger Flask fora de desenvolvimento local explícito."""
    if not config.debug:
        return
    if not config.development:
        raise RuntimeError("CONFORTO_DEBUG exige CONFORTO_DEVELOPMENT=1.")
    if config.host not in HOSTS_LOOPBACK:
        raise RuntimeError("CONFORTO_DEBUG só pode escutar em host de loopback.")


class ProvedorJSON(DefaultJSONProvider):
    """Serializador JSON com suporte às tabelas imutáveis do domínio."""

    @staticmethod
    def default(o):
        if isinstance(o, MappingProxyType):
            return dict(o)
        return DefaultJSONProvider.default(o)


def _criar_app_base(processo: str, config: AppConfig) -> Flask:
    app = Flask(__name__)
    app.json = ProvedorJSON(cast("App", app))
    app.config["MAX_CONTENT_LENGTH"] = config.max_content_length
    app.config["CONFORTO_PROCESSO"] = processo
    app.config["CONFORTO_DEBUG"] = config.debug
    # `app.testing` (padrão Flask) é o único sinal de "isto é uma app de
    # teste" -- deliberadamente independente do backend de persistência
    # (PostgreSQL). `CONFORTO_TESTING` não é definida em produção/Docker;
    # fica disponível para quem precisar instanciar a fábrica fora da suíte
    # atual (que é caixa-branca e não instancia a app). Ver
    # `auth._proteger_csrf`, que usa `app.testing` para dispensar CSRF nos
    # testes que não são o teste dedicado dessa proteção.
    app.testing = _ler_bool_env("CONFORTO_TESTING", False)

    # Inicializar rate limiting. A referência também permite isentar os
    # health checks, que são verificações internas recorrentes do Docker.
    app.extensions["conforto_rate_limiter"] = _criar_limiter(app)

    db.iniciar_banco()

    registrar_cabecalhos(app)

    @app.after_request
    def _nao_guardar_resposta_de_api(resposta):
        # Especifico deste projeto, nao do conjunto comum: as rotas `/api/`
        # servem leitura de sensor, que nao pode ser reaproveitada do cache.
        if request.path.startswith("/api/"):
            resposta.headers["Cache-Control"] = "no-store"
        return resposta

    @app.errorhandler(Exception)
    def tratar_erro_inesperado(erro):
        if isinstance(erro, HTTPException):
            if request.path.startswith("/api/"):
                return jsonify({"erro": erro.description}), erro.code or 500
            return erro

        app.logger.exception("Erro não tratado em %s", request.path)
        if request.path.startswith("/api/"):
            return jsonify({"erro": MENSAGEM_ERRO_INTERNO}), 500
        raise erro

    return app


def criar_app_ict(config: AppConfig | None = None) -> Flask:
    """Cria a única aplicação acessada por pessoas e navegadores."""

    config = config or AppConfig.from_env("ict")
    app = _criar_app_base("ict", config)
    limiter: Limiter = app.extensions["conforto_rate_limiter"]

    app.secret_key = auth.obter_chave_secreta()
    configurar_sessao(
        app,
        nome_cookie=os.environ.get("CONFORTO_SESSION_COOKIE_NAME", "conforto_session").strip()
        or "conforto_session",
        https_obrigatorio=_ler_bool_env("CONFORTO_COOKIE_SEGURO", False),
        duracao_horas=12,
    )

    # Este era o único dos quatro projetos sem `ProxyFix`, e roda atrás do
    # nginx. O efeito não é cosmético:
    #
    # 1. O `key_func=get_remote_address` do limitador via o IP do gateway do
    #    Docker, igual para todo mundo. O `default_limits` de "100 por hora,
    #    20 por minuto" era, portanto, UM BALDE ÚNICO somando o mundo inteiro
    #    -- não protegia contra força bruta (o atacante divide o balde com
    #    todos) e, num aplicativo que faz polling, é auto-bloqueio esperando
    #    a hora.
    # 2. O `audit_log` gravava esse mesmo IP de gateway em todo evento de
    #    autenticação: registro forense formalmente correto e materialmente
    #    inútil.
    #
    # ATRÁS DE VARIÁVEL, NUNCA INCONDICIONAL: confiar em `X-Forwarded-For` sem
    # um proxy à frente é PIOR que não confiar. Sem proxy, qualquer cliente
    # forja o cabeçalho, vira um IP novo a cada requisição e escapa do
    # limitador por completo -- e ainda envenena o log de auditoria com o
    # endereço que quiser. Mesma convenção do MegaSena
    # (`MEGA_SENA_TRUST_PROXY_HEADERS`) e do CRV.
    #
    # SOZINHO ISTO NÃO BASTA EM PRODUÇÃO. O waitress apaga os cabeçalhos
    # `X-Forwarded-*` antes de montar o environ, e o `ProxyFix` recebe um
    # environ já limpo -- ver o bloco longo em `_servir`, que configura o
    # waitress para confiar no nginx. As duas camadas existem porque cobrem
    # servidores diferentes: esta aqui é a que vale quando `CONFORTO_DEBUG`
    # liga o `app.run()` do Werkzeug, que não filtra cabeçalho nenhum.
    if _ler_bool_env("CONFORTO_TRUST_PROXY_HEADERS", False):
        app.wsgi_app = ProxyFix(  # type: ignore[method-assign]
            app.wsgi_app, x_for=1, x_proto=1, x_host=1
        )

    # O campo do formulário/header continua `_csrf_token` (não o
    # `csrf_token` padrão do Flask-WTF) para não precisar tocar templates
    # nem `api.js` -- e sem prazo próprio: o token vive e morre com a
    # sessão de 12h, como já era antes desta migração (o padrão do
    # Flask-WTF é 1h, o que introduziria falha de CSRF sem o login expirar).
    app.config["WTF_CSRF_FIELD_NAME"] = "_csrf_token"
    app.config["WTF_CSRF_TIME_LIMIT"] = None
    iniciar_csrf(app)

    def _conferir_banco() -> None:
        """Sonda de persistência do ICT, com o erro registrado antes de subir.

        O coletor é supervisionado por seu próprio health check no Compose.
        Acoplá-lo a esta sonda faria o Docker reiniciar o ICT durante uma
        indisponibilidade transitória do coletor, inclusive quando o ICT ainda
        consegue oferecer consultas e autenticação normalmente.

        O `raise` no fim não é redundante: `registrar_health` é quem traduz a
        falha em 503, e engolir a exceção aqui faria a sonda responder "ok"
        com o banco fora.
        """
        try:
            with db._conexao(escrita=False) as conn:
                conn.execute("SELECT 1").fetchone()
        except Exception as erro:
            app.logger.error("Health check DB falhou: %s", erro)
            raise

    registrar_health(
        app,
        servico="ict",
        verificar=_conferir_banco,
        endpoint="health_ict",
        limiter=limiter,
    )

    from . import dados_entrada_db
    from .dados_entrada_rotas import dados_entrada_bp, dados_entrada_leitura_bp
    from .ict.administracao import administracao_bp
    from .ict.operacao import operacao_bp
    from .ict.rotas import ict_bp
    from .rotas_comuns import comum_bp

    dados_entrada_db.iniciar_banco()
    app.register_blueprint(comum_bp)
    app.register_blueprint(auth.auth_bp)
    app.register_blueprint(auth.usuarios_bp)
    app.register_blueprint(dados_entrada_leitura_bp)
    app.register_blueprint(dados_entrada_bp)
    app.register_blueprint(ict_bp)
    app.register_blueprint(administracao_bp)
    app.register_blueprint(operacao_bp)
    # Estas três consultas são o polling autenticado e previsível da
    # Dashboard. O limite dedicado preserva a proteção global mais estrita
    # para as demais rotas, sem interromper a atualização legítima a cada
    # três segundos.
    #
    # `RouteLimit.__call__` devolve uma função *nova*, embrulhada -- o
    # enforcement de um limite decorado por rota roda DENTRO desse
    # embrulho (chama `_check_request_limit` quando a view é de fato
    # chamada), não no `before_request` genérico. Descartar o retorno em
    # vez de reatribuir a `view_functions` deixa o limite decorado e nunca
    # aplicado -- a mesma regressão real já encontrada e corrigida no
    # MegaSena e no ControleRendaVariavel. Achado aqui de novo: as três
    # rotas abaixo estavam sujeitas ao default global (20/min) em vez do
    # limite dedicado (60/min) -- em polling a cada 3s (20 req/min), isso
    # provavelmente já gerava 429 esporádico em produção.
    for endpoint in (
        "comum.historicos_recentes_zonas",
        "comum.status_operacao",
        "comum.eventos_operacao",
    ):
        app.view_functions[endpoint] = limiter.limit(
            "60 per minute; 5000 per hour", override_defaults=True
        )(app.view_functions[endpoint])

    auth.registrar_carregamento_usuario(app)
    requer_login(
        app,
        endpoints_publicos=auth.ENDPOINTS_ISENTOS_DE_LOGIN,
        endpoint_login="auth.login",
        esta_autenticado=lambda: g.usuario is not None,
        # Convenção deste app para toda resposta de erro em JSON (ver
        # `_negar_acesso`/`tratar_erro_inesperado`) -- os outros dois apps
        # Flask usam "error"/"erro" cada um com sua própria convenção;
        # `sharedauth.access` aceita as duas por parâmetro.
        chave_erro_api="erro",
    )
    auth.registrar_controle_de_area(app)

    # O rate-limit de 5/min no login nunca chegou a funcionar: usava um
    # `Limiter` órfão (`auth.obter_limiter()`), criado sem `app=` e sem
    # `init_app()` -- seu hook de enforcement nunca era registrado neste
    # app, então na prática só o default global (20/min) protegia o login.
    # Corrigido reaproveitando o limiter de verdade da aplicação, com o
    # mesmo limite padronizado nos três apps Flask (10/min).
    app.view_functions["auth.login"] = limiter.limit(LIMITE_LOGIN_PADRAO)(
        app.view_functions["auth.login"]
    )

    return app


def criar_app_coletor(config: AppConfig | None = None) -> Flask:
    """Cria o serviço privado que possui o cliente Modbus e a malha."""

    config = config or AppConfig.from_env("coletor")
    app = _criar_app_base("coletor", config)
    limiter: Limiter = app.extensions["conforto_rate_limiter"]

    # Importação deliberadamente exclusiva desta fábrica.
    from .coletor.rotas import coletor_bp

    app.register_blueprint(coletor_bp)

    # `limiter.exempt` devolve uma função *nova*, embrulhada. A chamada
    # anterior (`limiter.exempt(health)`) descartava o retorno, e o blueprint
    # seguia registrado com a função original — a isenção estava decorada e
    # nunca aplicada, com a sonda do Docker (a cada 60s) consumindo o
    # orçamento do limite global de 20/min. Mesma causa-raiz do limite de
    # login do MegaSena e das rotas de polling do dashboard deste projeto;
    # este é o terceiro ponto, achado ao subir o coletor de verdade.
    app.view_functions["coletor.health"] = limiter.exempt(
        app.view_functions["coletor.health"]
    )
    return app


def _servir(app: Flask, config: AppConfig) -> None:
    _validar_debug(config)
    if config.debug:
        app.run(
            debug=True,
            host=config.host,
            port=config.port,
            threaded=config.threaded,
            use_reloader=False,
        )
        return

    from waitress import serve

    # O `ProxyFix` em `criar_app_ict` NÃO basta aqui, e a razão é o servidor.
    #
    # O waitress 3.x vem com `clear_untrusted_proxy_headers=True` e
    # `trusted_proxy=None`: ele APAGA os cabeçalhos `X-Forwarded-*` antes de
    # montar o environ. O `ProxyFix` então recebe um environ já limpo, não acha
    # nada para ler e deixa o `REMOTE_ADDR` como está -- o IP do gateway do
    # Docker. A proteção existia no código e não existia em produção.
    #
    # Os outros três projetos usam gunicorn, que não mexe nesses cabeçalhos, e
    # lá o `ProxyFix` sozinho resolve. Este é o único com waitress. Foi copiar
    # o padrão do irmão para um servidor diferente que produziu uma correção
    # que parecia certa e não fazia efeito nenhum.
    #
    # `trusted_proxy="*"` é seguro NESTE arranjo e só nele: a porta do
    # contêiner é publicada em `127.0.0.1` (ver `compose.yaml`), então de fora
    # do host só se chega por meio do nginx. Não é uma porta exposta à
    # internet aceitando `X-Forwarded-For` de qualquer um -- o que seria
    # exatamente o risco que a variável de ambiente existe para evitar.
    #
    # `trusted_proxy_count=1` porque há um único proxy na frente. Contar mais
    # do que existe deixaria o cliente injetar entradas à esquerda e escolher
    # qual IP é lido.
    opcoes_proxy: dict[str, object] = {}
    if _ler_bool_env("CONFORTO_TRUST_PROXY_HEADERS", False):
        opcoes_proxy = {
            "trusted_proxy": "*",
            "trusted_proxy_count": 1,
            "trusted_proxy_headers": {
                "x-forwarded-for",
                "x-forwarded-proto",
                "x-forwarded-host",
            },
        }

    serve(
        app,
        host=config.host,
        port=config.port,
        threads=8 if config.threaded else 1,
        **opcoes_proxy,  # type: ignore[arg-type]
    )


def executar_ict(app: Flask, config: AppConfig) -> None:
    """Executa somente a interface ICT."""

    _servir(app, config)


def executar_coletor(app: Flask, config: AppConfig) -> None:
    """Executa a API interna e a malha contínua do coletor."""

    from . import notificacoes
    from .coletor.estado import gerenciador_controle

    fila = notificacoes.fila_notificacoes
    fila.iniciar(app.logger)
    gerenciador_controle.iniciar(app.logger)
    try:
        _servir(app, config)
    finally:
        gerenciador_controle.parar()
        fila.parar()
