"""APIs públicas da aba Operação.

O navegador conversa somente com o ICT. Depois de autenticar a sessão e
autorizar o perfil, estas rotas encaminham a ação à API privada do coletor.
"""

from flask import Blueprint, request

from .coletor_client import chamar_coletor

operacao_bp = Blueprint("operacao", __name__)


@operacao_bp.route("/api/zonas/<int:zona_id>/calcular", methods=["POST"])
def calcular_zona(zona_id):
    return chamar_coletor(
        f"/api/interno/zonas/{zona_id}/calcular",
        metodo="POST",
        dados=request.get_json(force=True, silent=True) or {},
    )


@operacao_bp.route("/api/zonas/<int:zona_id>/controle", methods=["PUT"])
def alterar_controle_zona(zona_id):
    return chamar_coletor(
        f"/api/interno/zonas/{zona_id}/controle",
        metodo="PUT",
        dados=request.get_json(force=True, silent=True) or {},
    )


@operacao_bp.route("/api/zonas/<int:zona_id>/comando", methods=["POST"])
def comandar_atuador_zona(zona_id):
    return chamar_coletor(
        f"/api/interno/zonas/{zona_id}/comando",
        metodo="POST",
        dados=request.get_json(force=True, silent=True) or {},
    )
