# -*- coding: utf-8 -*-
"""
database.py
============
Persistencia simples em SQLite (biblioteca padrao do Python, sem
dependencias extras) do historico de leituras, para alimentar os graficos
de "ultimos 20 indices calculados" descritos na secao 3.4.1 (Area 04) da
dissertacao.

NOTA DE CORRECAO: a versao anterior deste modulo usava
`with _lock, sqlite3.connect(...) as conn:` para cada operacao. O
`sqlite3.Connection` como context manager apenas comita/desfaz a transacao
ao sair do bloco -- ele NAO fecha a conexao sozinho (isso e documentado no
proprio modulo sqlite3 da biblioteca padrao). Como resultado, cada chamada
abria uma conexao nova que nunca era fechada, vazando conexoes/descritores
de arquivo ao longo do tempo (principalmente com o modo automatico, que
calcula a cada 1s). Agora todas as operacoes passam pelo gerenciador de
contexto `_conexao()` abaixo, que garante `close()` mesmo se ocorrer erro.
"""

from __future__ import annotations

import datetime
import json
import os
import sqlite3
import threading
from contextlib import contextmanager
from typing import Iterator

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(PROJECT_ROOT, "historico.db")

_lock = threading.Lock()
INTERVALO_MINIMO_LEITURAS = datetime.timedelta(minutes=1)

CONFIGURACOES_PADRAO = {
    "coletarDados": False,
    "habilitarSons": False,
    "enviarEmails": False,
    "habilitarEquipamentos": False,
    "emailDestino": "produtor@fazenda.com.br",
    "modoAutomatico": False,
    "intervaloLeituraSegundos": 1,
    "intervaloGravacaoMinutos": 1,
    "modoPontoOrvalho": "medido",
    "modoUmidadeRelativa": "calculado",
    "altitudeMetros": 0,
    "limiteUmidadeNebulizador": 70,
}


@contextmanager
def _conexao() -> Iterator[sqlite3.Connection]:
    """Abre uma conexao SQLite, garante commit em caso de sucesso (ou
    rollback em caso de excecao) e SEMPRE fecha a conexao ao final."""
    with _lock:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def iniciar_banco() -> None:
    with _conexao() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS leituras (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                especie TEXT NOT NULL,
                indice TEXT NOT NULL,
                valor REAL NOT NULL,
                status TEXT NOT NULL,
                entradas TEXT NOT NULL,
                criado_em TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS configuracoes (
                chave TEXT PRIMARY KEY,
                valor TEXT NOT NULL,
                atualizado_em TEXT NOT NULL
            )
            """
        )


def _intervalo_minimo_leituras(intervalo_minutos: float | int | str | None) -> datetime.timedelta:
    if intervalo_minutos is None:
        return INTERVALO_MINIMO_LEITURAS

    try:
        minutos = float(intervalo_minutos)
    except (TypeError, ValueError):
        return INTERVALO_MINIMO_LEITURAS

    return datetime.timedelta(minutes=max(0, minutos))


def salvar_leitura(
    especie: str,
    indice: str,
    valor: float,
    status: str,
    entradas: dict,
    intervalo_minutos: float | int | str | None = None,
) -> bool:
    agora = datetime.datetime.now().replace(microsecond=0)
    intervalo_minimo = _intervalo_minimo_leituras(intervalo_minutos)
    with _conexao() as conn:
        ultima = conn.execute(
            "SELECT criado_em FROM leituras WHERE especie = ? AND indice = ? "
            "ORDER BY id DESC LIMIT 1",
            (especie, indice),
        ).fetchone()
        if ultima:
            ultima_data = datetime.datetime.fromisoformat(ultima["criado_em"])
            if agora - ultima_data < intervalo_minimo:
                return False

        conn.execute(
            "INSERT INTO leituras (especie, indice, valor, status, entradas, criado_em) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                especie,
                indice,
                valor,
                status,
                json.dumps(entradas),
                agora.isoformat(timespec="seconds"),
            ),
        )
    return True


def obter_historico(especie: str, indice: str, limite: int = 20) -> list[dict]:
    with _conexao() as conn:
        linhas = conn.execute(
            "SELECT * FROM leituras WHERE especie = ? AND indice = ? "
            "ORDER BY id DESC LIMIT ?",
            (especie, indice, limite),
        ).fetchall()
    dados = [dict(linha) for linha in linhas]
    dados.reverse()  # ordem cronologica (mais antigo -> mais recente) para os graficos
    for item in dados:
        item["entradas"] = json.loads(item["entradas"])
    return dados


def limpar_historico(especie: str | None = None, indice: str | None = None) -> None:
    with _conexao() as conn:
        if especie and indice:
            conn.execute(
                "DELETE FROM leituras WHERE especie = ? AND indice = ?", (especie, indice)
            )
        elif especie:
            conn.execute("DELETE FROM leituras WHERE especie = ?", (especie,))
        else:
            conn.execute("DELETE FROM leituras")


def contar_leituras() -> int:
    """Utilitario de diagnostico: total de linhas gravadas na tabela."""
    with _conexao() as conn:
        (total,) = conn.execute("SELECT COUNT(*) FROM leituras").fetchone()
    return total


def obter_configuracoes() -> dict:
    with _conexao() as conn:
        linhas = conn.execute("SELECT chave, valor FROM configuracoes").fetchall()

    configuracoes = dict(CONFIGURACOES_PADRAO)
    for linha in linhas:
        try:
            configuracoes[linha["chave"]] = json.loads(linha["valor"])
        except json.JSONDecodeError:
            configuracoes[linha["chave"]] = linha["valor"]
    return configuracoes


def salvar_configuracoes(configuracoes: dict) -> dict:
    salvas = dict(CONFIGURACOES_PADRAO)
    salvas.update(
        {
            chave: valor
            for chave, valor in (configuracoes or {}).items()
            if chave in CONFIGURACOES_PADRAO
        }
    )
    agora = datetime.datetime.now().replace(microsecond=0).isoformat(timespec="seconds")
    with _conexao() as conn:
        conn.executemany(
            """
            INSERT INTO configuracoes (chave, valor, atualizado_em)
            VALUES (?, ?, ?)
            ON CONFLICT(chave) DO UPDATE SET
                valor = excluded.valor,
                atualizado_em = excluded.atualizado_em
            """,
            [
                (chave, json.dumps(valor), agora)
                for chave, valor in salvas.items()
            ],
        )
    return salvas
