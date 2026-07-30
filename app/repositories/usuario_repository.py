"""Repositório para operações com usuários e autenticação."""

from __future__ import annotations

from typing import Any

from app.auth import conferir_senha
from app.repositories.base import get_conexao


class UsuarioRepository:
    """Repositório para gerenciamento de usuários.

    Responsável por todas as operações CRUD relacionadas a usuários,
    incluindo validação de credenciais e gestão de sessões.
    """

    @staticmethod
    def obter_por_login(login: str) -> dict[str, Any] | None:
        """Obtém usuário pelo login."""
        with get_conexao() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, login, senha_hash, nome, email, area_id, ativo, criado_em
                FROM usuarios
                WHERE login = ?
            """,
                (login,),
            )

            linha = cursor.fetchone()
            if linha:
                return dict(linha)
            return None

    @staticmethod
    def obter_por_id(usuario_id: int) -> dict[str, Any] | None:
        """Obtém usuário pelo ID."""
        with get_conexao() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, login, senha_hash, nome, email, area_id, ativo, criado_em
                FROM usuarios
                WHERE id = ?
            """,
                (usuario_id,),
            )

            linha = cursor.fetchone()
            if linha:
                return dict(linha)
            return None

    @staticmethod
    def criar(
        login: str, senha_hash: str, nome: str, email: str, area_id: int | None = None
    ) -> int:
        """Cria um novo usuário."""
        with get_conexao() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO usuarios (login, senha_hash, nome, email, area_id)
                VALUES (?, ?, ?, ?, ?)
            """,
                (login, senha_hash, nome, email, area_id),
            )
            conn.commit()
            return cursor.lastrowid

    @staticmethod
    def atualizar_senha(usuario_id: int, nova_senha_hash: str) -> bool:
        """Atualiza a senha do usuário."""
        with get_conexao() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE usuarios
                SET senha_hash = ?, atualizado_em = CURRENT_TIMESTAMP
                WHERE id = ?
            """,
                (nova_senha_hash, usuario_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    @staticmethod
    def atualizar_status(usuario_id: int, ativo: bool) -> bool:
        """Ativa ou desativa usuário."""
        with get_conexao() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE usuarios
                SET ativo = ?, atualizado_em = CURRENT_TIMESTAMP
                WHERE id = ?
            """,
                (ativo, usuario_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    @staticmethod
    def listar_todos() -> list[dict[str, Any]]:
        """Lista todos os usuários (sem senha_hash por segurança)."""
        with get_conexao() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, login, nome, email, area_id, ativo, criado_em
                FROM usuarios
                ORDER BY nome
            """)

            return [dict(linha) for linha in cursor.fetchall()]

    @staticmethod
    def validar_credenciais(login: str, senha: str) -> dict[str, Any] | None:
        """Valida credenciais de login (com JOIN para área).

        Query otimizada para evitar N+1 ao buscar usuário e área.
        """
        with get_conexao() as conn:
            cursor = conn.cursor()
            # JOIN otimizado para buscar usuário e área em uma query
            cursor.execute(
                """
                SELECT
                    u.id, u.login, u.senha_hash, u.nome, u.email,
                    u.area_id, u.ativo, u.criado_em,
                    a.id as area_id, a.nome as area_nome, a.descricao as area_descricao
                FROM usuarios u
                LEFT JOIN areas a ON u.area_id = a.id
                WHERE u.login = ? AND u.ativo = 1
            """,
                (login,),
            )

            linha = cursor.fetchone()
            if not linha:
                return None

            dados = dict(linha)

            # Verifica senha
            if not conferir_senha(senha, dados["senha_hash"]):
                return None

            # Remove senha_hash do resultado
            del dados["senha_hash"]

            # Estrutura área separadamente
            if dados["area_id"]:
                dados["area"] = {
                    "id": dados.pop("area_id"),
                    "nome": dados.pop("area_nome"),
                    "descricao": dados.pop("area_descricao"),
                }
            else:
                dados.pop("area_id")
                dados.pop("area_nome")
                dados.pop("area_descricao")
                dados["area"] = None

            return dados
