# -*- coding: utf-8 -*-
"""
coletor/rotas.py
==================
Rotas que falam Modbus, calculam o indice e gravam no banco: cadastro de
zonas e equipamentos, disparo do ciclo de leitura+calculo+acionamento,
configuracao do sistema e manutencao do historico. Registradas via
`coletor_bp`, montado em `app_factory.criar_app` quando `papel_app` e
`None` ou `"coletor"`.
"""

from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request

from .. import database as db
from .. import modbus_client
from .. import thermal_indices as ti
from ..app_factory import MENSAGEM_ERRO_INTERNO
from ..models import Email
from ..zona_service import ZonaCalculoError
from .estado import (
    gerenciador_controle,
    zona_service,
    zona_simulador,
)
from .controle import ModoOperacaoError, ZonaOcupadaError

coletor_bp = Blueprint("coletor", __name__)


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
    reexibir o valor real. `database.obter_configuracoes()` continua
    disponível para os serviços executados no servidor; a máscara se
    aplica somente no limite HTTP."""
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
    db.limpar_historico()
    zona_service.limpar_historico_grafico()
    zona_service.limpar_resfriador()
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
        entradas = dados.get("entradas") if isinstance(dados.get("entradas"), dict) else None
        resposta = gerenciador_controle.calcular_manual(
            zona_id, entradas, logger=current_app.logger
        )
        resposta = _aplicar_notificacoes_zona(resposta, db.obter_configuracoes())
        return jsonify(resposta)
    except (
        ZonaCalculoError,
        ti.EntradaInvalidaError,
        ModoOperacaoError,
        ZonaOcupadaError,
    ) as erro:
        return jsonify({"erro": str(erro)}), 400


@coletor_bp.route("/api/zonas/<int:zona_id>/controle", methods=["PUT"])
def alterar_controle_zona(zona_id):
    dados = request.get_json(force=True, silent=True) or {}
    try:
        return jsonify(
            gerenciador_controle.alterar_controle(
                zona_id, dados, logger=current_app.logger
            )
        )
    except db.ZonaNaoEncontradaError as erro:
        return jsonify({"erro": str(erro)}), 404
    except (db.ZonaInvalidaError, ZonaCalculoError, ZonaOcupadaError) as erro:
        return jsonify({"erro": str(erro)}), 400


@coletor_bp.route("/api/zonas/<int:zona_id>/comando", methods=["POST"])
def comandar_atuador_zona(zona_id):
    dados = request.get_json(force=True, silent=True) or {}
    try:
        return jsonify(
            gerenciador_controle.comandar_manual(
                zona_id,
                dados.get("tipo", ""),
                dados.get("ligar"),
                logger=current_app.logger,
            )
        )
    except (ZonaCalculoError, ZonaOcupadaError) as erro:
        return jsonify({"erro": str(erro)}), 400
