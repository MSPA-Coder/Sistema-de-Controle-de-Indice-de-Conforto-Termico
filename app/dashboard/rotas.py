# -*- coding: utf-8 -*-
"""
dashboard/rotas.py
=====================
Rotas da aba Analises. So leitura: nenhuma delas grava no banco, aciona
equipamento ou fala Modbus -- por isso `database.py` e a UNICA dependencia
deste modulo (ver o pacote `coletor` para tudo que fala com hardware).
Registradas via `dashboard_bp`, montado em `app_factory.criar_app` quando
`papel_app` e `None` ou `"dashboard"`.
"""

from __future__ import annotations

from flask import Blueprint, jsonify

from .. import database as db

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/api/analises", methods=["GET"])
def obter_analises():
    return jsonify(db.obter_estatisticas_zonas())


@dashboard_bp.route("/api/analises/painel-executivo", methods=["GET"])
def obter_painel_executivo():
    return jsonify(db.obter_painel_zonas())
