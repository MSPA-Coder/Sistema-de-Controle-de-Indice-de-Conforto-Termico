"""Repositório para operações com configurações do sistema."""

from __future__ import annotations

from app.repositories.base import get_conexao


class ConfiguracaoRepository:
    """Repositório para gerenciamento de configurações.

    Responsável por todas as operações CRUD relacionadas a configurações,
    incluindo cache e sanitização de dados sensíveis.
    """

    @staticmethod
    def obter_todas() -> dict[str, str]:
        """Obtém todas as configurações como dicionário chave-valor."""
        with get_conexao() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT chave, valor
                FROM configuracoes
                ORDER BY chave
            """)

            return {linha[0]: linha[1] for linha in cursor.fetchall()}

    @staticmethod
    def obter_por_chave(chave: str) -> str | None:
        """Obtém configuração por chave específica."""
        with get_conexao() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT valor
                FROM configuracoes
                WHERE chave = ?
            """,
                (chave,),
            )

            linha = cursor.fetchone()
            return linha[0] if linha else None

    @staticmethod
    def definir(chave: str, valor: str) -> bool:
        """Define ou atualiza uma configuração."""
        with get_conexao() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO configuracoes (chave, valor, atualizado_em)
                VALUES (?, ?, CURRENT_TIMESTAMP)
            """,
                (chave, valor),
            )
            conn.commit()
            return True

    @staticmethod
    def remover(chave: str) -> bool:
        """Remove uma configuração."""
        with get_conexao() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM configuracoes WHERE chave = ?", (chave,))
            conn.commit()
            return cursor.rowcount > 0

    @staticmethod
    def obter_sanitizadas() -> dict[str, str]:
        """Obtém configurações com valores sensíveis mascarados.

        Útil para logging e exibição sem expor credenciais.
        """
        configs = ConfiguracaoRepository.obter_todas()

        # Chaves que contêm dados sensíveis
        chaves_sensiveis = [
            "smtp_senha",
            "smtp_password",
            "senha",
            "password",
            "secret",
            "token",
            "api_key",
            "apikey",
        ]

        for chave in configs:
            chave_lower = chave.lower()
            if any(sensivel in chave_lower for sensivel in chaves_sensiveis):
                configs[chave] = "***"

        return configs

    @staticmethod
    def obter_grupo(prefixo: str) -> dict[str, str]:
        """Obtém configurações de um grupo específico por prefixo."""
        with get_conexao() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT chave, valor
                FROM configuracoes
                WHERE chave LIKE ?
                ORDER BY chave
            """,
                (f"{prefixo}%",),
            )

            return {linha[0]: linha[1] for linha in cursor.fetchall()}

    @staticmethod
    def definir_grupo(configuracoes: dict[str, str]) -> int:
        """Define múltiplas configurações em lote."""
        with get_conexao() as conn:
            cursor = conn.cursor()
            total = 0
            for chave, valor in configuracoes.items():
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO configuracoes (chave, valor, atualizado_em)
                    VALUES (?, ?, CURRENT_TIMESTAMP)
                """,
                    (chave, valor),
                )
                total += 1
            conn.commit()
            return total
