"""Trilha persistente e consultável das operações administrativas relevantes."""

from __future__ import annotations

import datetime
import json
from typing import Any

from .comum import conexao


def registrar_evento_auditoria(
    *,
    evento: str,
    categoria: str,
    acao: str,
    sucesso: bool,
    ator_id: int | None,
    ator_login: str,
    ator_perfil: str,
    contexto: dict[str, Any],
    detalhes: dict[str, Any],
) -> None:
    """Persiste somente o contexto mínimo necessário para revisão posterior."""
    criado_em = datetime.datetime.now(datetime.UTC).isoformat()
    with conexao() as conn:
        conn.execute(
            """
            INSERT INTO auditoria_eventos
                (evento, categoria, acao, sucesso, ator_id, ator_login, ator_perfil,
                 contexto, detalhes, criado_em)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                evento,
                categoria,
                acao,
                int(sucesso),
                ator_id,
                ator_login,
                ator_perfil,
                json.dumps(contexto, ensure_ascii=False),
                json.dumps(detalhes, ensure_ascii=False),
                criado_em,
            ),
        )


def listar_eventos_auditoria(limite: int = 100) -> list[dict[str, Any]]:
    limite = max(1, min(500, int(limite)))
    with conexao(escrita=False) as conn:
        linhas = conn.execute(
            """
            SELECT evento, categoria, acao, sucesso, ator_id, ator_login, ator_perfil,
                   contexto, detalhes, criado_em
            FROM auditoria_eventos
            ORDER BY id DESC
            LIMIT ?
            """,
            (limite,),
        ).fetchall()
    resultado = []
    for linha in linhas:
        item = dict(linha)
        item["sucesso"] = bool(item["sucesso"])
        for chave in ("contexto", "detalhes"):
            try:
                item[chave] = json.loads(item[chave])
            except (TypeError, json.JSONDecodeError):
                item[chave] = {}
        resultado.append(item)
    return resultado
