"""Consultas e análises públicas servidas pelo ICT."""

from __future__ import annotations

from flask import Blueprint, jsonify

from .. import database as db

ict_bp = Blueprint("ict", __name__)


@ict_bp.route("/api/analises", methods=["GET"])
def obter_analises():
    return jsonify(db.obter_estatisticas_zonas())


@ict_bp.route("/api/analises/painel-executivo", methods=["GET"])
def obter_painel_executivo():
    return jsonify(db.obter_painel_zonas())
