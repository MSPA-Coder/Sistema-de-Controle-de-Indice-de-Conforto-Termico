"""Persistência de manutenção e observabilidade operacional."""

from __future__ import annotations

import datetime
import json
from typing import TYPE_CHECKING

from app.models import agora_utc, como_local_ingenuo, parsear_timestamp

from .comum import conexao
from .configuracoes import obter_configuracoes

if TYPE_CHECKING:
    from collections.abc import Sequence


def salvar_status_coletor(
    status: str,
    *,
    iniciado_em: datetime.datetime | None = None,
    ultimo_ciclo_em: datetime.datetime | None = None,
    proximo_ciclo_em: datetime.datetime | None = None,
    erro: str | None = None,
) -> dict:
    agora = agora_utc()
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
        "iniciado_em": como_local_ingenuo(inicio),
        "heartbeat_em": como_local_ingenuo(agora),
        "ultimo_ciclo_em": como_local_ingenuo(ultimo),
        "proximo_ciclo_em": como_local_ingenuo(proximo_ciclo_em),
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
    heartbeat = parsear_timestamp(dados["heartbeat_em"])
    intervalo = float(obter_configuracoes().get("intervaloLeituraSegundos") or 1)
    limite = datetime.timedelta(seconds=max(10.0, intervalo * 3))
    # O coletor pode entrar em repouso quando nao ha zona automatica. Nesse
    # caso, `proximo_ciclo_em` e a fonte de verdade para o periodo esperado
    # sem heartbeat; continuar usando somente o intervalo de leitura faria a
    # interface diagnosticar incorretamente um coletor saudavel como parado.
    proximo_ciclo = dados.get("proximo_ciclo_em")
    if proximo_ciclo:
        try:
            espera_anunciada = parsear_timestamp(proximo_ciclo) - heartbeat
            if espera_anunciada > datetime.timedelta(0):
                limite = max(limite, espera_anunciada + datetime.timedelta(seconds=10))
        except (TypeError, ValueError):
            pass
    dados["online"] = dados["status"] == "online" and agora_utc() - heartbeat <= limite
    for campo in ("iniciado_em", "heartbeat_em", "ultimo_ciclo_em", "proximo_ciclo_em"):
        dados[campo] = como_local_ingenuo(dados[campo])
    if not dados["online"] and dados["status"] == "online":
        dados["status"] = "sem_heartbeat"
    dados.pop("id", None)
    return dados


def registrar_evento_operacao(
    tipo: str, acao: str, *, zona_id: int | None = None, detalhes: dict | None = None
) -> None:
    agora = agora_utc()
    with conexao() as conn:
        conn.execute(
            "INSERT INTO eventos_operacao (zona_id, tipo, acao, detalhes, criado_em) "
            "VALUES (?, ?, ?, ?, ?)",
            (zona_id, tipo, acao, json.dumps(detalhes or {}), agora),
        )


def listar_eventos_operacao(
    zona_id: int | None = None,
    limite: int = 30,
    zona_ids: Sequence[int] | None = None,
) -> list[dict]:
    """Eventos recentes; `zona_ids` restringe as zonas que a conta pode ver."""
    condicoes: list[str] = []
    parametros_filtro: list = []
    if zona_id is not None:
        condicoes.append("zona_id = ?")
        parametros_filtro.append(zona_id)
    if zona_ids is not None:
        if zona_ids:
            condicoes.append(f"zona_id IN ({', '.join('?' for _ in zona_ids)})")
            parametros_filtro.extend(zona_ids)
        else:
            condicoes.append("FALSE")
    filtro = ("WHERE " + " AND ".join(condicoes)) if condicoes else ""
    parametros = (*parametros_filtro, limite)
    with conexao(escrita=False) as conn:
        linhas = conn.execute(
            f"SELECT * FROM eventos_operacao {filtro} ORDER BY id DESC LIMIT ?",
            parametros,
        ).fetchall()
    resultado = []
    for linha in linhas:
        item = dict(linha)
        item["criado_em"] = como_local_ingenuo(item["criado_em"])
        item["detalhes"] = json.loads(item["detalhes"])
        resultado.append(item)
    return resultado
