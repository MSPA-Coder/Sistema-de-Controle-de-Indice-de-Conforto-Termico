# -*- coding: utf-8 -*-
"""
coletor/rotas.py
==================
Rotas que falam Modbus, calculam o indice e gravam no banco: cadastro de
zonas e equipamentos, disparo do ciclo de leitura+calculo+acionamento,
configuracao do sistema, e o fluxo de demonstracao sem zona (aba
"Dashboard", herdado da dissertacao original -- "Area 02 - Coletar
Dados"). Registradas via `coletor_bp`, montado em `app_factory.criar_app`
quando `papel_app` e `None` ou `"coletor"`.
"""

from __future__ import annotations

import datetime

from flask import Blueprint, current_app, jsonify, request

from .. import database as db
from .. import modbus_client
from .. import thermal_indices as ti
from ..app_factory import MENSAGEM_ERRO_INTERNO
from ..models import Email, formatar_linhas_entradas
from ..zona_service import ZonaCalculoError
from .estado import (
    _resfriador,
    calculo_ict_service,
    historico_grafico_service,
    sensor_simulado_service,
    zona_service,
    zona_simulador,
)

coletor_bp = Blueprint("coletor", __name__)


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


@coletor_bp.route("/api/calcular", methods=["POST"])
def calcular():
    dados = request.get_json(force=True, silent=True) or {}
    especie = dados.get("especie", "")
    indice = dados.get("indice", "")
    entradas = dados.get("entradas", {}) or {}
    config = dados.get("config", {}) or {}

    try:
        resposta = calculo_ict_service.calcular(
            especie, indice, entradas, config, current_app.logger
        )
    except ti.EntradaInvalidaError as erro:
        return jsonify({"erro": str(erro)}), 400
    return jsonify(resposta)


@coletor_bp.route("/api/sensor")
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


@coletor_bp.route("/api/historico")
def historico():
    especie = request.args.get("especie", "")
    indice = request.args.get("indice", "")
    erro = _erro_indice_invalido(especie, indice)
    if erro:
        return jsonify(erro[0]), erro[1]
    return jsonify(db.obter_historico(especie, indice, limite=20))


@coletor_bp.route("/api/historico-todos")
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


@coletor_bp.route("/api/historico-grafico")
def historico_grafico():
    especie = request.args.get("especie", "")
    indice = request.args.get("indice", "")
    erro = _erro_indice_invalido(especie, indice)
    if erro:
        return jsonify(erro[0]), erro[1]
    return jsonify(historico_grafico_service.obter(especie, indice))


@coletor_bp.route("/api/historico-grafico-todos")
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


@coletor_bp.route("/api/backup-banco", methods=["POST"])
def backup_banco():
    try:
        return jsonify({"ok": True, "backup": db.criar_backup_banco()})
    except Exception:
        current_app.logger.exception("Falha ao criar backup do banco")
        return jsonify({"ok": False, "erro": MENSAGEM_ERRO_INTERNO}), 500


def _configuracoes_publicas(config: dict) -> dict:
    """Nunca deixa a senha SMTP sair do servidor. `smtpSenha` sempre volta
    vazio para o cliente HTTP, acompanhado de uma flag booleana
    (`smtpSenhaConfigurada`) indicando se ja existe uma senha salva --
    suficiente para a interface mostrar "senha configurada" sem nunca
    reexibir o valor real. `database.obter_configuracoes()` (usado
    internamente por `calculo_ict_service` para enviar e-mails de verdade)
    continua recebendo o valor real; a mascara so se aplica aqui, no
    limite HTTP."""
    publico = dict(config)
    publico["smtpSenhaConfigurada"] = bool(publico.get("smtpSenha"))
    publico["smtpSenha"] = ""
    return publico


def _smtp_config_atual(config: dict) -> dict:
    return {
        "host": config.get("smtpHost") or None,
        "porta": config.get("smtpPorta") or None,
        "usuario": config.get("smtpUsuario") or None,
        "senha": config.get("smtpSenha") or None,
    }


def _aplicar_som_zona(resposta: dict, config: dict) -> dict:
    if config.get("habilitarSons") and resposta.get("status") != "Conforto":
        resposta["tocarSom"] = True
    return resposta


def _deve_enviar_email_zona(resposta: dict, config: dict) -> bool:
    if not config.get("enviarEmails"):
        return False
    return ti.status_atinge_minimo(
        resposta.get("status", ""),
        config.get("statusMinimoEmail", "conforto"),
    )


