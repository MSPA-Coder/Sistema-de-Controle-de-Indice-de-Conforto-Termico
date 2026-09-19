"""APIs públicas da aba Operação.

O navegador conversa somente com o ICT. Depois de autenticar a sessão e
autorizar o perfil, estas rotas encaminham a ação à API privada do coletor.
"""

from flask import Blueprint, jsonify, request

from app import database as db
from app.seguranca import auth
from app.seguranca.tokens import CAPACIDADE_CONTROLE
from app.seguranca.zonas import verificar_acesso_zona

from .coletor_client import chamar_coletor

operacao_bp = Blueprint("operacao", __name__)


def _negar_zona_se_necessario(zona_id: int):
    usuario = auth.usuario_atual()
    if usuario is None:
        return jsonify({"erro": "Autenticação necessária."}), 401
    decisao = verificar_acesso_zona(
        zona_id,
        perfil=usuario["perfil"],
        area="operacao",
        obter_zona=db.obter_zona,
    )
    if decisao == "nao_encontrada":
        return jsonify({"erro": f"Zona {zona_id} não encontrada."}), 404
    if decisao == "negada":
        return jsonify({"erro": "Seu perfil não tem acesso a esta zona."}), 403
    return None


@operacao_bp.route("/api/zonas/<int:zona_id>/calcular", methods=["POST"])
def calcular_zona(zona_id):
    if resposta := _negar_zona_se_necessario(zona_id):
        return resposta
    return chamar_coletor(
        f"/api/interno/zonas/{zona_id}/calcular",
        metodo="POST",
        dados=request.get_json(force=True, silent=True) or {},
        capacidade=CAPACIDADE_CONTROLE,
    )


@operacao_bp.route("/api/zonas/<int:zona_id>/controle", methods=["PUT"])
def alterar_controle_zona(zona_id):
    if resposta := _negar_zona_se_necessario(zona_id):
        return resposta
    return chamar_coletor(
        f"/api/interno/zonas/{zona_id}/controle",
        metodo="PUT",
        dados=request.get_json(force=True, silent=True) or {},
        capacidade=CAPACIDADE_CONTROLE,
    )


@operacao_bp.route("/api/zonas/<int:zona_id>/comando", methods=["POST"])
def comandar_atuador_zona(zona_id):
    if resposta := _negar_zona_se_necessario(zona_id):
        return resposta
    return chamar_coletor(
        f"/api/interno/zonas/{zona_id}/comando",
        metodo="POST",
        dados=request.get_json(force=True, silent=True) or {},
        capacidade=CAPACIDADE_CONTROLE,
    )
