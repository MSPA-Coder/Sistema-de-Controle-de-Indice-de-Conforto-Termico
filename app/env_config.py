# -*- coding: utf-8 -*-
"""Carregamento mínimo do `.env` para execução local.

O arquivo contém somente parâmetros de implantação e não é editável pelo
ICT. No Docker, o Compose injeta esses valores ao criar os contêineres.
Configurações operacionais mantidas pelas abas vivem no PostgreSQL e são
consultadas pelo coletor durante seus ciclos.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

CAMINHO_ENV = Path(__file__).resolve().parent.parent / ".env"
CHAVES = frozenset(
    {
        "COLETOR_URL",
        "SMTP_HOST",
        "SMTP_PORT",
        "SMTP_USER",
        "SMTP_PASS",
    }
)
_LINHA_VALIDA = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$")


def carregar() -> None:
    """Carrega chaves conhecidas sem sobrescrever o ambiente do processo."""

    try:
        linhas = CAMINHO_ENV.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return

    for linha in linhas:
        bruta = linha.strip()
        if not bruta or bruta.startswith("#"):
            continue
        combinacao = _LINHA_VALIDA.match(bruta)
        if not combinacao:
            continue
        chave, valor = combinacao.groups()
        if chave in CHAVES:
            os.environ.setdefault(chave, valor)