def _aplicar_notificacoes_zona(resposta: dict, config: dict) -> dict:
    _aplicar_som_zona(resposta, config)

    if not _deve_enviar_email_zona(resposta, config):
        return resposta

    try:
        conteudo = Email.montar_conteudo(
            resposta["indice"],
            resposta["valor"],
            resposta["status"],
            resposta.get("entradas"),
            {"id": resposta.get("zona_id"), "nome": resposta.get("zona_nome")},
        )
        destino = (config.get("emailDestino") or "produtor@fazenda.com.br").strip()
        email = Email(destino, conteudo)
        enviado_de_verdade = email.enviar(_smtp_config_atual(config))
        resposta["email"] = {
            "destino": destino,
            "conteudo": conteudo,
            "enviado_de_verdade": enviado_de_verdade,
        }
    except Exception:
        current_app.logger.exception("Falha ao montar/enviar e-mail da zona")
    return resposta


def _formatar_entradas_email(entradas: dict | None) -> str:
    return "\n".join(formatar_linhas_entradas(entradas))


def _montar_conteudo_email_zonas(resultados: list[dict], status_minimo: str) -> str:
    agora = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    linhas = [
        "Alerta de zonas",
        f"Data: {agora}",
        f"Enviar a partir do status: {status_minimo}",
        "",
    ]
    for resultado in resultados:
        linhas.extend(
            [
                f"Zona: {resultado.get('zona_nome')} (ID {resultado.get('zona_id')})",
                f"Status: {resultado.get('status')}",
                f"Valor do {resultado.get('indice')}: {resultado.get('valor')}",
                _formatar_entradas_email(resultado.get("entradas")),
                f"Mensagem: {resultado.get('mensagem')}",
                "-" * 40,
            ]
        )
    linhas.extend(
        [
            "*" * 75,
            "Você está recebendo esse e-mail por estar cadastrado na lista de "
            "usuários do Sistema de Controle dos Índices de Conforto Térmico. "
            "Em caso de dúvida contate o administrador do sistema.",
            "Obrigado.",
        ]
    )
    return "\n".join(linha for linha in linhas if linha is not None)


def _montar_email_zonas_ativas(resultados: list[dict], config: dict) -> dict | None:
    qualificadas = [
        resultado
        for resultado in resultados
        if not resultado.get("erro") and _deve_enviar_email_zona(resultado, config)
    ]
    if not qualificadas:
        return None

    try:
        status_minimo = config.get("statusMinimoEmail", "conforto")
        conteudo = _montar_conteudo_email_zonas(qualificadas, status_minimo)
        destino = (config.get("emailDestino") or "produtor@fazenda.com.br").strip()
        email = Email(destino, conteudo)
        enviado_de_verdade = email.enviar(_smtp_config_atual(config))
        return {
            "destino": destino,
            "conteudo": conteudo,
            "enviado_de_verdade": enviado_de_verdade,
            "zonas": [resultado.get("zona_id") for resultado in qualificadas],
        }
    except Exception:
        current_app.logger.exception("Falha ao montar/enviar e-mail consolidado das zonas")
        return None


@coletor_bp.route("/api/configuracoes", methods=["GET"])
def obter_configuracoes():
    return jsonify(_configuracoes_publicas(db.obter_configuracoes()))


@coletor_bp.route("/api/configuracoes", methods=["POST"])
def salvar_configuracoes():
    dados = request.get_json(force=True, silent=True) or {}
    salvas = db.salvar_configuracoes(dados)
    return jsonify(_configuracoes_publicas(salvas))


