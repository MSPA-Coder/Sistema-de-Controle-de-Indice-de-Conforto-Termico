"""Cria os segredos locais exigidos pelo Docker Compose.

Os valores não são exibidos e arquivos existentes não são sobrescritos sem
``--force``. Em uma instalação com PostgreSQL já inicializado, trocar a senha
também exige alterar a senha do papel no banco antes de recriar os serviços.
"""

from __future__ import annotations

import argparse
import contextlib
import os
import secrets
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
DIRETORIO = RAIZ / ".secrets"
ARQUIVOS = {
    "postgres_password.txt": 36,
    "internal_token.txt": 48,
}
APP_UID = 10001
APP_GID = 10001


def _gravar(caminho: Path, quantidade_bytes: int, *, force: bool) -> bool:
    if caminho.exists() and not force:
        return False
    temporario = caminho.with_name(f".{caminho.name}.{secrets.token_hex(8)}.tmp")
    try:
        temporario.write_text(secrets.token_urlsafe(quantidade_bytes), encoding="utf-8")
        with contextlib.suppress(OSError):
            os.chown(temporario, APP_UID, APP_GID)
            os.chmod(temporario, 0o400)
        os.replace(temporario, caminho)
    finally:
        with contextlib.suppress(FileNotFoundError):
            temporario.unlink()
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--force",
        action="store_true",
        help="substitui segredos existentes (requer rotação coordenada no banco)",
    )
    args = parser.parse_args()

    DIRETORIO.mkdir(mode=0o700, parents=True, exist_ok=True)
    criados = [
        nome
        for nome, quantidade in ARQUIVOS.items()
        if _gravar(DIRETORIO / nome, quantidade, force=args.force)
    ]
    if criados:
        print(f"Segredos criados: {', '.join(criados)}")
    else:
        print("Segredos já existentes; nenhum arquivo foi alterado.")


if __name__ == "__main__":
    main()
