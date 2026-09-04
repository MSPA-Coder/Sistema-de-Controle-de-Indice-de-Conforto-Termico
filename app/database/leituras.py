"""Persistência do histórico de leituras e suas agregações temporais.

Este módulo concentra consultas e gravações das leituras brutas, da janela
recente compartilhada entre processos e dos resumos de 15 minutos e horários.
A fachada :mod:`app.database` continua exportando as mesmas funções públicas.
"""

from __future__ import annotations

import datetime
import json

from app.termico import thermal_indices as ti

from .comum import conexao

INTERVALO_MINIMO_LEITURAS = datetime.timedelta(minutes=1)


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
    *,
    zona_id: int,
) -> bool:
    """Grava uma leitura de zona no histórico.

    O intervalo mínimo é verificado por ``(zona_id, indice)`` para que zonas
    com a mesma espécie e índice não se bloqueiem mutuamente.
    """
    agora = datetime.datetime.now().replace(microsecond=0)
    intervalo_minimo = _intervalo_minimo_leituras(intervalo_minutos)
    with conexao() as conn:
        zona = conn.execute(
            "SELECT especie, indice FROM zonas WHERE id = ?",
            (zona_id,),
        ).fetchone()
        if zona is None:
            # As exceções de zona permanecem expostas pela fachada. O import
            # tardio evita que a extração forme um ciclo na inicialização.
            from .database import ZonaNaoEncontradaError

            raise ZonaNaoEncontradaError(f"Zona {zona_id} nao encontrada.")
        if zona["especie"] != especie or zona["indice"] != indice:
            from .database import ZonaInvalidaError

            raise ZonaInvalidaError(
                "A espécie e o índice da leitura devem corresponder ao cadastro da zona."
            )

        ultima = conn.execute(
            "SELECT criado_em FROM leituras WHERE zona_id = ? AND indice = ? "
            "ORDER BY id DESC LIMIT 1",
            (zona_id, indice),
        ).fetchone()
        if ultima:
            ultima_data = datetime.datetime.fromisoformat(ultima["criado_em"])
            if agora - ultima_data < intervalo_minimo:
                return False

        conn.execute(
            "INSERT INTO leituras (especie, indice, valor, status, entradas, criado_em, zona_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                especie,
                indice,
                valor,
                status,
                json.dumps(entradas),
                agora.isoformat(timespec="seconds"),
                zona_id,
            ),
        )
    return True


def obter_historico_por_zona(zona_id: int, limite: int = 20) -> list[dict]:
    """Devolve o histórico de uma zona, em ordem cronológica."""
    with conexao(escrita=False) as conn:
        linhas = conn.execute(
            "SELECT * FROM leituras WHERE zona_id = ? ORDER BY id DESC LIMIT ?",
            (zona_id, limite),
        ).fetchall()
    dados = [dict(linha) for linha in linhas]
    dados.reverse()
    for item in dados:
        item["entradas"] = json.loads(item["entradas"])
    return dados


