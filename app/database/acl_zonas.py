"""Persistência da associação entre usuários e zonas.

Administradores mantêm acesso global por perfil; os demais perfis precisam de
uma associação explícita. A tabela é deliberadamente pequena e só guarda a
concessão, deixando a decisão de autorização na camada ``seguranca``.
"""

from __future__ import annotations

import datetime

from .comum import conexao


def usuario_tem_acesso_zona(usuario_id: int, zona_id: int) -> bool:
    with conexao(escrita=False) as conn:
        linha = conn.execute(
            "SELECT 1 FROM usuario_zonas WHERE usuario_id = ? AND zona_id = ?",
            (usuario_id, zona_id),
        ).fetchone()
    return linha is not None


def listar_zonas_do_usuario(usuario_id: int) -> list[dict]:
    with conexao(escrita=False) as conn:
        linhas = conn.execute(
            """
            SELECT z.id, z.nome, z.especie, z.indice, z.ativa
            FROM usuario_zonas uz
            JOIN zonas z ON z.id = uz.zona_id
            WHERE uz.usuario_id = ?
            ORDER BY z.nome, z.id
            """,
            (usuario_id,),
        ).fetchall()
    return [dict(linha) for linha in linhas]


def conceder_acesso_zona(usuario_id: int, zona_id: int) -> bool:
    agora = datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds")
    with conexao() as conn:
        if conn.execute("SELECT 1 FROM usuarios WHERE id = ?", (usuario_id,)).fetchone() is None:
            return False
        if conn.execute("SELECT 1 FROM zonas WHERE id = ?", (zona_id,)).fetchone() is None:
            return False
        resultado = conn.execute(
            """
            INSERT INTO usuario_zonas (usuario_id, zona_id, concedido_em)
            VALUES (?, ?, ?)
            ON CONFLICT (usuario_id, zona_id) DO NOTHING
            """,
            (usuario_id, zona_id, agora),
        )
    return resultado.rowcount > 0


def revogar_acesso_zona(usuario_id: int, zona_id: int) -> bool:
    with conexao() as conn:
        resultado = conn.execute(
            "DELETE FROM usuario_zonas WHERE usuario_id = ? AND zona_id = ?",
            (usuario_id, zona_id),
        )
    return resultado.rowcount > 0
