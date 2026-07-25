# -*- coding: utf-8 -*-
"""Cliente HTTP privado usado pelo ICT para falar com o coletor."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from flask import current_app, jsonify

from .. import auth

COLETOR_URL_PADRAO = "http://127.0.0.1:5001"
TIMEOUT_COLETOR_SEGUNDOS = 5


def chamar_coletor(caminho: str, *, metodo: str, dados: dict | None = None):
    """Encaminha uma ação autenticada e preserva JSON/status do coletor."""

    if not caminho.startswith("/api/interno/"):
        raise ValueError("O cliente interno aceita somente caminhos /api/interno/.")

    url_base = os.environ.get("COLETOR_URL", COLETOR_URL_PADRAO).rstrip("/")
    corpo = json.dumps(dados or {}).encode("utf-8")
    requisicao = urllib.request.Request(
        f"{url_base}{caminho}",
        method=metodo,
        data=corpo,
        headers={
            "X-Interno-Token": auth.obter_ou_criar_token_interno(),
            "Content-Type": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(
            requisicao, timeout=TIMEOUT_COLETOR_SEGUNDOS
        ) as resposta:
            payload = json.loads(resposta.read().decode("utf-8") or "{}")
            return jsonify(payload), resposta.status
    except urllib.error.HTTPError as erro:
        try:
            payload = json.loads(erro.read().decode("utf-8") or "{}")
        except (ValueError, UnicodeDecodeError):
            payload = {"erro": "O serviço coletor devolveu uma resposta inválida."}
        return jsonify(payload), erro.code
    except (urllib.error.URLError, TimeoutError, OSError):
        current_app.logger.exception(
            "Não foi possível falar com o serviço coletor em %s", url_base
        )
        return (
            jsonify(
                {
                    "erro": (
                        "O serviço coletor está indisponível. "
                        "Confira o estado do contêiner coletor."
                    )
                }
            ),
            502,
        )
