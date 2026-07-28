# -*- coding: utf-8 -*-
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

from flask import Flask, jsonify, request
from flask.json.provider import DefaultJSONProvider
from werkzeug.exceptions import HTTPException

from . import auth
from . import database as db
from . import db_backend
from . import env_config

# Útil para execução local. No Docker, as variáveis injetadas pelo Compose
# têm precedência e pertencem à implantação, não à interface ICT.
env_config.carregar()

MENSAGEM_ERRO_INTERNO = "Erro interno inesperado. Consulte o log do servidor para detalhes."
PROCESSOS_APP = ("ict", "coletor")
CONFIG_SERVIDOR_PATH = Path(__file__).resolve().parents[1] / "config" / "servidor.json"


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

    @classmethod
    def from_env(cls, processo: str = "ict") -> "AppConfig":
        if processo not in PROCESSOS_APP:
            raise ValueError(
                f"processo inválido: {processo!r} (esperado um de {PROCESSOS_APP})"
            )

        config_arquivo = _ler_config_servidor(processo)
        return cls(
            debug=_ler_bool_env(
                "CONFORTO_DEBUG", _coagir_bool(config_arquivo.get("debug"), False)
            ),
            host=os.environ.get(
                "CONFORTO_HOST", str(config_arquivo.get("host") or "127.0.0.1")
            ),
            port=_ler_int_env(
                "CONFORTO_PORT", _coagir_int(config_arquivo.get("port"), 5000)
            ),
            threaded=_ler_bool_env(
                "CONFORTO_THREADED",
                _coagir_bool(config_arquivo.get("threaded"), True),
            ),
            max_content_length=_ler_int_env(
                "CONFORTO_MAX_CONTENT_LENGTH",
                _coagir_int(config_arquivo.get("max_content_length"), 1_000_000),
            ),
        )


class ProvedorJSON(DefaultJSONProvider):
    """Serializador JSON com suporte às tabelas imutáveis do domínio."""

    @staticmethod
    def default(o):
        if isinstance(o, MappingProxyType):
            return dict(o)
        return DefaultJSONProvider.default(o)


def _criar_app_base(processo: str, config: AppConfig) -> Flask:
    app = Flask(__name__)
    app.json = ProvedorJSON(app)
    app.config["MAX_CONTENT_LENGTH"] = config.max_content_length
    app.config["CONFORTO_PROCESSO"] = processo
    app.config["CONFORTO_DEBUG"] = config.debug
    db.iniciar_banco()

    @app.after_request
    def _aplicar_cabecalhos_seguranca(resposta):
        resposta.headers.setdefault("X-Content-Type-Options", "nosniff")
        resposta.headers.setdefault("X-Frame-Options", "DENY")
        resposta.headers.setdefault("Referrer-Policy", "no-referrer")
        resposta.headers.setdefault(
            "Permissions-Policy", "camera=(), microphone=(), geolocation=()"
        )
        resposta.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
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

    app.secret_key = auth.obter_ou_criar_chave_secreta()
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_SECURE"] = _ler_bool_env(
        "CONFORTO_COOKIE_SEGURO", False
    )
    # A implantação PostgreSQL é o ambiente operacional e sempre protege
    # requisições mutáveis. O fallback SQLite existe apenas para a suíte
    # unitária isolada, que testa autorização sem precisar propagar CSRF
    # por centenas de chamadas de baixo nível.
    app.config["CSRF_PROTECTION_ENABLED"] = db_backend.postgres_ativo()
    app.permanent_session_lifetime = datetime.timedelta(hours=12)

    @app.get("/health")
    def health_ict():
        with db._conexao(escrita=False) as conn:
            conn.execute("SELECT 1").fetchone()
        return jsonify({"servico": "ict", "status": "ok"})

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
    auth.registrar_autenticacao(app)
    return app


def criar_app_coletor(config: AppConfig | None = None) -> Flask:
    """Cria o serviço privado que possui o cliente Modbus e a malha."""

    config = config or AppConfig.from_env("coletor")
    app = _criar_app_base("coletor", config)

    # Importação deliberadamente exclusiva desta fábrica.
    from .coletor.rotas import coletor_bp

    app.register_blueprint(coletor_bp)
    return app


def _servir(app: Flask, config: AppConfig) -> None:
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
