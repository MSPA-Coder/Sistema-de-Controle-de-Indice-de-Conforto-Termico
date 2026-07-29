"""Repositório para operações com leituras de sensores."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.repositories.base import get_conexao


class LeituraRepository:
    """Repositório para gerenciamento de leituras de sensores.

    Responsável por todas as operações CRUD relacionadas a leituras,
    com otimizações para consultas temporais e agregações.
    """

    @staticmethod
    def obter_ultimas(zona_id: int | None = None, limite: int = 100) -> list[dict[str, Any]]:
        """Obtém últimas leituras, opcionalmente filtradas por zona."""
        with get_conexao() as conn:
            cursor = conn.cursor()
            if zona_id:
                cursor.execute("""
                    SELECT id, zona_id, temperatura, umidade, timestamp, criado_em
                    FROM leituras
                    WHERE zona_id = ?
                    ORDER BY timestamp DESC
                    LIMIT ?
                """, (zona_id, limite))
            else:
                cursor.execute("""
                    SELECT id, zona_id, temperatura, umidade, timestamp, criado_em
                    FROM leituras
                    ORDER BY timestamp DESC
                    LIMIT ?
                """, (limite,))

            return [dict(linha) for linha in cursor.fetchall()]

    @staticmethod
    def criar(zona_id: int, temperatura: float, umidade: float) -> int:
        """Cria uma nova leitura."""
        with get_conexao() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO leituras (zona_id, temperatura, umidade)
                VALUES (?, ?, ?)
            """, (zona_id, temperatura, umidade))
            conn.commit()
            return cursor.lastrowid

    @staticmethod
    def obter_por_periodo(
        zona_id: int,
        inicio: datetime,
        fim: datetime
    ) -> list[dict[str, Any]]:
        """Obtém leituras em um período específico."""
        with get_conexao() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, zona_id, temperatura, umidade, timestamp, criado_em
                FROM leituras
                WHERE zona_id = ? AND timestamp BETWEEN ? AND ?
                ORDER BY timestamp ASC
            """, (zona_id, inicio.isoformat(), fim.isoformat()))

            return [dict(linha) for linha in cursor.fetchall()]

    @staticmethod
    def obter_medias_periodo(
        zona_id: int,
        inicio: datetime,
        fim: datetime
    ) -> dict[str, float | None]:
        """Obtém médias de temperatura e umidade em um período.
        
        Query otimizada com agregação no banco para evitar processamento em Python.
        """
        with get_conexao() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 
                    AVG(temperatura) as media_temperatura,
                    AVG(umidade) as media_umidade,
                    MIN(temperatura) as min_temperatura,
                    MAX(temperatura) as max_temperatura,
                    COUNT(*) as total_leituras
                FROM leituras
                WHERE zona_id = ? AND timestamp BETWEEN ? AND ?
            """, (zona_id, inicio.isoformat(), fim.isoformat()))

            linha = cursor.fetchone()
            if linha:
                return {
                    "media_temperatura": linha[0],
                    "media_umidade": linha[1],
                    "min_temperatura": linha[2],
                    "max_temperatura": linha[3],
                    "total_leituras": linha[4]
                }
            return {
                "media_temperatura": None,
                "media_umidade": None,
                "min_temperatura": None,
                "max_temperatura": None,
                "total_leituras": 0
            }

    @staticmethod
    def excluir_antigos(dias: int = 365) -> int:
        """Exclui leituras mais antigas que N dias."""
        with get_conexao() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                DELETE FROM leituras
                WHERE timestamp < datetime('now', ?)
            """, (f"-{dias} days",))
            conn.commit()
            return cursor.rowcount
