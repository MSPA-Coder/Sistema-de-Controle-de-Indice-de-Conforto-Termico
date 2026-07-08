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

import datetime
import random
import threading

from flask import Flask, jsonify, render_template, request
from werkzeug.exceptions import HTTPException

import database as db
import thermal_indices as ti
from models import Email, Resfriamento, Temperatura

app = Flask(__name__)
db.iniciar_banco()

# Estado do equipamento remoto (ventilador/nebulizador). A dissertação
# descreve um único posto de controle (estação de produção), por isso um
# único objeto "global" em memória é suficiente aqui - assim como o programa
# original era uma aplicação desktop de um único usuário.
_resfriador = Resfriamento()
_historico_graficos = {}
_historico_graficos_lock = threading.Lock()
_estado_sensor = {}
_estado_sensor_lock = threading.Lock()
LIMITE_HISTORICO_GRAFICOS = 20
FATOR_RESFRIAMENTO = 0.95
FATOR_VENTILACAO = 1.05


def _copiar_leitura(leitura):
    copia = dict(leitura)
    copia["entradas"] = dict(leitura["entradas"])
    return copia


def _historico_visual(especie, indice):
    chave = (especie, indice)
    with _historico_graficos_lock:
        if chave in _historico_graficos:
            return [_copiar_leitura(leitura) for leitura in _historico_graficos[chave]]

    return db.obter_historico(especie, indice, limite=LIMITE_HISTORICO_GRAFICOS)


def _registrar_leitura_visual(especie, indice, valor, status, entradas):
    chave = (especie, indice)
    leitura = {
        "criado_em": datetime.datetime.now().isoformat(timespec="seconds"),
        "valor": valor,
        "status": status,
        "entradas": dict(entradas),
    }

    with _historico_graficos_lock:
        if chave not in _historico_graficos:
            _historico_graficos[chave] = db.obter_historico(
                especie, indice, limite=LIMITE_HISTORICO_GRAFICOS - 1
            )
        _historico_graficos[chave].append(leitura)
        _historico_graficos[chave] = _historico_graficos[chave][-LIMITE_HISTORICO_GRAFICOS:]
        return [_copiar_leitura(item) for item in _historico_graficos[chave]]


def _limpar_historico_visual(especie, indice):
    with _historico_graficos_lock:
        if especie and indice:
            _historico_graficos.pop((especie, indice), None)
        else:
            _historico_graficos.clear()


def _leitura_aleatoria(indice):
    if indice == "ITU":
        return {"tbs": round(random.uniform(18, 40), 1), "tbu": round(random.uniform(12, 30), 1)}
    if indice == "ITUV":
        return {
            "tbs": round(random.uniform(18, 40), 1),
            "tbu": round(random.uniform(12, 30), 1),
            "v": round(random.uniform(0.1, 5.0), 2),
        }
    if indice == "IGNU":
        return {"tgn": round(random.uniform(18, 45), 1), "tpo": round(random.uniform(5, 30), 1)}
    raise ti.EntradaInvalidaError("Índice inválido.")


def _registrar_estado_sensor(especie, indice, entradas, valor, status):
    with _estado_sensor_lock:
        _estado_sensor[(especie, indice)] = {
            "entradas": dict(entradas),
            "valor": valor,
            "status": status,
        }


def _limpar_estado_sensor(especie, indice):
    with _estado_sensor_lock:
        if especie and indice:
            _estado_sensor.pop((especie, indice), None)
        else:
            _estado_sensor.clear()


def _valor_ajustado(campo, valor):
    minimo, maximo = ti.RANGE_VALIDACAO[campo]
    if campo == "v":
        ajustado = valor * FATOR_VENTILACAO
    elif valor >= 0:
        ajustado = valor * FATOR_RESFRIAMENTO
    else:
        ajustado = valor / FATOR_RESFRIAMENTO
    return max(minimo, min(maximo, ajustado))


