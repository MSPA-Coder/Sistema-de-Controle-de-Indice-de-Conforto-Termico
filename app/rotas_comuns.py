"""Página principal e consultas públicas compartilhadas pelas abas do ICT."""

from __future__ import annotations

import datetime
import math

from flask import Blueprint, jsonify, render_template, request

from . import agregacao, auth
from . import database as db
from . import thermal_indices as ti

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


def _parametro_data(nome: str) -> tuple[str | None, tuple | None]:
    valor = request.args.get(nome)
    if valor in (None, ""):
        return None, None
    try:
        return datetime.date.fromisoformat(valor).isoformat(), None
    except ValueError:
        return None, ({"erro": f"Parâmetro '{nome}' precisa estar em AAAA-MM-DD."}, 400)


@comum_bp.route("/")
def index():
    # Todas as abas pertencem ao ICT; somente o perfil da sessão decide
    # quais botões existem e quais APIs podem ser chamadas.
    usuario = auth.usuario_atual()
    areas_permitidas = (
        auth.AREAS_POR_PERFIL.get(usuario["perfil"], frozenset()) if usuario else frozenset()
    )
    return render_template(
        "index.html",
        usuario_atual=usuario,
        areas_permitidas=areas_permitidas,
        perfil_label=auth.PERFIL_LABEL,
    )


@comum_bp.route("/favicon.ico")
def favicon():
    return "", 204


@comum_bp.route("/api/configuracao-interface", methods=["GET"])
def configuracao_interface():
    """Metadados térmicos necessários antes de inicializar a interface."""
    return jsonify(
        {
            "indicesPorEspecie": ti.INDICES_POR_ESPECIE,
            "nomeEspecie": ti.NOME_ESPECIE,
            "nomeIndice": ti.NOME_INDICE,
            "camposPorIndice": ti.CAMPOS_POR_INDICE,
            "campoMetadados": ti.CAMPO_METADADOS,
            "abaInicial": "principal",
        }
    )


@comum_bp.route("/api/zonas", methods=["GET"])
def listar_zonas():
    return jsonify(db.listar_zonas())


@comum_bp.route("/api/zonas/historicos-recentes", methods=["GET"])
def historicos_recentes_zonas():
    """Janelas curtas de todas as zonas, usadas pelo Dashboard ao vivo."""
    limite, erro = _parametro_inteiro("limite", 30)
    if erro:
        return jsonify(erro[0]), erro[1]
    limite = max(1, min(200, limite or 30))
    return jsonify(db.obter_historicos_recentes_zonas(limite=limite))


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

    data_inicio, erro = _parametro_data("data_inicio")
    if erro:
        return jsonify(erro[0]), erro[1]
    data_fim, erro = _parametro_data("data_fim")
    if erro:
        return jsonify(erro[0]), erro[1]
    if data_inicio and data_fim and data_inicio > data_fim:
        return jsonify({"erro": "A data inicial não pode ser posterior à data final."}), 400

    return jsonify(
        db.obter_historico_leituras(
            limite=limite or 30,
            deslocamento=deslocamento,
            zona_id=zona_id,
            indice=indice,
            status=status,
            valor_referencia=valor_referencia,
            data_inicio=data_inicio,
            data_fim=data_fim,
        )
    )


@comum_bp.route("/api/zonas/<int:zona_id>/consolidar-historico", methods=["POST"])
def consolidar_historico_zona(zona_id):
    """Materializa os resumos pendentes da zona antes de exibir seu historico."""
    zona = db.obter_zona(zona_id)
    if zona is None:
        return jsonify({"erro": f"Zona {zona_id} nao encontrada."}), 404
    return jsonify({"ok": True, "resultado": agregacao.executar_para_zona(zona)})


@comum_bp.route("/api/zonas/<int:zona_id>/agregados-15min", methods=["GET"])
def agregados_15min_zona(zona_id):
    """Serie de medias/minimo/maximo por janela de 15 min, consolidada por
    `agregacao.py`. Usada para graficos de tendencia mais longos sem
    precisar varrer a leitura bruta minuto a minuto."""
    if db.obter_zona(zona_id) is None:
        return jsonify({"erro": f"Zona {zona_id} nao encontrada."}), 404
    limite, erro = _parametro_inteiro("limite", 96)
    if erro:
        return jsonify(erro[0]), erro[1]
    return jsonify(db.obter_agregados_15min(zona_id, limite=limite or 96))


@comum_bp.route("/api/zonas/<int:zona_id>/resumo-horario", methods=["GET"])
def resumo_horario_zona(zona_id):
    """Serie horaria consolidada: media/minimo/maximo do indice, status da
    media e percentual de tempo em cada status na hora. E a granularidade
    recomendada para relatorios (ver `docs/ANALISE_DE_DADOS.pdf`)."""
    if db.obter_zona(zona_id) is None:
        return jsonify({"erro": f"Zona {zona_id} nao encontrada."}), 404
    limite, erro = _parametro_inteiro("limite", 168)
    if erro:
        return jsonify(erro[0]), erro[1]
    data_inicio, erro = _parametro_data("data_inicio")
    if erro:
        return jsonify(erro[0]), erro[1]
    data_fim, erro = _parametro_data("data_fim")
    if erro:
        return jsonify(erro[0]), erro[1]
    if data_inicio and data_fim and data_inicio > data_fim:
        return jsonify({"erro": "A data inicial não pode ser posterior à data final."}), 400
    return jsonify(
        db.obter_resumos_horarios(
            zona_id, limite=limite or 168, data_inicio=data_inicio, data_fim=data_fim
        )
    )
