# -*- coding: utf-8 -*-
"""
app.py
======
Sistema de Controle dos Índices de Conforto Térmico - aplicação Flask.

Baseado na dissertação de mestrado "Programa Computacional para o Cálculo de
Índices de Conforto Térmico na Produção Industrial de Animais para Carne e
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

# Estado do equipamento remoto (ventilador/nebulizador). A dissertação
# descreve um único posto de controle (estação de produção), por isso um
# único objeto "global" em memória é suficiente aqui - assim como o programa
# original era uma aplicação desktop de um único usuário.
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
    """Rede de segurança: qualquer exceção não tratada em uma rota /api/*
    ainda assim retorna JSON (nunca a página HTML padrão de erro do Flask).
    Isso evita que o front-end, que sempre espera JSON de /api/*, quebre ao
    tentar interpretar uma página de erro como se fosse dado — o que antes
    aparecia disfarçado de "falha de comunicação com o servidor"."""
    if isinstance(erro, HTTPException):
        if request.path.startswith("/api/"):
            return jsonify({"erro": erro.description}), erro.code or 500
        return erro

    app.logger.exception("Erro não tratado em %s", request.path)
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
    """Simula a leitura de um sensor remoto (Área 02 - opção 'Coletar
    Dados' da dissertação, seção 3.4.3). Gera valores plausíveis dentro da
    faixa validada no Capítulo IV (0-45°C / 0,01-5,00 m/s)."""
    especie = request.args.get("especie", "frangos")
    indice = request.args.get("indice", "")
    if not ti.indice_disponivel(especie, indice):
        return jsonify({"erro": "Índice inválido para a espécie selecionada."}), 400

    leitura = sensor_simulado_service.gerar(
        especie,
        indice,
        resfriamento_ativo=_resfriador.estado()["ativo"],
        ao_atingir_conforto=_resfriador.desativar,
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
    """Rota utilitária de diagnóstico: confirma se o banco está acessível e
    quantos registros já foram gravados ao todo (útil para conferir se as
    leituras estão mesmo sendo persistidas)."""
    try:
        total = db.contar_leituras()
        return jsonify(
            {"banco_ok": True, "total_leituras_gravadas": total, "arquivo_banco": db.DB_PATH}
        )
    except Exception as erro:
        return jsonify({"banco_ok": False, "erro": str(erro)}), 500


@app.route("/api/reset", methods=["POST"])
def reset():
    dados = request.get_json(force=True, silent=True) or {}
    db.limpar_historico(dados.get("especie"), dados.get("indice"))
    historico_grafico_service.limpar(dados.get("especie"), dados.get("indice"))
    sensor_simulado_service.limpar(dados.get("especie"), dados.get("indice"))
    _resfriador.desativar()
    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(debug=True)
