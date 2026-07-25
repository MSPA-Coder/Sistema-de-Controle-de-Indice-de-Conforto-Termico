# -*- coding: utf-8 -*-
"""Administração pública do ICT.

Cadastro, configurações e manutenção persistem no PostgreSQL. A única ação
que precisa do hardware, o teste de conexão, atravessa a API privada do
coletor pelo mesmo cliente interno utilizado pela aba Operação.
"""

from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request

from .. import database as db
from .coletor_client import chamar_coletor

administracao_bp = Blueprint("administracao", __name__)

def _configuracoes_publicas(config: dict) -> dict:
    """Nunca deixa a senha SMTP sair do servidor -- mesma mascara que
    existia em `coletor/rotas.py` antes desta rota se mudar de modulo."""
    publico = dict(config)
    publico["smtpSenhaConfigurada"] = bool(publico.get("smtpSenha"))
    publico["smtpSenha"] = ""
    return publico


# ---------------------------------------------------------------------------
# Configuracoes, backup e reset
# ---------------------------------------------------------------------------
@administracao_bp.route("/api/backup-banco", methods=["POST"])
def backup_banco():
    try:
        return jsonify({"ok": True, "backup": db.criar_backup_banco()})
    except Exception:
        from ..app_factory import MENSAGEM_ERRO_INTERNO

        current_app.logger.exception("Falha ao criar backup do banco")
        return jsonify({"ok": False, "erro": MENSAGEM_ERRO_INTERNO}), 500


@administracao_bp.route("/api/configuracoes", methods=["GET"])
def obter_configuracoes():
    return jsonify(_configuracoes_publicas(db.obter_configuracoes()))


@administracao_bp.route("/api/configuracoes", methods=["POST"])
def salvar_configuracoes():
    dados = request.get_json(force=True, silent=True) or {}
    salvas = db.salvar_configuracoes(dados)
    return jsonify(_configuracoes_publicas(salvas))


@administracao_bp.route("/api/reset", methods=["POST"])
def reset():
    """Apaga todo o historico persistido. O grafico ao vivo do coletor
    (buffer em memoria, limitado a poucas dezenas de pontos por zona) NAO
    e limpo na hora -- ele se auto-corrige sozinho dentro de poucos
    ciclos automaticos, conforme novos pontos empurram os antigos para
    fora do buffer. Trade-off deliberado: nao vale a pena outra chamada
    de rede/token para um efeito puramente cosmetico e de curtissima
    duracao numa acao administrativa rara."""
    db.limpar_historico()
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Cadastro: zonas e equipamentos
# ---------------------------------------------------------------------------
@administracao_bp.route("/api/zonas", methods=["POST"])
def criar_zona():
    dados = request.get_json(force=True, silent=True) or {}
    try:
        return jsonify(db.criar_zona(dados)), 201
    except db.ZonaInvalidaError as erro:
        return jsonify({"erro": str(erro)}), 400


@administracao_bp.route("/api/zonas/<int:zona_id>", methods=["GET"])
def obter_zona(zona_id):
    zona = db.obter_zona(zona_id)
    if zona is None:
        return jsonify({"erro": f"Zona {zona_id} não encontrada."}), 404
    return jsonify(zona)


@administracao_bp.route("/api/zonas/<int:zona_id>", methods=["PUT"])
def atualizar_zona(zona_id):
    dados = request.get_json(force=True, silent=True) or {}
    try:
        zona = db.atualizar_zona(zona_id, dados)
    except db.ZonaInvalidaError as erro:
        return jsonify({"erro": str(erro)}), 400
    if zona is None:
        return jsonify({"erro": f"Zona {zona_id} não encontrada."}), 404
    return jsonify(zona)


@administracao_bp.route("/api/zonas/<int:zona_id>", methods=["DELETE"])
def excluir_zona(zona_id):
    if not db.excluir_zona(zona_id):
        return jsonify({"erro": f"Zona {zona_id} não encontrada."}), 404
    # Ver docstring do modulo: a limpeza do estado em memoria do coletor
    # para esta zona acontece no proximo ciclo automatico dele, nao aqui.
    return jsonify({"ok": True})


@administracao_bp.route("/api/zonas/<int:zona_id>/equipamentos", methods=["POST"])
def criar_equipamento(zona_id):
    dados = request.get_json(force=True, silent=True) or {}
    try:
        return jsonify(db.criar_equipamento(zona_id, dados)), 201
    except db.ZonaNaoEncontradaError as erro:
        return jsonify({"erro": str(erro)}), 404
    except db.ZonaInvalidaError as erro:
        return jsonify({"erro": str(erro)}), 400


@administracao_bp.route("/api/zonas/<int:zona_id>/equipamentos/<int:equipamento_id>", methods=["PUT"])
def atualizar_equipamento(zona_id, equipamento_id):
    dados = request.get_json(force=True, silent=True) or {}
    try:
        equipamento = db.atualizar_equipamento(equipamento_id, dados)
    except db.ZonaInvalidaError as erro:
        return jsonify({"erro": str(erro)}), 400
    if equipamento is None or equipamento["zona_id"] != zona_id:
        return jsonify(
            {"erro": f"Equipamento {equipamento_id} não encontrado na zona {zona_id}."}
        ), 404
    return jsonify(equipamento)


@administracao_bp.route(
    "/api/zonas/<int:zona_id>/equipamentos/<int:equipamento_id>", methods=["DELETE"]
)
def excluir_equipamento(zona_id, equipamento_id):
    equipamento = db.obter_equipamento(equipamento_id)
    if equipamento is None or equipamento["zona_id"] != zona_id:
        return jsonify(
            {"erro": f"Equipamento {equipamento_id} não encontrado na zona {zona_id}."}
        ), 404
    db.excluir_equipamento(equipamento_id)
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Teste de conexao -- unica rota deste modulo que precisa do coletor
# ---------------------------------------------------------------------------
def _equipamento_da_zona_ou_none(zona_id: int, equipamento_id: int) -> dict | None:
    equipamento = db.obter_equipamento(equipamento_id)
    if equipamento is None or equipamento["zona_id"] != zona_id:
        return None
    return equipamento


@administracao_bp.route(
    "/api/zonas/<int:zona_id>/equipamentos/<int:equipamento_id>/testar-conexao", methods=["POST"]
)
def testar_conexao_equipamento(zona_id, equipamento_id):
    equipamento = _equipamento_da_zona_ou_none(zona_id, equipamento_id)
    if equipamento is None:
        return jsonify(
            {"erro": f"Equipamento {equipamento_id} não encontrado na zona {zona_id}."}
        ), 404

    return chamar_coletor(
        f"/api/interno/zonas/{zona_id}/equipamentos/{equipamento_id}/testar-conexao",
        metodo="POST",
        dados={},
    )
