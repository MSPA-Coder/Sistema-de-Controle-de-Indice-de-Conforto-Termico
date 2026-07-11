# -*- coding: utf-8 -*-
"""
web.py
======
Sistema de Controle dos Indices de Conforto Termico - aplicacao Flask.

Baseado na dissertacao de mestrado "Programa Computacional para o Calculo de
Indices de Conforto Termico na Producao Industrial de Animais para Carne e
Leite" (Mariano Sergio Pacheco de Angelo, UNIP, 2013), reimplementado em
Python/Flask a pedido do autor.

Para rodar:
    pip install -r requirements.txt
    python app.py
Depois abra http://127.0.0.1:5000 no navegador.

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

import os
from dataclasses import dataclass
from types import MappingProxyType

from flask import Flask, jsonify, render_template, request
from flask.json.provider import DefaultJSONProvider
from werkzeug.exceptions import HTTPException

from . import database as db
from . import thermal_indices as ti
from .models import Resfriamento
from .services import CalculoIctService, HistoricoGraficoService, SensorSimuladoService

# Mensagem generica devolvida ao cliente para qualquer excecao nao tratada.
# O detalhe real (stack trace, tipo da excecao, mensagem interna) so vai
# para o log do servidor via `app.logger.exception` -- nunca para a
# resposta HTTP. Vazar `str(erro)` para o cliente e um vazamento de
# informacao classico (pode incluir caminhos de arquivo, nomes de tabelas,
# trechos de query, etc.) e nao ajuda um usuario final a fazer nada.
MENSAGEM_ERRO_INTERNO = "Erro interno inesperado. Consulte o log do servidor para detalhes."


def _ler_bool_env(nome: str, padrao: bool) -> bool:
    valor = os.environ.get(nome)
    if valor is None:
        return padrao
    return valor.strip().lower() in ("1", "true", "sim", "on")


def _ler_int_env(nome: str, padrao: int) -> int:
    valor = os.environ.get(nome)
    if valor is None:
        return padrao
    try:
        return int(valor)
    except ValueError:
        return padrao


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
    def from_env(cls) -> "AppConfig":
        return cls(
            debug=_ler_bool_env("CONFORTO_DEBUG", False),
            host=os.environ.get("CONFORTO_HOST", "127.0.0.1"),
            port=_ler_int_env("CONFORTO_PORT", 5000),
            threaded=_ler_bool_env("CONFORTO_THREADED", True),
            # 1 MiB e generoso para o payload JSON desta API (entradas de
            # sensor e configuracoes sao poucas dezenas de campos numericos)
            # e evita que uma requisicao com corpo gigante consuma memoria
            # do processo desnecessariamente.
            max_content_length=_ler_int_env("CONFORTO_MAX_CONTENT_LENGTH", 1_000_000),
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


_config = AppConfig.from_env()

app = Flask(__name__)
app.json = ProvedorJSON(app)
app.config["MAX_CONTENT_LENGTH"] = _config.max_content_length
db.iniciar_banco()

# Estado do equipamento remoto (ventilador/nebulizador). A dissertacao
# descreve um unico posto de controle (estacao de producao), por isso um
# unico objeto "global" em memoria e suficiente aqui - assim como o programa
# original era uma aplicacao desktop de um unico usuario.
_resfriador = Resfriamento()
historico_grafico_service = HistoricoGraficoService(db.obter_historico)
sensor_simulado_service = SensorSimuladoService()
calculo_ict_service = CalculoIctService(
    _resfriador,
    historico_grafico_service,
    sensor_simulado_service,
    db.salvar_leitura,
    db.obter_historico,
)


@app.after_request
def _aplicar_cabecalhos_seguranca(resposta):
    """Cabecalhos de defesa em profundidade. Nenhum deles muda o
    comportamento funcional da aplicacao para um cliente legitimo; todos
    reduzem a superficie de ataque para um cliente malicioso:

    - X-Content-Type-Options: navegador nao deve "adivinhar" um tipo de
      conteudo diferente do declarado (mitiga certos ataques de MIME
      sniffing).
    - X-Frame-Options: impede que a pagina seja carregada dentro de um
      <iframe> de outro site (mitiga clickjacking).
    - Referrer-Policy: nao vaza a URL completa desta aplicacao local para
      terceiros ao seguir um link para fora dela.
    - Cache-Control: respostas de /api/* carregam estado (leituras,
      configuracoes) que muda a cada chamada; nunca devem ser cacheadas
      pelo navegador ou por um proxy intermediario. Deixamos os arquivos
      estaticos (JS/CSS) de fora dessa regra de proposito, para nao perder
      o cache do navegador neles.
    """
    resposta.headers.setdefault("X-Content-Type-Options", "nosniff")
    resposta.headers.setdefault("X-Frame-Options", "DENY")
    resposta.headers.setdefault("Referrer-Policy", "no-referrer")
    if request.path.startswith("/api/"):
        resposta.headers["Cache-Control"] = "no-store"
    return resposta


@app.errorhandler(Exception)
def tratar_erro_inesperado(erro):
    """Rede de seguranca: qualquer excecao nao tratada em uma rota /api/*
    ainda assim retorna JSON (nunca a pagina HTML padrao de erro do Flask).
    Isso evita que o front-end, que sempre espera JSON de /api/*, quebre ao
    tentar interpretar uma pagina de erro como se fosse dado — o que antes
    aparecia disfarcado de "falha de comunicacao com o servidor".

    O detalhe da excecao e sempre logado no servidor via
    `app.logger.exception`; a resposta ao cliente usa a mensagem generica
    `MENSAGEM_ERRO_INTERNO` (ver nota no topo do modulo)."""
    if isinstance(erro, HTTPException):
        if request.path.startswith("/api/"):
            return jsonify({"erro": erro.description}), erro.code or 500
        return erro

    app.logger.exception("Erro nao tratado em %s", request.path)
    if request.path.startswith("/api/"):
        return jsonify({"erro": MENSAGEM_ERRO_INTERNO}), 500
    raise erro


def _erro_especie_invalida(especie: str) -> tuple | None:
    """Retorna uma tupla (payload, status) pronta para `jsonify` se a
    especie for invalida, ou None se estiver tudo certo. Evita que uma
    especie desconhecida caia silenciosamente numa lista vazia (o que
    parece "sem historico ainda" quando na verdade e um parametro digitado
    errado) -- prefere-se um 400 explicito e imediato."""
    if especie not in ti.ESPECIES_VALIDAS:
        return {"erro": f"Espécie inválida: '{especie}'."}, 400
    return None


def _erro_indice_invalido(especie: str, indice: str) -> tuple | None:
    if not ti.indice_disponivel(especie, indice):
        return {"erro": f"Índice inválido para a espécie '{especie}'."}, 400
    return None


@app.route("/")
def index():
    return render_template(
        "index.html",
        indices_por_especie=ti.INDICES_POR_ESPECIE,
        nome_especie=ti.NOME_ESPECIE,
        nome_indice=ti.NOME_INDICE,
        campos_por_indice=ti.CAMPOS_POR_INDICE,
        campo_metadados=ti.CAMPO_METADADOS,
        limites=ti.LIMITES,
    )


@app.route("/favicon.ico")
def favicon():
    return "", 204


@app.route("/api/calcular", methods=["POST"])
def calcular():
    dados = request.get_json(force=True, silent=True) or {}
    especie = dados.get("especie", "")
    indice = dados.get("indice", "")
    entradas = dados.get("entradas", {}) or {}
    config = dados.get("config", {}) or {}

    try:
        resposta = calculo_ict_service.calcular(
            especie, indice, entradas, config, app.logger
        )
    except ti.EntradaInvalidaError as erro:
        return jsonify({"erro": str(erro)}), 400
    return jsonify(resposta)


@app.route("/api/sensor")
def sensor_simulado():
    """Simula a leitura de um sensor remoto (Area 02 - opcao 'Coletar
    Dados' da dissertacao, secao 3.4.3). Gera valores plausiveis dentro da
    faixa validada no Capitulo IV (0-45°C / 0,01-5,00 m/s)."""
    especie = request.args.get("especie", "frangos")
    indice = request.args.get("indice", "")
    erro = _erro_indice_invalido(especie, indice)
    if erro:
        return jsonify(erro[0]), erro[1]

    leitura = sensor_simulado_service.gerar(
        especie,
        indice,
        resfriamento_ativo=_resfriador.estado()["ativo"],
    )
    return jsonify(leitura)


@app.route("/api/historico")
def historico():
    especie = request.args.get("especie", "")
    indice = request.args.get("indice", "")
    erro = _erro_indice_invalido(especie, indice)
    if erro:
        return jsonify(erro[0]), erro[1]
    return jsonify(db.obter_historico(especie, indice, limite=20))


@app.route("/api/historico-todos")
def historico_todos():
    especie = request.args.get("especie", "")
    erro = _erro_especie_invalida(especie)
    if erro:
        return jsonify(erro[0]), erro[1]
    return jsonify(
        {
            indice: db.obter_historico(especie, indice, limite=20)
            for indice in ti.INDICES_POR_ESPECIE.get(especie, ())
        }
    )


@app.route("/api/historico-grafico")
def historico_grafico():
    especie = request.args.get("especie", "")
    indice = request.args.get("indice", "")
    erro = _erro_indice_invalido(especie, indice)
    if erro:
        return jsonify(erro[0]), erro[1]
    return jsonify(historico_grafico_service.obter(especie, indice))


@app.route("/api/historico-grafico-todos")
def historico_grafico_todos():
    especie = request.args.get("especie", "")
    erro = _erro_especie_invalida(especie)
    if erro:
        return jsonify(erro[0]), erro[1]
    return jsonify(
        {
            indice: historico_grafico_service.obter(especie, indice)
            for indice in ti.INDICES_POR_ESPECIE.get(especie, ())
        }
    )


@app.route("/api/diagnostico")
def diagnostico():
    """Rota utilitaria de diagnostico: confirma se o banco esta acessivel e
    quantos registros ja foram gravados ao todo (util para conferir se as
    leituras estao mesmo sendo persistidas).

    O caminho absoluto do arquivo do banco so e incluido com o servidor em
    modo debug: fora de depuracao local, expor a estrutura de diretorios do
    servidor a quem acessar essa rota e um vazamento de informacao
    desnecessario para o proposito da rota (confirmar que o banco
    responde)."""
    try:
        total = db.contar_leituras()
        payload = {"banco_ok": True, "total_leituras_gravadas": total}
        if _config.debug:
            payload["arquivo_banco"] = db.DB_PATH
        return jsonify(payload)
    except Exception:
        app.logger.exception("Falha ao consultar diagnostico do banco")
        return jsonify({"banco_ok": False, "erro": MENSAGEM_ERRO_INTERNO}), 500


@app.route("/api/configuracoes", methods=["GET"])
def obter_configuracoes():
    return jsonify(db.obter_configuracoes())


@app.route("/api/configuracoes", methods=["POST"])
def salvar_configuracoes():
    dados = request.get_json(force=True, silent=True) or {}
    return jsonify(db.salvar_configuracoes(dados))


@app.route("/api/reset", methods=["POST"])
def reset():
    dados = request.get_json(force=True, silent=True) or {}
    especie = dados.get("especie")
    indice = dados.get("indice")
    if especie is not None and especie not in ti.ESPECIES_VALIDAS:
        return jsonify({"erro": f"Espécie inválida: '{especie}'."}), 400
    if indice is not None and indice not in ti.NOME_INDICE:
        return jsonify({"erro": f"Índice inválido: '{indice}'."}), 400
    db.limpar_historico(especie, indice)
    historico_grafico_service.limpar(especie, indice)
    sensor_simulado_service.limpar(especie, indice)
    _resfriador.desativar()
    return jsonify({"ok": True})


def executar_servidor_local(config: AppConfig | None = None) -> None:
    """Executa o servidor local sem o reloader do Werkzeug.

    O reloader cria um processo pai e um filho. Em execucoes locais pelo
    PyCharm, terminal ou automacao, isso pode deixar processos Flask aparentes
    depois que a janela principal foi encerrada.

    `debug`, `host`, `port` e `threaded` vem de `AppConfig` (por padrao,
    `AppConfig.from_env()` -- ver a nota de seguranca no topo do modulo
    sobre por que o debug comeca desligado). Aceitar `config` como
    parametro (em vez de ler `os.environ` diretamente aqui) torna essa
    funcao testavel de forma deterministica, sem depender de variaveis de
    ambiente do shell de quem roda os testes.
    """
    config = config or _config
    app.run(
        debug=config.debug,
        host=config.host,
        port=config.port,
        threaded=config.threaded,
        use_reloader=False,
    )


if __name__ == "__main__":
    executar_servidor_local()
