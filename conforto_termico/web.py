# -*- coding: utf-8 -*-
"""
app.py
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
"""

from __future__ import annotations

from flask import Flask, jsonify, render_template, request
from werkzeug.exceptions import HTTPException

from . import database as db
from . import thermal_indices as ti
from .models import Resfriamento
from .services import CalculoIctService, HistoricoGraficoService, SensorSimuladoService

app = Flask(__name__)
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


@app.errorhandler(Exception)
def tratar_erro_inesperado(erro):
    """Rede de seguranca: qualquer excecao nao tratada em uma rota /api/*
    ainda assim retorna JSON (nunca a pagina HTML padrao de erro do Flask).
    Isso evita que o front-end, que sempre espera JSON de /api/*, quebre ao
    tentar interpretar uma pagina de erro como se fosse dado — o que antes
    aparecia disfarcado de "falha de comunicacao com o servidor"."""
    if isinstance(erro, HTTPException):
        if request.path.startswith("/api/"):
            return jsonify({"erro": erro.description}), erro.code or 500
        return erro

    app.logger.exception("Erro nao tratado em %s", request.path)
    if request.path.startswith("/api/"):
        return jsonify({"erro": f"Erro interno inesperado: {erro}"}), 500
    raise erro


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
    if not ti.indice_disponivel(especie, indice):
        return jsonify({"erro": "Índice inválido para a espécie selecionada."}), 400

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
    return jsonify(db.obter_historico(especie, indice, limite=20))


@app.route("/api/historico-todos")
def historico_todos():
    especie = request.args.get("especie", "")
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
    return jsonify(historico_grafico_service.obter(especie, indice))


@app.route("/api/historico-grafico-todos")
def historico_grafico_todos():
    especie = request.args.get("especie", "")
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
    leituras estao mesmo sendo persistidas)."""
    try:
        total = db.contar_leituras()
        return jsonify(
            {"banco_ok": True, "total_leituras_gravadas": total, "arquivo_banco": db.DB_PATH}
        )
    except Exception as erro:
        return jsonify({"banco_ok": False, "erro": str(erro)}), 500


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
    db.limpar_historico(dados.get("especie"), dados.get("indice"))
    historico_grafico_service.limpar(dados.get("especie"), dados.get("indice"))
    sensor_simulado_service.limpar(dados.get("especie"), dados.get("indice"))
    _resfriador.desativar()
    return jsonify({"ok": True})


def executar_servidor_local() -> None:
    """Executa o servidor local sem o reloader do Werkzeug.

    O reloader cria um processo pai e um filho. Em execucoes locais pelo
    PyCharm, terminal ou automacao, isso pode deixar processos Flask aparentes
    depois que a janela principal foi encerrada.
    """
    app.run(debug=True, use_reloader=False)


if __name__ == "__main__":
    executar_servidor_local()
