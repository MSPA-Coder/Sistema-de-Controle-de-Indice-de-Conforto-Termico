"""API privada do serviço coletor.

Nenhuma rota deste módulo é destinada ao navegador. O ICT autentica a
pessoa, autoriza o perfil e encaminha somente as ações de tempo real. O
token interno é conferido para toda a API, exceto no health-check.
"""

from __future__ import annotations

import hmac

from flask import Blueprint, current_app, jsonify, request

from .. import auth, notificacoes
from .. import database as db
from .. import thermal_indices as ti
from ..models import Email
from ..zona_service import ZonaCalculoError
from .controle import ModoOperacaoError, ZonaOcupadaError
from .estado import gerenciador_controle, testar_conexao_equipamento

coletor_bp = Blueprint("coletor", __name__)


def _aplicar_som_zona(resposta: dict, config: dict) -> dict:
    if config.get("habilitarSons") and resposta.get("status") != "Conforto":
        resposta["tocarSom"] = True
    return resposta


def _aplicar_notificacoes_zona(resposta: dict, config: dict) -> dict:
    """Fluxo MANUAL: som + e-mail SINCRONO (ver docstring de
    `notificacoes.py` sobre por que este fluxo, ao contrario do
    automatico, pode continuar enviando sem fila -- e uma unica
    requisicao HTTP isolada, nao a thread que cuida de todas as zonas)."""
    _aplicar_som_zona(resposta, config)

    if not notificacoes.deve_notificar_email(resposta, config):
        return resposta

    try:
        conteudo = notificacoes.montar_conteudo_zona(resposta)
        destino = (config.get("emailDestino") or "alertas@example.invalid").strip()
        email = Email(destino, conteudo)
        enviado_de_verdade = email.enviar(notificacoes.smtp_config_atual(config))
        resposta["email"] = {
            "destino": destino,
            "conteudo": conteudo,
            "enviado_de_verdade": enviado_de_verdade,
        }
    except Exception:
        current_app.logger.exception("Falha ao montar/enviar e-mail da zona")
    return resposta


def _token_interno_valido() -> bool:
    esperado = auth.obter_ou_criar_token_interno()
    enviado = request.headers.get("X-Interno-Token", "")
    # comparacao em tempo constante: isto e uma checagem de segredo, nao
    # de identidade de usuario, mas o mesmo cuidado contra timing attack
    # se aplica.
    return bool(esperado) and hmac.compare_digest(enviado, esperado)


@coletor_bp.before_request
def _exigir_token_interno():
    if request.endpoint == "coletor.health":
        return None
    if not _token_interno_valido():
        return jsonify({"erro": "Token interno inválido ou ausente."}), 403
    return None


@coletor_bp.route("/health", methods=["GET"])
def health():
    return jsonify({"servico": "coletor", "status": "ok"})


@coletor_bp.route(
    "/api/interno/zonas/<int:zona_id>/equipamentos/<int:equipamento_id>/testar-conexao",
    methods=["POST"],
)
def testar_conexao_interno(zona_id, equipamento_id):
    equipamento = db.obter_equipamento(equipamento_id)
    if equipamento is None or equipamento["zona_id"] != zona_id:
        return jsonify(
            {"erro": f"Equipamento {equipamento_id} não encontrado na zona {zona_id}."}
        ), 404
    return jsonify(testar_conexao_equipamento(equipamento))


@coletor_bp.route("/api/interno/zonas/<int:zona_id>/calcular", methods=["POST"])
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


@coletor_bp.route("/api/interno/zonas/<int:zona_id>/controle", methods=["PUT"])
def alterar_controle_zona(zona_id):
    dados = request.get_json(force=True, silent=True) or {}
    try:
        return jsonify(
            gerenciador_controle.alterar_controle(zona_id, dados, logger=current_app.logger)
        )
    except db.ZonaNaoEncontradaError as erro:
        return jsonify({"erro": str(erro)}), 404
    except (db.ZonaInvalidaError, ZonaCalculoError, ZonaOcupadaError) as erro:
        return jsonify({"erro": str(erro)}), 400


@coletor_bp.route("/api/interno/zonas/<int:zona_id>/comando", methods=["POST"])
def comandar_atuador_zona(zona_id):
    dados = request.get_json(force=True, silent=True) or {}
    tipo = dados.get("tipo")
    ligar = dados.get("ligar")
    if not isinstance(tipo, str) or not isinstance(ligar, bool):
        return jsonify({"erro": "tipo deve ser texto e ligar deve ser booleano."}), 400
    try:
        return jsonify(
            gerenciador_controle.comandar_manual(
                zona_id,
                tipo,
                ligar,
                logger=current_app.logger,
            )
        )
    except (ZonaCalculoError, ZonaOcupadaError) as erro:
        return jsonify({"erro": str(erro)}), 400
