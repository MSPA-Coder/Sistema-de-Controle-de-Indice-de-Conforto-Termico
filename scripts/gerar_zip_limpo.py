"""Gera um ZIP limpo do Sistema de Controle dos Índices de Conforto Térmico.

O arquivo gerado não inclui metadados locais, caches, bancos SQLite,
ambientes virtuais, logs ou temporários.

Uso, a partir da raiz do projeto:
    docker compose --env-file .env.docker run --rm --no-deps \
        -v "${PWD}/dist:/output" ict \
        python scripts/gerar_zip_limpo.py --output /output/ConfortoTermico_clean.zip

O utilitário deve ser executado na imagem Docker do projeto. O destino precisa
ser um volume gravável porque os contêneres operacionais usam filesystem de
somente leitura.
"""

from __future__ import annotations

import argparse
import fnmatch
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = PROJECT_ROOT.parent / f"{PROJECT_ROOT.name}_clean.zip"

EXCLUDED_DIRS = {
    ".agents",
    ".codex",
    ".dropbox.cache",
    ".git",
    ".hypothesis",
    ".idea",
    ".mypy_cache",
    ".nox",
    ".pyre",
    ".pytest_cache",
    ".pytype",
    ".ruff_cache",
    ".tox",
    ".venv",
    "__pycache__",
    "__pypackages__",
    "backups",
    "build",
    "dist",
    "env",
    "htmlcov",
    "instance",
    "logs",
    "tmp",
    "temp",
    "uploads",
    "venv",
}

EXCLUDED_PATTERNS = (
    "*.bak",
    "*.db",
    "*.db-*",
    "*.db-journal",
    "*.db-shm",
    "*.db-wal",
    "*.egg",
    "*.egg-info",
    "*.log",
    "*.mdc",
    "*.pyc",
    "*.pyo",
    "*.sqlite",
    "*.sqlite-*",
    "*.sqlite3",
    "*.sqlite3-*",
    "*.swp",
    "*.swo",
    "*.tmp",
    "*.zip",
    ".coverage",
    ".coverage.*",
    ".DS_Store",
    ".dropbox",
    ".dropbox.attr",
    ".env",
    ".env.*",
    "Thumbs.db",
    "desktop.ini",
    "pip-wheel-metadata",
)


def _is_excluded(path: Path) -> bool:
    rel = path.relative_to(PROJECT_ROOT)
    rel_parts = rel.parts
    if any(part in EXCLUDED_DIRS for part in rel_parts):
        return True
    name = path.name
    return any(fnmatch.fnmatch(name, pattern) for pattern in EXCLUDED_PATTERNS)


def gerar_zip(output: Path) -> Path:
    output = output.resolve()
    if output.exists():
        output.unlink()

    files = [
        path
        for path in PROJECT_ROOT.rglob("*")
        if path.is_file() and path.resolve() != output and not _is_excluded(path)
    ]

    with ZipFile(output, "w", ZIP_DEFLATED) as zf:
        for path in sorted(files):
            arcname = PROJECT_ROOT.name / path.relative_to(PROJECT_ROOT)
            zf.write(path, arcname.as_posix())

    return output


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Gera ZIP limpo do Sistema de Controle dos Índices de Conforto Térmico."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Caminho do ZIP de saída. Padrão: {DEFAULT_OUTPUT}",
    )
    args = parser.parse_args()

    output = gerar_zip(args.output)
    print(output)


if __name__ == "__main__":
    main()