def _leitura_com_resfriamento(especie, indice):
    with _estado_sensor_lock:
        estado = _estado_sensor.get((especie, indice))

    if not estado or estado["status"] == "Conforto":
        if estado and estado["status"] == "Conforto":
            _resfriador.desativar()
        return None

    entradas = dict(estado["entradas"])
    campos_ajustados = ti.CAMPOS_POR_INDICE[indice]
    ajustada = {
        campo: round(_valor_ajustado(campo, entradas[campo]), 2 if campo == "v" else 1)
        for campo in campos_ajustados
    }
    valor, status = ti.calcular_e_classificar(especie, indice, ajustada)
    _registrar_estado_sensor(especie, indice, ajustada, valor, status)
    return ajustada


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

    # 1) Cálculo em si — se falhar, é erro do usuário (dados inválidos) e
    #    retorna 400 com mensagem clara; nada é gravado.
    try:
        temperatura = Temperatura(especie, indice)
        valor, status = temperatura.calcular_ict(entradas)
    except ti.EntradaInvalidaError as erro:
        return jsonify({"erro": str(erro)}), 400

    _registrar_estado_sensor(especie, indice, temperatura.entradas, valor, status)

    try:
        historico_grafico = _registrar_leitura_visual(especie, indice, valor, status, temperatura.entradas)
    except Exception:
        app.logger.exception("Falha ao atualizar histórico visual dos gráficos")
        historico_grafico = []

    # 2) A partir daqui o cálculo já está pronto. Cada efeito colateral abaixo
    #    (gravar no banco, acionar equipamentos, montar e-mail) é isolado em
    #    seu próprio try/except: uma falha em qualquer um deles não deve
    #    derrubar a resposta inteira nem esconder o valor já calculado.
    aviso = None
    leitura_gravada = False
    try:
        leitura_gravada = db.salvar_leitura(especie, indice, valor, status, temperatura.entradas)
    except Exception:
        app.logger.exception("Falha ao gravar leitura no banco de dados")
        aviso = "O valor foi calculado, mas não foi possível salvar no histórico (veja o log do Flask)."

    equipamento_info = _resfriador.estado()
    if config.get("habilitarEquipamentos"):
        try:
            intensidade = ti.INTENSIDADE_EQUIPAMENTO[status]
            if intensidade:
                _resfriador.ativar(intensidade)
            else:
                _resfriador.desativar()
            equipamento_info = _resfriador.estado()
        except Exception:
            app.logger.exception("Falha ao atualizar equipamentos remotos")

    email_info = None
    if config.get("enviarEmails"):
        try:
            conteudo = Email.montar_conteudo(indice, valor, status)
            destino = (config.get("emailDestino") or "produtor@fazenda.com.br").strip()
            email = Email(destino, conteudo)
            enviado_de_verdade = email.enviar()
            email_info = {
                "destino": destino,
                "conteudo": conteudo,
                "enviado_de_verdade": enviado_de_verdade,
            }
        except Exception:
            app.logger.exception("Falha ao montar/enviar e-mail")

    try:
        historico = db.obter_historico(especie, indice, limite=20)
    except Exception:
        app.logger.exception("Falha ao consultar histórico")
        historico = []

    resposta = {
        "valor": valor,
        "status": status,
        "cor": ti.CORES_STATUS[status],
        "mensagem": ti.MENSAGENS_STATUS[status],
        "leitura_gravada": leitura_gravada,
        "equipamento": equipamento_info,
        "email": email_info,
        "tocarSom": bool(config.get("habilitarSons")),
        "historico": historico,
        "historico_grafico": historico_grafico,
    }
    if aviso:
        resposta["aviso"] = aviso
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

    leitura = None
    if _resfriador.estado()["ativo"]:
        leitura = _leitura_com_resfriamento(especie, indice)
    if leitura is None:
        leitura = _leitura_aleatoria(indice)
    return jsonify(leitura)


@app.route("/api/historico")
def historico():
    especie = request.args.get("especie", "")
    indice = request.args.get("indice", "")
    return jsonify(db.obter_historico(especie, indice, limite=20))


@app.route("/api/historico-grafico")
def historico_grafico():
    especie = request.args.get("especie", "")
    indice = request.args.get("indice", "")
    return jsonify(_historico_visual(especie, indice))


@app.route("/api/diagnostico")
def diagnostico():
    """Rota utilitária de diagnóstico: confirma se o banco está acessível e
    quantos registros já foram gravados ao todo (útil para conferir se as
    leituras estão mesmo sendo persistidas)."""
    try:
        total = db.contar_leituras()
        return jsonify({"banco_ok": True, "total_leituras_gravadas": total, "arquivo_banco": db.DB_PATH})
    except Exception as erro:
        return jsonify({"banco_ok": False, "erro": str(erro)}), 500


@app.route("/api/reset", methods=["POST"])
def reset():
    dados = request.get_json(force=True, silent=True) or {}
    db.limpar_historico(dados.get("especie"), dados.get("indice"))
    _limpar_historico_visual(dados.get("especie"), dados.get("indice"))
    _limpar_estado_sensor(dados.get("especie"), dados.get("indice"))
    _resfriador.desativar()
    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(debug=True)
