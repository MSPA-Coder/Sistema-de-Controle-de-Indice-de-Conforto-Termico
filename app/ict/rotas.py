"""Consultas e análises públicas servidas pelo ICT."""

from __future__ import annotations

from flask import Blueprint, current_app, g, jsonify, request

from .. import database as db
from ..nucleo.cache import CacheComTTL
from ..seguranca.limites import LimitadorJanela

ict_bp = Blueprint("ict", __name__)

TTL_CACHE_ANALISES_SEGUNDOS = 15.0
LIMITE_ANALISES_POR_MINUTO = 30
LIMITE_ANALISES_POR_HORA = 300


def _cache_analises() -> CacheComTTL:
    return current_app.extensions.setdefault(
        "conforto_cache_analises",
        CacheComTTL(ttl_segundos=TTL_CACHE_ANALISES_SEGUNDOS),
    )


def _limite_analises() -> LimitadorJanela:
    return current_app.extensions.setdefault(
        "conforto_limite_analises",
        LimitadorJanela(
            (
                (60, LIMITE_ANALISES_POR_MINUTO),
                (3600, LIMITE_ANALISES_POR_HORA),
            )
        ),
    )


def _chave_limite_analises() -> str:
    usuario = getattr(g, "usuario", None) or {}
    identidade = usuario.get("id", "anonimo")
    return f"{identidade}:{request.remote_addr or 'desconhecido'}"


def _proteger_analise():
    if not _limite_analises().permitir(_chave_limite_analises()):
        resposta = jsonify({"erro": "Limite temporário de consultas de análise excedido."})
        resposta.headers["Retry-After"] = "60"
        return resposta, 429
    return None


def _obter_com_cache(chave: str, consulta):
    cache = _cache_analises()
    resultado = cache.get(chave)
    if resultado is None:
        resultado = consulta()
        cache.set(chave, resultado)
    return resultado


@ict_bp.route("/api/analises", methods=["GET"])
def obter_analises():
    if resposta := _proteger_analise():
        return resposta
    return jsonify(
        _obter_com_cache("estatisticas_zonas", db.obter_estatisticas_zonas)
    )


@ict_bp.route("/api/analises/painel-executivo", methods=["GET"])
def obter_painel_executivo():
    if resposta := _proteger_analise():
        return resposta
    return jsonify(_obter_com_cache("painel_zonas", db.obter_painel_zonas))
