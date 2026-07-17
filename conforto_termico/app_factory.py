# -*- coding: utf-8 -*-
"""
app_factory.py
===============
Monta o app Flask a partir das pecas compartilhadas (blueprints +
configuracao), parametrizado por `papel_app`:

- `papel_app=None`         -> tudo num processo so (Fase 0 -- ver web.py)
- `papel_app="coletor"`    -> so as rotas que falam Modbus, calculam o
  indice e gravam no banco (ver `coletor/rotas.py`)
- `papel_app="dashboard"`  -> so as rotas de leitura/analise, sem Modbus
  (ver `dashboard/rotas.py`)

`rotas_comuns.py` (pagina inicial, lista de zonas, historico de leituras,
diagnostico) e registrado nos tres casos -- sao rotas somente leitura,
uteis nos dois papeis, e por isso vivem num Blueprint proprio em vez de
duplicadas: registrar a MESMA rota duas vezes no mesmo app (papel_app=None,
quando os dois blueprints coexistem) quebraria o Flask.

Os modulos `coletor.rotas` e `dashboard.rotas` so sao IMPORTADOS quando o
papel correspondente e realmente usado -- import, nao so registro. Isso
importa: `coletor.estado` importa `modbus_client`/`ZonaService`/etc.; um
processo criado com `papel_app="dashboard"` nunca deve puxar esse modulo
para dentro do seu espaco de processo. Um app de dashboard genuinamente
NAO CONSEGUE falar Modbus, nem por engano -- nao so "a rota nao existe".

NOTA DE SEGURANCA: o modo debug do Flask/Werkzeug expoe um console
interativo capaz de executar codigo arbitrario a quem conseguir alcancar a
pagina de erro. Isso e aceitavel apenas em desenvolvimento local, na
maquina do proprio desenvolvedor. Por isso `AppConfig.from_env()` abaixo
comeca DESLIGADO por padrao (`CONFORTO_DEBUG=0`) e so liga se o
desenvolvedor pedir explicitamente. O host tambem e mantido em
`127.0.0.1` por padrao (nao ouve a rede local nem a internet), tambem
configuravel via variavel de ambiente para quem realmente precisa expor o
servico propositalmente.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from flask import Flask, jsonify, request
from flask.json.provider import DefaultJSONProvider
from werkzeug.exceptions import HTTPException

from . import database as db

# Mensagem generica devolvida ao cliente para qualquer excecao nao tratada.
# O detalhe real (stack trace, tipo da excecao, mensagem interna) so vai
# para o log do servidor via `app.logger.exception` -- nunca para a
# resposta HTTP. Vazar `str(erro)` para o cliente e um vazamento de
# informacao classico (pode incluir caminhos de arquivo, nomes de tabelas,
# trechos de query, etc.) e nao ajuda um usuario final a fazer nada.
MENSAGEM_ERRO_INTERNO = "Erro interno inesperado. Consulte o log do servidor para detalhes."

# Os tres papeis validos de app (ver docstring do modulo). `None` so existe
# para a composicao "tudo num processo so" da Fase 0 (`web.py`).
PAPEIS_APP = (None, "coletor", "dashboard")
CONFIG_SERVIDOR_PATH = Path(__file__).resolve().parents[1] / "config" / "servidor.json"


def _ler_config_servidor(papel_app: str | None) -> dict:
    """Le configuracoes locais versionadas para cada papel do servidor.

    Variaveis de ambiente continuam tendo precedencia. Se o arquivo estiver
    ausente ou malformado, os padroes seguros em codigo continuam valendo.
    """
    try:
        with CONFIG_SERVIDOR_PATH.open("r", encoding="utf-8") as arquivo:
            bruto = json.load(arquivo)
    except (OSError, json.JSONDecodeError):
        return {}

    if not isinstance(bruto, dict):
        return {}

    config = {}
    for chave in ("padrao", papel_app):
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
    valor = os.environ.get(nome)
    return _coagir_bool(valor, padrao)


def _ler_int_env(nome: str, padrao: int) -> int:
    valor = os.environ.get(nome)
    return _coagir_int(valor, padrao)


@dataclass(frozen=True)
class AppConfig:
    """Configuracao de execucao do servidor, centralizada num unico lugar
    em vez de `os.environ.get(...)` espalhado pelo codigo. Todos os campos
    tem um padrao seguro para uso local; nenhum exige variavel de ambiente
    configurada para funcionar."""

    debug: bool
    host: str
    port: int
    threaded: bool
    max_content_length: int

    @classmethod
    def from_env(cls, papel_app: str | None = None) -> "AppConfig":
        if papel_app not in PAPEIS_APP:
            raise ValueError(f"papel_app invalido: {papel_app!r} (esperado um de {PAPEIS_APP})")

        config_arquivo = _ler_config_servidor(papel_app)
        return cls(
            debug=_ler_bool_env("CONFORTO_DEBUG", _coagir_bool(config_arquivo.get("debug"), False)),
            host=os.environ.get("CONFORTO_HOST", str(config_arquivo.get("host") or "127.0.0.1")),
            port=_ler_int_env("CONFORTO_PORT", _coagir_int(config_arquivo.get("port"), 5000)),
            threaded=_ler_bool_env(
                "CONFORTO_THREADED", _coagir_bool(config_arquivo.get("threaded"), True)
            ),
            # 1 MiB e generoso para o payload JSON desta API (entradas de
            # sensor e configuracoes sao poucas dezenas de campos numericos)
            # e evita que uma requisicao com corpo gigante consuma memoria
            # do processo desnecessariamente.
            max_content_length=_ler_int_env(
                "CONFORTO_MAX_CONTENT_LENGTH",
                _coagir_int(config_arquivo.get("max_content_length"), 1_000_000),
            ),
        )


class ProvedorJSON(DefaultJSONProvider):
    """Provedor JSON do Flask com suporte a `MappingProxyType`.

    `thermal_indices.py` congela seus dicionarios de configuracao
    compartilhada (especies, indices, limites, etc.) com
    `types.MappingProxyType` para impedir mutacao acidental em tempo de
    execucao (ver `_congelar` naquele modulo). O serializador JSON padrao
    do Python nao sabe lidar com esse tipo -- sem este provedor, tanto
    `jsonify(...)` quanto o filtro `| tojson` do Jinja levantariam
    `TypeError` ao tentar renderizar a pagina inicial."""

    @staticmethod
    def default(o):
        if isinstance(o, MappingProxyType):
            return dict(o)
        return DefaultJSONProvider.default(o)


def criar_app(papel_app: str | None = None, config: AppConfig | None = None) -> Flask:
    """Monta e devolve um app Flask pronto para uso. Ver docstring do
    modulo para o significado de `papel_app`."""
    if papel_app not in PAPEIS_APP:
        raise ValueError(f"papel_app invalido: {papel_app!r} (esperado um de {PAPEIS_APP})")

    config = config or AppConfig.from_env(papel_app)

    app = Flask(__name__)
    app.json = ProvedorJSON(app)
    app.config["MAX_CONTENT_LENGTH"] = config.max_content_length
    # Guardados em `app.config` (nao num global do modulo) porque, na Fase
    # 1, mais de um app (coletor e dashboard) pode existir no mesmo
    # interpretador Python durante os testes -- cada um precisa do seu
    # proprio papel/flag de debug, sem vazar para o outro.
    app.config["CONFORTO_PAPEL_APP"] = papel_app
    app.config["CONFORTO_DEBUG"] = config.debug

    db.iniciar_banco()

    from .rotas_comuns import comum_bp

    app.register_blueprint(comum_bp)

    if papel_app in (None, "coletor"):
        from .coletor.rotas import coletor_bp

        app.register_blueprint(coletor_bp)

    if papel_app in (None, "dashboard"):
        from .dashboard.rotas import dashboard_bp

        app.register_blueprint(dashboard_bp)

    @app.after_request
    def _aplicar_cabecalhos_seguranca(resposta):
        """Cabecalhos de defesa em profundidade. Nenhum deles muda o
        comportamento funcional da aplicacao para um cliente legitimo;
        todos reduzem a superficie de ataque para um cliente malicioso:

        - X-Content-Type-Options: navegador nao deve "adivinhar" um tipo
          de conteudo diferente do declarado (mitiga certos ataques de MIME
          sniffing).
        - X-Frame-Options: impede que a pagina seja carregada dentro de um
          <iframe> de outro site (mitiga clickjacking).
        - Referrer-Policy: nao vaza a URL completa desta aplicacao local
          para terceiros ao seguir um link para fora dela.
        - Cache-Control: respostas de /api/* carregam estado (leituras,
          configuracoes) que muda a cada chamada; nunca devem ser
          cacheadas pelo navegador ou por um proxy intermediario. Deixamos
          os arquivos estaticos (JS/CSS) de fora dessa regra de proposito,
          para nao perder o cache do navegador neles.
        """
        resposta.headers.setdefault("X-Content-Type-Options", "nosniff")
        resposta.headers.setdefault("X-Frame-Options", "DENY")
        resposta.headers.setdefault("Referrer-Policy", "no-referrer")
        if request.path.startswith("/api/"):
            resposta.headers["Cache-Control"] = "no-store"
        return resposta

    @app.errorhandler(Exception)
    def tratar_erro_inesperado(erro):
        """Rede de seguranca: qualquer excecao nao tratada em uma rota
        /api/* ainda assim retorna JSON (nunca a pagina HTML padrao de
        erro do Flask). Isso evita que o front-end, que sempre espera JSON
        de /api/*, quebre ao tentar interpretar uma pagina de erro como se
        fosse dado — o que antes aparecia disfarcado de "falha de
        comunicacao com o servidor".

        O detalhe da excecao e sempre logado no servidor via
        `app.logger.exception`; a resposta ao cliente usa a mensagem
        generica `MENSAGEM_ERRO_INTERNO` (ver nota no topo do modulo)."""
        if isinstance(erro, HTTPException):
            if request.path.startswith("/api/"):
                return jsonify({"erro": erro.description}), erro.code or 500
            return erro

        app.logger.exception("Erro nao tratado em %s", request.path)
        if request.path.startswith("/api/"):
            return jsonify({"erro": MENSAGEM_ERRO_INTERNO}), 500
        raise erro

    return app


def executar_servidor(app: Flask, config: AppConfig) -> None:
    """Executa `app` localmente, sem o reloader do Werkzeug.

    O reloader cria um processo pai e um filho. Em execucoes locais pelo
    PyCharm, terminal ou automacao, isso pode deixar processos Flask
    aparentes depois que a janela principal foi encerrada."""
    gerenciador = None
    if app.config.get("CONFORTO_PAPEL_APP") in (None, "coletor"):
        # Importacao deliberadamente tardia: o processo dashboard continua
        # sem carregar qualquer codigo Modbus ou de acionamento.
        from .coletor.estado import gerenciador_controle

        gerenciador = gerenciador_controle
        gerenciador.iniciar(app.logger)
    try:
        app.run(
            debug=config.debug,
            host=config.host,
            port=config.port,
            threaded=config.threaded,
            use_reloader=False,
        )
    finally:
        if gerenciador:
            gerenciador.parar()