def salvar_leitura_recente_zona(
    zona_id: int,
    especie: str,
    indice: str,
    valor: float,
    status: str,
    entradas: dict,
    limite: int = 30,
) -> None:
    """Mantém uma janela curta para gráficos entre processos separados."""
    agora = datetime.datetime.now().replace(microsecond=0).isoformat(timespec="seconds")
    limite = max(1, min(200, int(limite)))
    with conexao() as conn:
        conn.execute(
            """
            INSERT INTO leituras_recentes_zona
                (zona_id, especie, indice, valor, status, entradas, criado_em)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (zona_id, especie, indice, valor, status, json.dumps(entradas), agora),
        )
        conn.execute(
            """
            DELETE FROM leituras_recentes_zona
            WHERE zona_id = ? AND id NOT IN (
                SELECT id FROM leituras_recentes_zona
                WHERE zona_id = ? ORDER BY id DESC LIMIT ?
            )
            """,
            (zona_id, zona_id, limite),
        )


def obter_leituras_recentes_zona(zona_id: int, limite: int = 30) -> list[dict]:
    limite = max(1, min(200, int(limite)))
    with conexao(escrita=False) as conn:
        linhas = conn.execute(
            """
            SELECT * FROM leituras_recentes_zona
            WHERE zona_id = ? ORDER BY id DESC LIMIT ?
            """,
            (zona_id, limite),
        ).fetchall()
    dados = [dict(linha) for linha in reversed(linhas)]
    for item in dados:
        item["entradas"] = json.loads(item["entradas"])
    return dados


def obter_historicos_recentes_zonas(limite: int = 30) -> dict[int, list[dict]]:
    """Devolve a janela recente de todas as zonas em uma só consulta comum.

    Para zonas que ainda não tenham janela recente, busca o fallback do
    histórico persistido para todas elas de uma vez só (uma consulta com
    janela por partição), preservando o contrato cronológico do dashboard
    sem uma consulta por zona.
    """
    limite = max(1, min(200, int(limite)))
    with conexao(escrita=False) as conn:
        zonas = [
            linha["id"] for linha in conn.execute("SELECT id FROM zonas ORDER BY id").fetchall()
        ]
        linhas_recentes = conn.execute(
            "SELECT * FROM leituras_recentes_zona ORDER BY zona_id, id DESC"
        ).fetchall()

        historicos: dict[int, list[dict]] = {zona_id: [] for zona_id in zonas}
        for linha in linhas_recentes:
            zona_id = linha["zona_id"]
            itens = historicos.get(zona_id)
            if itens is not None and len(itens) < limite:
                itens.append(dict(linha))

        zonas_sem_janela = [zona_id for zona_id, itens in historicos.items() if not itens]
        if zonas_sem_janela:
            marcadores = ",".join("?" for _ in zonas_sem_janela)
            linhas_fallback = conn.execute(
                f"""
                SELECT * FROM (
                    SELECT *, ROW_NUMBER() OVER (
                        PARTITION BY zona_id ORDER BY id DESC
                    ) AS _posicao
                    FROM leituras
                    WHERE zona_id IN ({marcadores})
                ) AS janela
                WHERE _posicao <= ?
                ORDER BY zona_id, id DESC
                """,
                (*zonas_sem_janela, limite),
            ).fetchall()
            for linha in linhas_fallback:
                item = dict(linha)
                item.pop("_posicao", None)
                historicos[linha["zona_id"]].append(item)

        for itens in historicos.values():
            itens.reverse()

    for itens in historicos.values():
        for item in itens:
            item["entradas"] = json.loads(item["entradas"])
    return historicos


def obter_historico_leituras(
    limite: int = 30,
    deslocamento: int | None = None,
    zona_id: int | None = None,
    indice: str | None = None,
    status: str | None = None,
    valor_referencia: float | None = None,
    data_inicio: str | None = None,
    data_fim: str | None = None,
) -> dict:
    """Consulta paginada do histórico persistido e seus extremos filtrados."""
    limite = max(1, min(200, int(limite)))
    filtros = []
    parametros: list = []

    if zona_id is not None:
        filtros.append("l.zona_id = ?")
        parametros.append(zona_id)
    if indice:
        filtros.append("l.indice = ?")
        parametros.append(indice)
    if status:
        filtros.append("l.status = ?")
        parametros.append(status)
    if data_inicio:
        filtros.append("l.criado_em >= ?")
        parametros.append(f"{data_inicio} 00:00:00")
    if data_fim:
        fim_exclusivo = (
            datetime.date.fromisoformat(data_fim) + datetime.timedelta(days=1)
        ).isoformat()
        filtros.append("l.criado_em < ?")
        parametros.append(f"{fim_exclusivo} 00:00:00")

    with conexao(escrita=False) as conn:
        valores_encontrados: list[float] = []
        if valor_referencia is not None:
            where_base = ("WHERE " + " AND ".join(filtros)) if filtros else ""
            candidatos = conn.execute(
                f"""
                SELECT DISTINCT l.valor, ABS(l.valor - ?) AS diferenca_absoluta
                FROM leituras l
                {where_base}
                ORDER BY diferenca_absoluta ASC, l.valor ASC
                LIMIT 2
                """,
                [valor_referencia, *parametros],
            ).fetchall()
            valores_encontrados = [float(linha["valor"]) for linha in candidatos]
            if valores_encontrados and abs(valores_encontrados[0] - valor_referencia) <= 1e-9:
                valores_encontrados = valores_encontrados[:1]
            if valores_encontrados:
                placeholders = ", ".join("?" for _ in valores_encontrados)
                filtros.append(f"l.valor IN ({placeholders})")
                parametros.extend(valores_encontrados)

        where = ("WHERE " + " AND ".join(filtros)) if filtros else ""
        total = conn.execute(
            f"SELECT COUNT(*) FROM leituras l {where}",
            parametros,
        ).fetchone()[0]

        linhas_extremos_indices = conn.execute(
            f"""
            SELECT l.indice, MIN(l.valor) AS minimo, MAX(l.valor) AS maximo
            FROM leituras l
            {where}
            GROUP BY l.indice
            """,
            parametros,
        ).fetchall()
        where_entradas = (
            where + " AND jsonb_typeof((l.entradas::jsonb) -> j.key) = 'number'"
            if where
            else "WHERE jsonb_typeof((l.entradas::jsonb) -> j.key) = 'number'"
        )
        sql_extremos_entradas = f"""
            SELECT
                j.key AS campo,
                MIN(CAST(j.value AS DOUBLE PRECISION)) AS minimo,
                MAX(CAST(j.value AS DOUBLE PRECISION)) AS maximo
            FROM leituras l
            CROSS JOIN LATERAL jsonb_each_text(l.entradas::jsonb) AS j(key, value)
            {where_entradas}
            GROUP BY j.key
        """
        linhas_extremos_entradas = conn.execute(
            sql_extremos_entradas,
            parametros,
        ).fetchall()
        minimos_indices = {
            linha["indice"]: float(linha["minimo"])
            for linha in linhas_extremos_indices
            if linha["minimo"] is not None
        }
        maximos_indices = {
            linha["indice"]: float(linha["maximo"])
            for linha in linhas_extremos_indices
            if linha["maximo"] is not None
        }
        minimos_entradas = {
            linha["campo"]: float(linha["minimo"])
            for linha in linhas_extremos_entradas
            if linha["minimo"] is not None
        }
        maximos_entradas = {
            linha["campo"]: float(linha["maximo"])
            for linha in linhas_extremos_entradas
            if linha["maximo"] is not None
        }

        if deslocamento is None:
            deslocamento_calculado = max(0, total - limite)
        else:
            deslocamento_calculado = max(0, min(int(deslocamento), max(0, total - limite)))
        linhas = conn.execute(
            f"""
            SELECT l.*, z.nome AS zona_nome
            FROM leituras l
            LEFT JOIN zonas z ON z.id = l.zona_id
            {where}
            ORDER BY l.id ASC
            LIMIT ? OFFSET ?
            """,
            [*parametros, limite, deslocamento_calculado],
        ).fetchall()

    leituras = [dict(linha) for linha in linhas]
    for item in leituras:
        item["entradas"] = json.loads(item["entradas"])
    return {
        "leituras": leituras,
        "total": total,
        "limite": limite,
        "deslocamento": deslocamento_calculado,
        "valor_referencia": valor_referencia,
        "valores_encontrados": valores_encontrados,
        "minimos": {
            "indices": minimos_indices,
            "entradas": minimos_entradas,
        },
        "maximos": {
            "indices": maximos_indices,
            "entradas": maximos_entradas,
        },
    }


def limpar_historico() -> None:
    with conexao() as conn:
        conn.execute("DELETE FROM leituras")
        conn.execute("DELETE FROM leituras_recentes_zona")
        conn.execute("DELETE FROM agregados_15min")
        conn.execute("DELETE FROM resumos_horarios")


# A lógica de quando consolidar pertence a ``agregacao.py``; este agregado
# fornece apenas as consultas e gravações idempotentes.
def _formatar_janela(momento: datetime.datetime, minutos: int) -> str:
    """Arredonda ``momento`` para o início do bucket de ``minutos``."""
    bucket = (momento.minute // minutos) * minutos
    return momento.replace(minute=bucket, second=0, microsecond=0).isoformat(timespec="seconds")


def janelas_15min_pendentes(zona_id: int, indice: str) -> list[str]:
    """Devolve os inícios de janelas fechadas ainda não consolidadas."""
    agora = datetime.datetime.now().replace(microsecond=0)
    janela_atual_aberta = _formatar_janela(agora, 15)
    with conexao(escrita=False) as conn:
        linhas = conn.execute(
            """
            SELECT DISTINCT
                to_char(
                    date_bin(
                        INTERVAL '15 minutes',
                        l.criado_em::timestamp,
                        TIMESTAMP '2000-01-01'
                    ),
                    'YYYY-MM-DD"T"HH24:MI:SS'
                ) AS janela_inicio
            FROM leituras l
            WHERE l.zona_id = ?
              AND l.indice = ?
              AND l.criado_em < ?
              AND NOT EXISTS (
                  SELECT 1
                  FROM agregados_15min a
                  WHERE a.zona_id = l.zona_id
                    AND a.indice = l.indice
                    AND a.janela_inicio = to_char(
                        date_bin(
                            INTERVAL '15 minutes',
                            l.criado_em::timestamp,
                            TIMESTAMP '2000-01-01'
                        ),
                        'YYYY-MM-DD"T"HH24:MI:SS'
                    )
              )
            ORDER BY janela_inicio
            """,
            (zona_id, indice, janela_atual_aberta),
        ).fetchall()
    return [linha["janela_inicio"] for linha in linhas]


def agregar_janela_15min(
    zona_id: int, especie: str, indice: str, janela_inicio: str
) -> dict | None:
    """Consolida uma janela de 15 minutos por UPSERT, se tiver leituras."""
    janela_fim = (
        datetime.datetime.fromisoformat(janela_inicio) + datetime.timedelta(minutes=15)
    ).isoformat(timespec="seconds")
    with conexao() as conn:
        linhas = conn.execute(
            """
            SELECT valor, entradas FROM leituras
            WHERE zona_id = ? AND indice = ? AND criado_em >= ? AND criado_em < ?
            """,
            (zona_id, indice, janela_inicio, janela_fim),
        ).fetchall()
        if not linhas:
            return None

        valores = [linha["valor"] for linha in linhas]
        entradas_por_campo: dict[str, list[float]] = {}
        for linha in linhas:
            for campo, valor in json.loads(linha["entradas"]).items():
                if isinstance(valor, (int, float)):
                    entradas_por_campo.setdefault(campo, []).append(float(valor))
        entradas_medias = {
            campo: round(sum(valores_campo) / len(valores_campo), 2)
            for campo, valores_campo in entradas_por_campo.items()
        }

        agora = datetime.datetime.now().replace(microsecond=0).isoformat(timespec="seconds")
        registro = {
            "zona_id": zona_id,
            "especie": especie,
            "indice": indice,
            "janela_inicio": janela_inicio,
            "amostras": len(valores),
            "valor_medio": round(sum(valores) / len(valores), 2),
            "valor_minimo": round(min(valores), 2),
            "valor_maximo": round(max(valores), 2),
            "entradas_medias": entradas_medias,
        }
        conn.execute(
            """
            INSERT INTO agregados_15min
                (zona_id, especie, indice, janela_inicio, amostras,
                 valor_medio, valor_minimo, valor_maximo, entradas_medias, criado_em)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (zona_id, indice, janela_inicio) DO UPDATE SET
                amostras = excluded.amostras,
                valor_medio = excluded.valor_medio,
                valor_minimo = excluded.valor_minimo,
                valor_maximo = excluded.valor_maximo,
                entradas_medias = excluded.entradas_medias,
                criado_em = excluded.criado_em
            """,
            (
                zona_id,
                especie,
                indice,
                janela_inicio,
                registro["amostras"],
                registro["valor_medio"],
                registro["valor_minimo"],
                registro["valor_maximo"],
                json.dumps(entradas_medias),
                agora,
            ),
        )
    return registro


def horas_pendentes(zona_id: int, indice: str) -> list[str]:
    """Devolve as horas fechadas ainda não resumidas."""
    agora = datetime.datetime.now().replace(microsecond=0)
    hora_atual_aberta = agora.replace(minute=0, second=0, microsecond=0).isoformat(
        timespec="seconds"
    )
    with conexao(escrita=False) as conn:
        linhas = conn.execute(
            """
            SELECT DISTINCT
                to_char(
                    date_trunc('hour', a.janela_inicio::timestamp),
                    'YYYY-MM-DD"T"HH24:MI:SS'
                ) AS hora_inicio
            FROM agregados_15min a
            WHERE a.zona_id = ?
              AND a.indice = ?
              AND a.janela_inicio < ?
              AND NOT EXISTS (
                  SELECT 1
                  FROM resumos_horarios r
                  WHERE r.zona_id = a.zona_id
                    AND r.indice = a.indice
                    AND r.hora_inicio = to_char(
                        date_trunc('hour', a.janela_inicio::timestamp),
                        'YYYY-MM-DD"T"HH24:MI:SS'
                    )
              )
            ORDER BY hora_inicio
            """,
            (zona_id, indice, hora_atual_aberta),
        ).fetchall()
    return [linha["hora_inicio"] for linha in linhas]


def consolidar_resumo_horario(
    zona_id: int, especie: str, indice: str, hora_inicio: str
) -> dict | None:
    """Consolida as leituras brutas de uma hora por UPSERT."""
    hora_fim = (
        datetime.datetime.fromisoformat(hora_inicio) + datetime.timedelta(hours=1)
    ).isoformat(timespec="seconds")
    with conexao() as conn:
        linhas = conn.execute(
            """
            SELECT valor, status FROM leituras
            WHERE zona_id = ? AND indice = ? AND criado_em >= ? AND criado_em < ?
            """,
            (zona_id, indice, hora_inicio, hora_fim),
        ).fetchall()
        if not linhas:
            return None

        valores = [linha["valor"] for linha in linhas]
        valor_medio = round(sum(valores) / len(valores), 2)
        status_da_media = ti.classificar_status(valor_medio, especie, indice)

        total = len(linhas)
        contagem = dict.fromkeys(ti.STATUS_ORDEM, 0)
        for linha in linhas:
            contagem[linha["status"]] = contagem.get(linha["status"], 0) + 1
        percentuais = {
            status: round((contagem.get(status, 0) / total) * 100, 1) for status in ti.STATUS_ORDEM
        }

        agora = datetime.datetime.now().replace(microsecond=0).isoformat(timespec="seconds")
        conn.execute(
            """
            INSERT INTO resumos_horarios
                (zona_id, especie, indice, hora_inicio, amostras, valor_medio,
                 valor_minimo, valor_maximo, status_da_media,
                 pct_conforto, pct_alerta, pct_perigo, pct_emergencia, criado_em)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (zona_id, indice, hora_inicio) DO UPDATE SET
                amostras = excluded.amostras,
                valor_medio = excluded.valor_medio,
                valor_minimo = excluded.valor_minimo,
                valor_maximo = excluded.valor_maximo,
                status_da_media = excluded.status_da_media,
                pct_conforto = excluded.pct_conforto,
                pct_alerta = excluded.pct_alerta,
                pct_perigo = excluded.pct_perigo,
                pct_emergencia = excluded.pct_emergencia,
                criado_em = excluded.criado_em
            """,
            (
                zona_id,
                especie,
                indice,
                hora_inicio,
                total,
                valor_medio,
                round(min(valores), 2),
                round(max(valores), 2),
                status_da_media,
                percentuais["Conforto"],
                percentuais["Alerta"],
                percentuais["Perigo"],
                percentuais["Emergência"],
                agora,
            ),
        )
    return {
        "zona_id": zona_id,
        "indice": indice,
        "hora_inicio": hora_inicio,
        "amostras": total,
        "valor_medio": valor_medio,
        "status_da_media": status_da_media,
        "percentuais": percentuais,
    }


def obter_agregados_15min(zona_id: int, limite: int = 96) -> list[dict]:
    """Últimas janelas consolidadas de uma zona, em ordem cronológica."""
    limite = max(1, min(2000, int(limite)))
    with conexao(escrita=False) as conn:
        linhas = conn.execute(
            """
            SELECT * FROM agregados_15min WHERE zona_id = ?
            ORDER BY janela_inicio DESC LIMIT ?
            """,
            (zona_id, limite),
        ).fetchall()
    dados = [dict(linha) for linha in reversed(linhas)]
    for item in dados:
        item["entradas_medias"] = json.loads(item["entradas_medias"])
    return dados


def obter_resumos_horarios(
    zona_id: int,
    limite: int = 168,
    data_inicio: str | None = None,
    data_fim: str | None = None,
) -> list[dict]:
    """Últimos resumos horários de uma zona, com filtro de data opcional."""
    limite = max(1, min(5000, int(limite)))
    filtros = ["zona_id = ?"]
    parametros: list = [zona_id]
    if data_inicio:
        filtros.append("hora_inicio >= ?")
        parametros.append(f"{data_inicio} 00:00:00")
    if data_fim:
        fim_exclusivo = (
            datetime.date.fromisoformat(data_fim) + datetime.timedelta(days=1)
        ).isoformat()
        filtros.append("hora_inicio < ?")
        parametros.append(f"{fim_exclusivo} 00:00:00")
    where = "WHERE " + " AND ".join(filtros)
    with conexao(escrita=False) as conn:
        linhas = conn.execute(
            f"SELECT * FROM resumos_horarios {where} ORDER BY hora_inicio DESC LIMIT ?",
            [*parametros, limite],
        ).fetchall()
    return [dict(linha) for linha in reversed(linhas)]


def contar_leituras() -> int:
    """Utilitário de diagnóstico: total de linhas gravadas na tabela."""
    with conexao(escrita=False) as conn:
        total = conn.execute("SELECT COUNT(*) FROM leituras").fetchone()[0]
    return int(total)
