"""Repositório para operações com zonas térmicas."""

from __future__ import annotations

from typing import Any

from app.repositories.base import get_conexao


class ZonaRepository:
    """Repositório para gerenciamento de zonas térmicas.

    Responsável por todas as operações CRUD relacionadas a zonas,
    separando a lógica de acesso a dados da lógica de negócio.
    """

    @staticmethod
    def obter_todas() -> list[dict[str, Any]]:
        """Obtém todas as zonas do banco de dados."""
        with get_conexao() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, nome, descricao, criado_em, atualizado_em
                FROM zonas
                ORDER BY nome
            """)
            return [dict(linha) for linha in cursor.fetchall()]

    @staticmethod
    def obter_por_id(zona_id: int) -> dict[str, Any] | None:
        """Obtém uma zona pelo ID."""
        with get_conexao() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, nome, descricao, criado_em, atualizado_em
                FROM zonas
                WHERE id = ?
            """,
                (zona_id,),
            )
            linha = cursor.fetchone()
            return dict(linha) if linha else None

    @staticmethod
    def criar(nome: str, descricao: str = "") -> int:
        """Cria uma nova zona."""
        with get_conexao() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO zonas (nome, descricao)
                VALUES (?, ?)
            """,
                (nome, descricao),
            )
            conn.commit()
            return cursor.lastrowid

    @staticmethod
    def atualizar(zona_id: int, nome: str | None = None, descricao: str | None = None) -> bool:
        """Atualiza uma zona existente."""
        with get_conexao() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM zonas WHERE id = ?", (zona_id,))
            if not cursor.fetchone():
                return False

            atualizacoes = []
            valores = []
            if nome is not None:
                atualizacoes.append("nome = ?")
                valores.append(nome)
            if descricao is not None:
                atualizacoes.append("descricao = ?")
                valores.append(descricao)

            if atualizacoes:
                valores.append(zona_id)
                query = f"UPDATE zonas SET {', '.join(atualizacoes)}, atualizado_em = CURRENT_TIMESTAMP WHERE id = ?"
                cursor.execute(query, valores)
                conn.commit()
            return True

    @staticmethod
    def excluir(zona_id: int) -> bool:
        """Exclui uma zona."""
        with get_conexao() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM zonas WHERE id = ?", (zona_id,))
            conn.commit()
            return cursor.rowcount > 0

    @staticmethod
    def obter_com_leituras(zona_id: int) -> dict[str, Any] | None:
        """Obtém zona com suas leituras recentes (JOIN otimizado).

        Elimina problema N+1 ao buscar zona e leituras em uma única query.
        """
        with get_conexao() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT
                    z.id, z.nome, z.descricao, z.criado_em, z.atualizado_em,
                    l.id as leitura_id, l.temperatura, l.umidade, l.timestamp
                FROM zonas z
                LEFT JOIN leituras l ON z.id = l.zona_id
                WHERE z.id = ?
                ORDER BY l.timestamp DESC
                LIMIT 100
            """,
                (zona_id,),
            )

            linhas = cursor.fetchall()
            if not linhas:
                return None

            primeira = dict(linhas[0])
            zona = {
                "id": primeira["id"],
                "nome": primeira["nome"],
                "descricao": primeira["descricao"],
                "criado_em": primeira["criado_em"],
                "atualizado_em": primeira["atualizado_em"],
                "leituras": [],
            }

            for linha in linhas:
                dados = dict(linha)
                if dados["leitura_id"]:
                    zona["leituras"].append(
                        {
                            "id": dados["leitura_id"],
                            "temperatura": dados["temperatura"],
                            "umidade": dados["umidade"],
                            "timestamp": dados["timestamp"],
                        }
                    )

            return zona
