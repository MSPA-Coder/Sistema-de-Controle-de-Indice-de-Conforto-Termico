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

import random

from flask import Flask, jsonify, render_template, request

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


@app.errorhandler(Exception)
def tratar_erro_inesperado(erro):
    """Rede de segurança: qualquer exceção não tratada em uma rota /api/*
    ainda assim retorna JSON (nunca a página HTML padrão de erro do Flask).
    Isso evita que o front-end, que sempre espera JSON de /api/*, quebre ao
    tentar interpretar uma página de erro como se fosse dado — o que antes
    aparecia disfarçado de "falha de comunicação com o servidor"."""
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

    # 2) A partir daqui o cálculo já está pronto. Cada efeito colateral abaixo
    #    (gravar no banco, acionar equipamentos, montar e-mail) é isolado em
    #    seu próprio try/except: uma falha em qualquer um deles não deve
    #    derrubar a resposta inteira nem esconder o valor já calculado.
    aviso = None
    try:
        db.salvar_leitura(especie, indice, valor, status, temperatura.entradas)
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
        "equipamento": equipamento_info,
        "email": email_info,
        "tocarSom": bool(config.get("habilitarSons")),
        "historico": historico,
    }
    if aviso:
        resposta["aviso"] = aviso
    return jsonify(resposta)


@app.route("/api/sensor")
def sensor_simulado():
    """Simula a leitura de um sensor remoto (Área 02 - opção 'Coletar
    Dados' da dissertação, seção 3.4.3). Gera valores plausíveis dentro da
    faixa validada no Capítulo IV (0-45°C / 0,01-5,00 m/s)."""
    indice = request.args.get("indice", "")
    if indice == "ITU":
        leitura = {"tbs": round(random.uniform(18, 40), 1), "tbu": round(random.uniform(12, 30), 1)}
    elif indice == "ITUV":
        leitura = {
            "tbs": round(random.uniform(18, 40), 1),
            "tbu": round(random.uniform(12, 30), 1),
            "v": round(random.uniform(0.1, 5.0), 2),
        }
    elif indice == "IGNU":
        leitura = {"tgn": round(random.uniform(18, 45), 1), "tpo": round(random.uniform(5, 30), 1)}
    else:
        return jsonify({"erro": "Índice inválido."}), 400
    return jsonify(leitura)


@app.route("/api/historico")
def historico():
    especie = request.args.get("especie", "")
    indice = request.args.get("indice", "")
    return jsonify(db.obter_historico(especie, indice, limite=20))


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
    _resfriador.desativar()
    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(debug=True)
