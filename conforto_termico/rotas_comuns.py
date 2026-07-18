# -*- coding: utf-8 -*-
"""
rotas_comuns.py
=================
Rotas somente leitura, uteis nos dois papeis de app (coletor e dashboard):
pagina inicial, lista de zonas (para rotular telas), navegacao pelo
historico persistido, e um health-check simples do banco.

Vivem num Blueprint proprio (nem em `coletor/rotas.py` nem em
`dashboard/rotas.py`) porque sao registradas nos TRES casos de
`app_factory.criar_app` (`papel_app` None/"coletor"/"dashboard"). Se
estivessem duplicadas em coletor e dashboard, o caso `papel_app=None`
(Fase 0, os dois blueprints no mesmo app) tentaria registrar a mesma URL
duas vezes -- o Flask recusa isso.
"""

from __future__ import annotations

import math

from flask import Blueprint, current_app, jsonify, render_template, request

from . import database as db
from . import thermal_indices as ti
from .app_factory import MENSAGEM_ERRO_INTERNO

comum_bp = Blueprint("comum", __name__)


def _parametro_inteiro(nome: str, padrao: int | None = None) -> tuple[int | None, tuple | None]:
    valor = request.args.get(nome)
    if valor in (None, ""):
        return padrao, None
    try:
        return int(valor), None
    except ValueError:
        return None, ({"erro": f"Parâmetro '{nome}' precisa ser inteiro."}, 400)


def _parametro_float(nome: str) -> tuple[float | None, tuple | None]:
    valor = request.args.get(nome)
    if valor in (None, ""):
        return None, None
    try:
        numero = float(valor)
    except ValueError:
        return None, ({"erro": f"Parâmetro '{nome}' precisa ser numérico."}, 400)
    if not math.isfinite(numero):
        return None, ({"erro": f"Parâmetro '{nome}' precisa ser numérico e finito."}, 400)
    return numero, None


@comum_bp.route("/")
def index():
    # O papel do app corrente (None/"coletor"/"dashboard") decide quais
    # botoes de aba o template mostra e qual aba abre por padrao -- ver
    # `templates/index.html`. Dashboard e somente leitura e existe em
    # todos os papeis; Operacao aparece apenas no processo coletor.
    papel_app = current_app.config.get("CONFORTO_PAPEL_APP")
    aba_inicial = "principal"
    return render_template(
        "index.html",
        indices_por_especie=ti.INDICES_POR_ESPECIE,
        nome_especie=ti.NOME_ESPECIE,
        nome_indice=ti.NOME_INDICE,
        campos_por_indice=ti.CAMPOS_POR_INDICE,
        campo_metadados=ti.CAMPO_METADADOS,
        limites=ti.LIMITES,
        papel_app=papel_app,
        aba_inicial=aba_inicial,
    )


@comum_bp.route("/favicon.ico")
def favicon():
    return "", 204


@comum_bp.route("/api/zonas", methods=["GET"])
def listar_zonas():
    return jsonify(db.listar_zonas())


@comum_bp.route("/api/zonas/<int:zona_id>/historico", methods=["GET"])
def historico_zona(zona_id):
    if db.obter_zona(zona_id) is None:
        return jsonify({"erro": f"Zona {zona_id} nao encontrada."}), 404
    limite, erro = _parametro_inteiro("limite", 30)
    if erro:
        return jsonify(erro[0]), erro[1]
    limite = max(1, min(200, limite or 30))
    recentes = db.obter_leituras_recentes_zona(zona_id, limite=limite)
    return jsonify(recentes or db.obter_historico_por_zona(zona_id, limite=limite))


@comum_bp.route("/api/operacao/status", methods=["GET"])
def status_operacao():
    config = db.obter_configuracoes()
    return jsonify(
        {
            "coletor": db.obter_status_coletor(),
            "configuracao_global": {
                "habilitarEquipamentos": bool(config.get("habilitarEquipamentos")),
                "intervaloLeituraSegundos": config.get("intervaloLeituraSegundos"),
            },
            "zonas": db.obter_estado_operacional_zonas(),
        }
    )


@comum_bp.route("/api/operacao/eventos", methods=["GET"])
def eventos_operacao():
    zona_id, erro = _parametro_inteiro("zona_id")
    if erro:
        return jsonify(erro[0]), erro[1]
    limite, erro = _parametro_inteiro("limite", 30)
    if erro:
        return jsonify(erro[0]), erro[1]
    return jsonify(db.listar_eventos_operacao(zona_id, max(1, min(200, limite or 30))))


@comum_bp.route("/api/historico-leituras")
def historico_leituras():
    limite, erro = _parametro_inteiro("limite", 30)
    if erro:
        return jsonify(erro[0]), erro[1]
    deslocamento, erro = _parametro_inteiro("deslocamento")
    if erro:
        return jsonify(erro[0]), erro[1]

    zona_id, erro = _parametro_inteiro("zona_id")
    if erro:
        return jsonify(erro[0]), erro[1]
    if zona_id is not None and db.obter_zona(zona_id) is None:
        return jsonify({"erro": f"Zona {zona_id} não encontrada."}), 404

    indice = request.args.get("indice") or None
    if indice is not None and indice not in ti.NOME_INDICE:
        return jsonify({"erro": f"Índice inválido: '{indice}'."}), 400

    status = request.args.get("status") or None
    if status is not None and ti.normalizar_chave_texto(status).lower() not in ti.STATUS_PESO:
        return jsonify({"erro": f"Status inválido: '{status}'."}), 400

    valor_referencia, erro = _parametro_float("valor_referencia")
    if erro:
        return jsonify(erro[0]), erro[1]

    return jsonify(
        db.obter_historico_leituras(
            limite=limite or 30,
            deslocamento=deslocamento,
            zona_id=zona_id,
            indice=indice,
            status=status,
            valor_referencia=valor_referencia,
        )
    )


@comum_bp.route("/api/diagnostico")
def diagnostico():
    """Rota utilitaria de diagnostico: confirma se o banco esta acessivel e
    quantos registros ja foram gravados ao todo (util para conferir se as
    leituras estao mesmo sendo persistidas).

    O caminho absoluto do arquivo do banco so e incluido com o servidor em
    modo debug: fora de depuracao local, expor a estrutura de diretorios do
    servidor a quem acessar essa rota e um vazamento de informacao
    desnecessario para o proposito da rota (confirmar que o banco
    responde)."""
    try:
        total = db.contar_leituras()
        payload = {"banco_ok": True, "total_leituras_gravadas": total}
        if current_app.config.get("CONFORTO_DEBUG"):
            payload["arquivo_banco"] = db.DB_PATH
        return jsonify(payload)
    except Exception:
        current_app.logger.exception("Falha ao consultar diagnostico do banco")
        return jsonify({"banco_ok": False, "erro": MENSAGEM_ERRO_INTERNO}), 500
