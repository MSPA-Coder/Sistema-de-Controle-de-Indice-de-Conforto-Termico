"""Leitura fechada dos Docker secrets usados pelos processos da aplicação."""

from __future__ import annotations

import os
from pathlib import Path

DOCKER_SECRETS_DIR = Path("/run/secrets")


def read_compose_secret(variable: str, filename: str) -> str | None:
    """Lê somente o arquivo de segredo Compose esperado para ``variable``.

    ``*_FILE`` é configuração de implantação, não um seletor arbitrário de
    arquivo. O token explícito em variável permanece disponível onde o
    contrato o prevê; esta função trata exclusivamente o caminho do Docker
    secret montado pelo Compose.
    """
    configured = os.environ.get(variable)
    if configured is None:
        return None
    if not configured.strip():
        raise RuntimeError(f"{variable} não pode estar vazio.")

    expected = (DOCKER_SECRETS_DIR / filename).resolve(strict=False)
    try:
        candidate = Path(configured).resolve(strict=True)
    except OSError as error:
        raise RuntimeError(f"Não foi possível ler o segredo indicado por {variable}.") from error
    if candidate != expected or not candidate.is_file():
        raise RuntimeError(f"{variable} deve apontar para /run/secrets/{filename}.")

    try:
        value = candidate.read_text(encoding="utf-8").strip()
    except OSError as error:
        raise RuntimeError(f"Não foi possível ler o segredo indicado por {variable}.") from error
    if not value:
        raise RuntimeError(f"{variable} não pode estar vazio.")
    return value
