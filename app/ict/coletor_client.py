"""Fronteira HTTP do ICT: recusa de negócio não é indisponibilidade."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import BinaryIO, cast

from flask import current_app, jsonify
from flask.typing import ResponseReturnValue

from app.nucleo.circuit_breaker import CircuitBreaker
from app.seguranca import auth
from app.seguranca.tokens import CAPACIDADE_CONTROLE

from .contracts import JSONObject

COLETOR_URL_PADRAO = "http://127.0.0.1:5001"
TIMEOUT_COLETOR_SEGUNDOS = 5
MAX_RESPOSTA_BYTES = 1024 * 1024
STATUS_TRANSITORIOS = frozenset({500, 502, 503, 504})


class ColetorIndisponivelError(OSError):
    """Falha de transporte, servidor transitório ou protocolo da dependência."""


def _ler_json(resposta: BinaryIO) -> JSONObject:
    bruto = resposta.read(MAX_RESPOSTA_BYTES + 1)
    if len(bruto) > MAX_RESPOSTA_BYTES:
        raise ColetorIndisponivelError("Resposta interna excedeu o limite.")
    try:
        payload = json.loads(bruto.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as erro:
        raise ColetorIndisponivelError("Resposta interna inválida.") from erro
    if not isinstance(payload, dict):
        raise ColetorIndisponivelError("Resposta interna precisa ser um objeto JSON.")
    # json.loads só produz valores JSON; após a guarda, a raiz é objeto.
    return cast("JSONObject", payload)


def _circuito() -> CircuitBreaker:
    # Um circuito por aplicação/dependência, não um estado por URL de zona.
    circuito = current_app.extensions.setdefault(
        "conforto_circuit_breaker", CircuitBreaker("coletor")
    )
    if not isinstance(circuito, CircuitBreaker):
        raise TypeError("Extensão de circuito inválida.")
    return circuito


def chamar_coletor(
    caminho: str,
    *,
    metodo: str,
    dados: JSONObject | None = None,
    capacidade: str = CAPACIDADE_CONTROLE,
) -> ResponseReturnValue:
    if not caminho.startswith("/api/interno/"):
        raise ValueError("O cliente interno aceita somente caminhos /api/interno/.")
    url_base = os.environ.get("COLETOR_URL", COLETOR_URL_PADRAO).rstrip("/")
    requisicao = urllib.request.Request(
        f"{url_base}{caminho}",
        method=metodo,
        data=json.dumps(dados or {}).encode("utf-8"),
        headers={
            "X-Interno-Token": auth.obter_token_interno(capacidade),
            "Content-Type": "application/json",
        },
    )

    def fazer_requisicao() -> ResponseReturnValue:
        try:
            with urllib.request.urlopen(requisicao, timeout=TIMEOUT_COLETOR_SEGUNDOS) as resposta:
                return jsonify(_ler_json(cast("BinaryIO", resposta))), resposta.status
        except urllib.error.HTTPError as erro:
            with erro:
                if erro.code in STATUS_TRANSITORIOS:
                    raise ColetorIndisponivelError("Falha transitória do coletor.") from erro
                try:
                    payload = _ler_json(cast("BinaryIO", erro))
                except ColetorIndisponivelError:
                    payload = {"erro": "O serviço coletor devolveu uma resposta inválida."}
                return jsonify(payload), erro.code

    def fallback() -> ResponseReturnValue:
        # Não registra bearer, URL de configuração ou texto da exceção externa.
        current_app.logger.warning("Coletor indisponível; operação interna não confirmada.")
        return jsonify(
            {
                "erro": "O serviço coletor está temporariamente indisponível. Tente novamente em alguns instantes.",
                "circuit_breaker": "ativo",
            }
        ), 502

    # Não há retry: um timeout não prova que um comando deixou de acontecer.
    return _circuito().executar(fazer_requisicao, fallback=fallback)
