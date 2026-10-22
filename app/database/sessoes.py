"""Sessões encerradas no logout.

O cookie de sessão é assinado e sem estado no servidor; o `sid` gravado nele no
login é registrado aqui quando a pessoa sai, e `_carregar_usuario_da_sessao`
trata a sessão com `sid` revogado como deslogada. Ver a migração
``20261021_01_sessoes_revogadas``.
"""

from __future__ import annotations

import datetime

from .comum import conexao


def revogar_sessao(sid: str, expira_em: datetime.datetime) -> None:
    """Registra o `sid` como encerrado até `expira_em` (UTC) e limpa os vencidos."""
    agora = datetime.datetime.now(datetime.UTC).isoformat()
    with conexao() as conn:
        conn.execute("DELETE FROM sessoes_revogadas WHERE expira_em < ?", (agora,))
        conn.execute(
            "INSERT INTO sessoes_revogadas (sid, expira_em) VALUES (?, ?) ON CONFLICT DO NOTHING",
            (sid, expira_em.astimezone(datetime.UTC).isoformat()),
        )


def sessao_revogada(sid: str) -> bool:
    with conexao(escrita=False) as conn:
        linha = conn.execute("SELECT 1 FROM sessoes_revogadas WHERE sid = ?", (sid,)).fetchone()
    return linha is not None
