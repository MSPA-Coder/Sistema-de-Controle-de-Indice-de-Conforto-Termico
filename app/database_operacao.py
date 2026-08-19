"""Persistência de manutenção e observabilidade operacional.

As funções são usadas pela fachada :mod:`app.database`, que preserva o
contrato público. O diretório de instância é recebido explicitamente pelo
backup porque os testes podem substituí-lo temporariamente na fachada.
"""

from __future__ import annotations

import datetime
import json
import os
import subprocess
from typing import TYPE_CHECKING

from . import db_backend
from .database_comum import conexao
from .database_configuracoes import obter_configuracoes

if TYPE_CHECKING:
    from collections.abc import Callable
    from typing import Any


def criar_backup_banco(
    instance_dir: str,
    *,
    obter_url: Callable[[], str] = db_backend.database_url,
    executar: Callable[..., Any] = subprocess.run,
    obter_tamanho: Callable[[str], int] = os.path.getsize,
) -> dict:
    """Cria um dump PostgreSQL consistente no diretório de instância."""
    from sqlalchemy.engine import make_url

    os.makedirs(instance_dir, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    caminho_backup = os.path.join(instance_dir, f"conforto_termico_backup_{timestamp}.dump")
    url = make_url(obter_url())
    ambiente_pg_dump = dict(os.environ)
    if url.password:
        ambiente_pg_dump["PGPASSWORD"] = url.password
    executar(
        [
            "pg_dump",
            "--format=custom",
            "--no-owner",
            "--no-privileges",
            f"--file={caminho_backup}",
            f"--host={url.host or 'postgres'}",
            f"--port={url.port or 5432}",
            f"--username={url.username or 'conforto'}",
            f"--dbname={url.database or 'conforto_termico'}",
        ],
        check=True,
        env=ambiente_pg_dump,
    )
    return {
        "arquivo": os.path.basename(caminho_backup),
        "caminho": caminho_backup,
        "tamanho_bytes": obter_tamanho(caminho_backup),
    }


def salvar_status_coletor(
    status: str,
    *,
    iniciado_em: str | None = None,
    ultimo_ciclo_em: str | None = None,
    proximo_ciclo_em: str | None = None,
    erro: str | None = None,
) -> dict:
    agora = datetime.datetime.now().replace(microsecond=0).isoformat(timespec="seconds")
    with conexao() as conn:
        atual = conn.execute("SELECT * FROM estado_coletor WHERE id = 1").fetchone()
        inicio = iniciado_em or (atual["iniciado_em"] if atual else None) or agora
        ultimo = ultimo_ciclo_em or (atual["ultimo_ciclo_em"] if atual else None)
        conn.execute(
            """
            INSERT INTO estado_coletor
                (id, status, iniciado_em, heartbeat_em, ultimo_ciclo_em, proximo_ciclo_em, erro)
            VALUES (1, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                status = excluded.status,
                iniciado_em = excluded.iniciado_em,
                heartbeat_em = excluded.heartbeat_em,
                ultimo_ciclo_em = excluded.ultimo_ciclo_em,
                proximo_ciclo_em = excluded.proximo_ciclo_em,
                erro = excluded.erro
            """,
            (status, inicio, agora, ultimo, proximo_ciclo_em, erro),
        )
    return {
        "status": status,
        "iniciado_em": inicio,
        "heartbeat_em": agora,
        "ultimo_ciclo_em": ultimo,
        "proximo_ciclo_em": proximo_ciclo_em,
        "erro": erro,
    }


def obter_status_coletor() -> dict:
    with conexao(escrita=False) as conn:
        linha = conn.execute("SELECT * FROM estado_coletor WHERE id = 1").fetchone()
    if linha is None:
        return {
            "status": "offline",
            "online": False,
            "iniciado_em": None,
            "heartbeat_em": None,
            "ultimo_ciclo_em": None,
            "proximo_ciclo_em": None,
            "erro": None,
        }

    dados = dict(linha)
    heartbeat = datetime.datetime.fromisoformat(dados["heartbeat_em"])
    intervalo = float(obter_configuracoes().get("intervaloLeituraSegundos") or 1)
    limite = datetime.timedelta(seconds=max(10.0, intervalo * 3))
    # O coletor pode entrar em repouso quando nao ha zona automatica. Nesse
    # caso, `proximo_ciclo_em` e a fonte de verdade para o periodo esperado
    # sem heartbeat; continuar usando somente o intervalo de leitura faria a
    # interface diagnosticar incorretamente um coletor saudavel como parado.
    proximo_ciclo = dados.get("proximo_ciclo_em")
    if proximo_ciclo:
        try:
            espera_anunciada = datetime.datetime.fromisoformat(proximo_ciclo) - heartbeat
            if espera_anunciada > datetime.timedelta(0):
                limite = max(limite, espera_anunciada + datetime.timedelta(seconds=10))
        except (TypeError, ValueError):
            pass
    dados["online"] = dados["status"] == "online" and datetime.datetime.now() - heartbeat <= limite
    if not dados["online"] and dados["status"] == "online":
        dados["status"] = "sem_heartbeat"
    dados.pop("id", None)
    return dados


def registrar_evento_operacao(
    tipo: str, acao: str, *, zona_id: int | None = None, detalhes: dict | None = None
) -> None:
    agora = datetime.datetime.now().replace(microsecond=0).isoformat(timespec="seconds")
    with conexao() as conn:
        conn.execute(
            "INSERT INTO eventos_operacao (zona_id, tipo, acao, detalhes, criado_em) "
            "VALUES (?, ?, ?, ?, ?)",
            (zona_id, tipo, acao, json.dumps(detalhes or {}), agora),
        )


def listar_eventos_operacao(zona_id: int | None = None, limite: int = 30) -> list[dict]:
    filtro = "WHERE zona_id = ?" if zona_id is not None else ""
    parametros = (zona_id, limite) if zona_id is not None else (limite,)
    with conexao(escrita=False) as conn:
        linhas = conn.execute(
            f"SELECT * FROM eventos_operacao {filtro} ORDER BY id DESC LIMIT ?",
            parametros,
        ).fetchall()
    resultado = []
    for linha in linhas:
        item = dict(linha)
        item["detalhes"] = json.loads(item["detalhes"])
        resultado.append(item)
    return resultado
