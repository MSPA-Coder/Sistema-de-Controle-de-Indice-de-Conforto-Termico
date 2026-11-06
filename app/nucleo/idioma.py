"""Idioma da interface, isolado por contexto de requisição."""

import json
from contextvars import ContextVar
from functools import lru_cache
from pathlib import Path
from typing import Final

from werkzeug.datastructures import LanguageAccept

IDIOMA_PADRAO: Final = "pt-br"
IDIOMAS_VALIDOS: Final = (IDIOMA_PADRAO, "en")
_idioma: ContextVar[str] = ContextVar("idioma_interface", default=IDIOMA_PADRAO)
_CATALOGO_EN = Path(__file__).resolve().parent.parent / "traducoes" / "en.json"


def normalizar(idioma: str | None) -> str:
    return idioma if idioma in IDIOMAS_VALIDOS else IDIOMA_PADRAO


def do_navegador(aceitos: LanguageAccept) -> str:
    """Escolhe somente idiomas suportados, respeitando a preferência do navegador."""
    melhor = aceitos.best_match(("pt-br", "pt", "en", "en-us", "en-gb"))
    return "en" if melhor and melhor.startswith("en") else IDIOMA_PADRAO


def ativo() -> str:
    return _idioma.get()


@lru_cache(maxsize=1)
def _catalogo_en() -> dict[str, str]:
    with _CATALOGO_EN.open(encoding="utf-8") as arquivo:
        return json.load(arquivo)


def traduzir(texto: str) -> str:
    """Traduz textos de interface marcados; dados e chaves não passam aqui."""
    if ativo() != "en":
        return texto
    return _catalogo_en().get(texto, texto)


def catalogo_javascript() -> dict[str, str]:
    """Catálogo de interface, sem dados de usuários, para os módulos do navegador."""
    return _catalogo_en() if ativo() == "en" else {}


def ativar(idioma: str | None):
    return _idioma.set(normalizar(idioma))


def desativar(token) -> None:
    _idioma.reset(token)
