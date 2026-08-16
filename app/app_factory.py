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

import datetime
import json
import os
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, cast

from flask import Flask, jsonify, request
from flask.json.provider import DefaultJSONProvider
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.exceptions import HTTPException

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

# Conjunto defensivo comum aos quatro projetos do mantenedor. Manter igual em
# todos e o que permite auditar um e confiar nos demais.
#
# Constantes de modulo, e nao literais dentro do `after_request`, para que a
# suite minima consiga afirmar sobre a politica sem construir a aplicacao --
# que aqui conecta ao banco no factory.
#
# `Referrer-Policy` e `same-origin`, nao `no-referrer`: sob `no-referrer` o
# navegador serializa o cabecalho `Origin` como `null` tambem em POST de mesma
# origem (Fetch spec), e qualquer verificacao de CSRF que consulte `Origin`
# passa a recusar a requisicao com o token correto. `same-origin` nao vaza
# referrer para fora da origem, que e o que importa, e preserva o `Origin`.
CABECALHOS_SEGURANCA = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "same-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Cross-Origin-Opener-Policy": "same-origin",
    "X-Permitted-Cross-Domain-Policies": "none",
}

# Nenhum template deste projeto usa `style=` nem `<style>`, entao
# `style-src 'self'` fecha sem excecao: um XSS refletido nao consegue injetar
# estilo nem script.
CONTENT_SECURITY_POLICY = (
    "default-src 'self'; script-src 'self'; style-src 'self'; "
    "img-src 'self' data:; font-src 'self'; connect-src 'self'; "
    "base-uri 'self'; form-action 'self'; object-src 'none'; "
    "frame-ancestors 'none'"
)
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

    @app.after_request
    def _aplicar_cabecalhos_seguranca(resposta):
        for cabecalho, valor in CABECALHOS_SEGURANCA.items():
            resposta.headers.setdefault(cabecalho, valor)
        resposta.headers.setdefault("Content-Security-Policy", CONTENT_SECURITY_POLICY)
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

    app.secret_key = auth.obter_ou_criar_chave_secreta()
    app.config["SESSION_COOKIE_NAME"] = (
        os.environ.get("CONFORTO_SESSION_COOKIE_NAME", "conforto_session").strip()
        or "conforto_session"
    )
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_SECURE"] = _ler_bool_env("CONFORTO_COOKIE_SEGURO", False)
    # CSRF é sempre protegido por padrão (ver `auth._proteger_csrf`, que
    # usa `app.config.get("CSRF_PROTECTION_ENABLED", True)`). Não depende
    # do backend de persistência: testes que precisam dispensar CSRF usam
    # `app.testing`, e o único teste que exercita a proteção em si
    # (`TestProtecaoCsrf`) desliga `app.testing` explicitamente.
    app.permanent_session_lifetime = datetime.timedelta(hours=12)

    @app.get("/health")
    @limiter.exempt
    def health_ict():
        """Health check do ICT que valida sua dependência de persistência.

        O coletor é supervisionado por seu próprio health check no Compose.
        Acoplá-lo a esta sonda faria o Docker reiniciar o ICT durante uma
        indisponibilidade transitória do coletor, inclusive quando o ICT ainda
        consegue oferecer consultas e autenticação normalmente.
        """
        import logging

        logger = logging.getLogger(__name__)

        status = {"servico": "ict", "status": "ok"}
        status_code = 200

        # Verificar banco de dados
        try:
            with db._conexao(escrita=False) as conn:
                conn.execute("SELECT 1").fetchone()
            status["db"] = "up"
        except Exception as e:
            status["db"] = "down"
            status["status"] = "degraded"
            status_code = 503
            logger.error("Health check DB falhou: %s", str(e))

        return jsonify(status), status_code

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
    for endpoint in (
        "comum.historicos_recentes_zonas",
        "comum.status_operacao",
        "comum.eventos_operacao",
    ):
        limiter.limit("60 per minute; 5000 per hour", override_defaults=True)(
            app.view_functions[endpoint]
        )
    auth.registrar_autenticacao(app)
    return app


def criar_app_coletor(config: AppConfig | None = None) -> Flask:
    """Cria o serviço privado que possui o cliente Modbus e a malha."""

    config = config or AppConfig.from_env("coletor")
    app = _criar_app_base("coletor", config)
    limiter: Limiter = app.extensions["conforto_rate_limiter"]

    # Importação deliberadamente exclusiva desta fábrica.
    from .coletor.rotas import coletor_bp, health

    limiter.exempt(health)
    app.register_blueprint(coletor_bp)
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

    serve(
        app,
        host=config.host,
        port=config.port,
        threads=8 if config.threaded else 1,
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
