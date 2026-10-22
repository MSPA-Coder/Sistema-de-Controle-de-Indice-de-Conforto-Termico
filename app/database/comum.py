"""Infraestrutura compartilhada pelos agregados de persistência."""

from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING

from app.nucleo import db_backend

if TYPE_CHECKING:
    from collections.abc import Iterator

PERFIS_VALIDOS = (
    "operador",
    "tecnico",
    "veterinario",
    "analista",
    "gestor",
    "administrador",
)


@contextmanager
def conexao(*, escrita: bool = True) -> Iterator:
    """Abre uma conexão PostgreSQL, confirma ou desfaz a transação e a fecha."""
    conn = db_backend.abrir_conexao_postgres("historico")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def coagir_booleano(valor, padrao: bool) -> bool:
    if isinstance(valor, bool):
        return valor
    if isinstance(valor, (int, float)):
        return bool(valor)
    if isinstance(valor, str):
        normalizado = valor.strip().lower()
        if normalizado in ("true", "1", "sim", "on"):
            return True
        if normalizado in ("false", "0", "nao", "não", "off", ""):
            return False
    return padrao


def normalizar_texto(valor, rotulo: str, *, maximo: int, erro: type[ValueError]) -> str:
    """Texto de cadastro: só `str`, sem caractere de controle, no limite.

    Antes, `str(valor)` transformava `None` no texto "None" e um número em nome,
    o NUL (`\x00`) chegava ao PostgreSQL e virava erro 500, e o que passava de
    255 caracteres era cortado sem aviso. Aqui cada caso vira uma recusa que diz
    o campo. Devolve o texto aparado; vazio é decisão de quem chama.
    """
    if not isinstance(valor, str):
        raise erro(f"O campo '{rotulo}' precisa ser texto.")
    texto = valor.strip()
    if any(ord(c) < 32 or ord(c) == 127 for c in texto):
        raise erro(f"O campo '{rotulo}' não pode ter caracteres de controle.")
    if len(texto) > maximo:
        raise erro(f"O campo '{rotulo}' pode ter no máximo {maximo} caracteres.")
    return texto


def exigir_booleano(valor, rotulo: str, *, erro: type[ValueError]) -> bool:
    """Booleano de cadastro: aceita só o que `coagir_booleano` reconhece.

    `coagir_booleano` devolve o padrão para qualquer texto desconhecido, o que
    fazia "talvez" virar `true` sem aviso. Em cadastro de hardware o erro tem de
    ser dito.
    """
    if isinstance(valor, bool):
        return valor
    if isinstance(valor, (int, float)) and valor in (0, 1):
        return bool(valor)
    if isinstance(valor, str):
        normalizado = valor.strip().lower()
        if normalizado in ("true", "1", "sim", "on"):
            return True
        if normalizado in ("false", "0", "nao", "não", "off"):
            return False
    raise erro(f"O campo '{rotulo}' precisa ser verdadeiro ou falso.")