@coletor_bp.route("/api/reset", methods=["POST"])
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
    if especie is None and indice is None:
        zona_service.limpar_historico_grafico()
        zona_service.limpar_resfriador()
    _resfriador.desativar()
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Zonas Modbus: cadastro de zonas e seus equipamentos (sensores, ventiladores,
# nebulizadores), e o disparo do ciclo de leitura+calculo+acionamento.
# ---------------------------------------------------------------------------

@coletor_bp.route("/api/zonas", methods=["POST"])
def criar_zona():
    dados = request.get_json(force=True, silent=True) or {}
    try:
        return jsonify(db.criar_zona(dados)), 201
    except db.ZonaInvalidaError as erro:
        return jsonify({"erro": str(erro)}), 400


@coletor_bp.route("/api/zonas/<int:zona_id>", methods=["GET"])
def obter_zona(zona_id):
    zona = db.obter_zona(zona_id)
    if zona is None:
        return jsonify({"erro": f"Zona {zona_id} não encontrada."}), 404
    return jsonify(zona)


@coletor_bp.route("/api/zonas/<int:zona_id>", methods=["PUT"])
def atualizar_zona(zona_id):
    dados = request.get_json(force=True, silent=True) or {}
    try:
        zona = db.atualizar_zona(zona_id, dados)
    except db.ZonaInvalidaError as erro:
        return jsonify({"erro": str(erro)}), 400
    if zona is None:
        return jsonify({"erro": f"Zona {zona_id} não encontrada."}), 404
    return jsonify(zona)


@coletor_bp.route("/api/zonas/<int:zona_id>", methods=["DELETE"])
def excluir_zona(zona_id):
    if not db.excluir_zona(zona_id):
        return jsonify({"erro": f"Zona {zona_id} não encontrada."}), 404
    zona_service.limpar_historico_grafico(zona_id)
    zona_service.limpar_resfriador(zona_id)
    return jsonify({"ok": True})


@coletor_bp.route("/api/zonas/<int:zona_id>/equipamentos", methods=["POST"])
def criar_equipamento(zona_id):
    dados = request.get_json(force=True, silent=True) or {}
    try:
        return jsonify(db.criar_equipamento(zona_id, dados)), 201
    except db.ZonaNaoEncontradaError as erro:
        return jsonify({"erro": str(erro)}), 404
    except db.ZonaInvalidaError as erro:
        return jsonify({"erro": str(erro)}), 400


@coletor_bp.route("/api/zonas/<int:zona_id>/equipamentos/<int:equipamento_id>", methods=["PUT"])
def atualizar_equipamento(zona_id, equipamento_id):
    dados = request.get_json(force=True, silent=True) or {}
    try:
        equipamento = db.atualizar_equipamento(equipamento_id, dados)
    except db.ZonaInvalidaError as erro:
        return jsonify({"erro": str(erro)}), 400
    if equipamento is None or equipamento["zona_id"] != zona_id:
        return jsonify({"erro": f"Equipamento {equipamento_id} não encontrado na zona {zona_id}."}), 404
    return jsonify(equipamento)


@coletor_bp.route("/api/zonas/<int:zona_id>/equipamentos/<int:equipamento_id>", methods=["DELETE"])
def excluir_equipamento(zona_id, equipamento_id):
    equipamento = db.obter_equipamento(equipamento_id)
    if equipamento is None or equipamento["zona_id"] != zona_id:
        return jsonify({"erro": f"Equipamento {equipamento_id} não encontrado na zona {zona_id}."}), 404
    db.excluir_equipamento(equipamento_id)
    return jsonify({"ok": True})


@coletor_bp.route(
    "/api/zonas/<int:zona_id>/equipamentos/<int:equipamento_id>/testar-conexao", methods=["POST"]
)
def testar_conexao_equipamento(zona_id, equipamento_id):
    equipamento = db.obter_equipamento(equipamento_id)
    if equipamento is None or equipamento["zona_id"] != zona_id:
        return jsonify({"erro": f"Equipamento {equipamento_id} não encontrado na zona {zona_id}."}), 404

    modo_simulado = bool(db.obter_configuracoes().get("modoSimuladoZonas", True))
    if modo_simulado:
        return jsonify({"conectado": zona_simulador.testar_conexao(equipamento), "modo_simulado": True})

    conectado = modbus_client.testar_conexao(equipamento)
    resposta = {"conectado": conectado, "modo_simulado": False}
    if not modbus_client.PYMODBUS_DISPONIVEL:
        resposta["aviso"] = (
            "A biblioteca pymodbus não está instalada neste servidor "
            "(pip install pymodbus). Sem ela, nenhuma zona consegue ler ou "
            "acionar equipamentos de verdade."
        )
    return jsonify(resposta)


@coletor_bp.route("/api/zonas/<int:zona_id>/calcular", methods=["POST"])
def calcular_zona(zona_id):
    dados = request.get_json(force=True, silent=True) or {}
    try:
        if isinstance(dados.get("entradas"), dict):
            resposta = zona_service.calcular_manual(
                zona_id, dados.get("entradas") or {}, logger=current_app.logger
            )
        else:
            resposta = zona_service.calcular(zona_id, logger=current_app.logger)
        resposta = _aplicar_notificacoes_zona(resposta, db.obter_configuracoes())
        return jsonify(resposta)
    except (ZonaCalculoError, ti.EntradaInvalidaError) as erro:
        return jsonify({"erro": str(erro)}), 400


@coletor_bp.route("/api/zonas/calcular-ativas", methods=["POST"])
def calcular_zonas_ativas():
    config = db.obter_configuracoes()
    resultados = []
    for zona in db.listar_zonas(apenas_ativas=True):
        try:
            resposta = zona_service.calcular(zona["id"], logger=current_app.logger)
            resultados.append(_aplicar_som_zona(resposta, config))
        except (ZonaCalculoError, ti.EntradaInvalidaError) as erro:
            resultados.append(
                {
                    "zona_id": zona["id"],
                    "zona_nome": zona["nome"],
                    "erro": str(erro),
                }
            )
    payload = {"resultados": resultados}
    email_info = _montar_email_zonas_ativas(resultados, config)
    if email_info:
        payload["email"] = email_info
    return jsonify(payload)


@coletor_bp.route("/api/zonas/<int:zona_id>/historico", methods=["GET"])
def historico_zona(zona_id):
    if db.obter_zona(zona_id) is None:
        return jsonify({"erro": f"Zona {zona_id} não encontrada."}), 404
    return jsonify(zona_service.obter_historico_grafico(zona_id))
