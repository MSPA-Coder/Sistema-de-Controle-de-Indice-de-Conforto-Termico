"""Fronteira explícita de autorização de zona.

Usuários administradores mantêm acesso global por perfil. Os demais precisam
de uma concessão persistida na relação ``historico.usuario_zonas``. A
existência da zona é sempre conferida antes do encaminhamento, evitando que um
ID arbitrário atravesse a fronteira ICT→coletor.
"""

from __future__ import annotations

from collections.abc import Callable


def verificar_acesso_zona(
    zona_id: int,
    *,
    perfil: str,
    area: str,
    obter_zona: Callable[[int], dict | None],
    usuario_id: int | None = None,
    tem_acesso_zona: Callable[[int, int], bool] | None = None,
) -> str:
    """Retorna ``autorizada``, ``negada`` ou ``nao_encontrada``.

    ``usuario_id`` é opcional somente para manter a função útil em testes
    unitários antigos que mediam apenas a política por área. As rotas reais
    sempre o fornecem; nesse caminho a ausência da associação nega o acesso.
    """
    from .auth import area_permitida

    if not area_permitida(perfil, area):
        return "negada"
    if obter_zona(zona_id) is None:
        return "nao_encontrada"

    if usuario_id is not None and perfil != "administrador":
        if tem_acesso_zona is None:
            from .. import database as db

            tem_acesso_zona = db.usuario_tem_acesso_zona
        if not tem_acesso_zona(usuario_id, zona_id):
            return "negada"

    return "autorizada"
