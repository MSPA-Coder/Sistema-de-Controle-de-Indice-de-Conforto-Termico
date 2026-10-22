"""Recalcula o IGNU gravado com a fórmula anterior ao ADR 009.

Até 15/09/2026 o IGNU era ``0,6·Tgn + 0,36·Tpo + 41,5``; desde o ADR 009 é
``Tgn + 0,36·Tpo + 41,5`` (Buffington et al., 1981). Valor e status já gravados
não se corrigem sozinhos, e nada na linha diz qual fórmula a gerou. Como as
entradas (``tgn`` e ``tpo``) ficam guardadas junto de cada linha, o valor e o
status saem delas de novo, sem gerar a série outra vez.

Atualiza ``historico.leituras``, ``historico.leituras_recentes_zona`` e
``dados_entrada.medicoes`` e refaz os agregados de 15 minutos e os resumos
horários das zonas afetadas. É idempotente: depois de aplicado, uma segunda
execução não encontra nada a mudar.

    python -m scripts.recalcular_ignu            # só mostra o que mudaria
    python -m scripts.recalcular_ignu --aplicar  # grava

Em contêiner (o host não tem as dependências):

    docker compose --env-file .env.docker exec ict python -m scripts.recalcular_ignu

Faça backup antes de ``--aplicar`` numa base com dados que importam.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app import database as db
from app.nucleo import db_backend
from app.termico import agregacao
from app.termico import thermal_indices as ti

INDICE = "IGNU"
TOLERANCIA = 1e-9

# (esquema, tabela, coluna do valor, coluna do status, coluna das entradas, coluna da zona)
ALVOS = (
    ("historico", "leituras", "valor", "status", "entradas", "zona_id"),
    ("historico", "leituras_recentes_zona", "valor", "status", "entradas", "zona_id"),
    ("dados_entrada", "medicoes", "valor_indice", "status_termico", "entradas_indice", "zona_id"),
)


def _entradas(bruto) -> dict:
    return json.loads(bruto) if isinstance(bruto, (str, bytes)) else dict(bruto)


def _novo_valor(antigo: float, entradas: dict) -> float:
    valor = ti.calcular_ignu(float(entradas["tgn"]), float(entradas["tpo"]))
    # Preserva a precisão com que a linha foi gravada: 2 casas (coletor) ou 4 (gerador).
    return round(valor, 2 if abs(round(antigo, 2) - antigo) <= TOLERANCIA else 4)


def _recalcular_tabela(esquema, tabela, col_valor, col_status, col_entradas, col_zona, aplicar):
    """Devolve (linhas lidas, linhas a mudar, mudanças de status, zonas afetadas)."""
    lidas = 0
    mudancas: list[tuple[float, str, int]] = []
    transicoes: Counter = Counter()
    zonas: set[int] = set()
    conn = db_backend.abrir_conexao_postgres(esquema)
    try:
        linhas = conn.execute(
            f"SELECT id, {col_zona} AS zona_id, especie, {col_valor} AS valor, "
            f"{col_status} AS status, {col_entradas} AS entradas "
            f"FROM {tabela} WHERE indice = ? ORDER BY id",
            (INDICE,),
        ).fetchall()
        for linha in linhas:
            lidas += 1
            _id, zona_id = linha["id"], linha["zona_id"]
            especie, valor, status, bruto = (
                linha["especie"],
                linha["valor"],
                linha["status"],
                linha["entradas"],
            )
            entradas = _entradas(bruto)
            if "tgn" not in entradas or "tpo" not in entradas:
                continue
            novo = _novo_valor(float(valor), entradas)
            novo_status = ti.classificar_status(novo, especie, INDICE)
            if abs(novo - float(valor)) <= TOLERANCIA and novo_status == status:
                continue
            mudancas.append((novo, novo_status, _id))
            if novo_status != status:
                transicoes[(status, novo_status)] += 1
            if zona_id is not None:
                zonas.add(int(zona_id))
        if aplicar and mudancas:
            conn.executemany(
                f"UPDATE {tabela} SET {col_valor} = ?, {col_status} = ? WHERE id = ?",
                mudancas,
            )
            conn.commit()
    finally:
        conn.close()
    return lidas, len(mudancas), transicoes, zonas


def _refazer_agregados(zonas: set[int]) -> None:
    # Só as zonas que ainda usam o IGNU: para as outras não há como reconstruir,
    # e apagar deixaria o agregado antigo sem substituto.
    zonas_ignu = {}
    for zona_id in sorted(zonas):
        zona = db.obter_zona(zona_id)
        if zona is not None and zona["indice"] == INDICE:
            zonas_ignu[zona_id] = zona
    conn = db_backend.abrir_conexao_postgres("historico")
    try:
        for zona_id in sorted(zonas_ignu):
            conn.execute(
                "DELETE FROM agregados_15min WHERE zona_id = ? AND indice = ?", (zona_id, INDICE)
            )
            conn.execute(
                "DELETE FROM resumos_horarios WHERE zona_id = ? AND indice = ?", (zona_id, INDICE)
            )
        conn.commit()
    finally:
        conn.close()
    for zona_id, zona in sorted(zonas_ignu.items()):
        # `executar_para_zona` processa até 500 janelas por chamada.
        while True:
            resultado = agregacao.executar_para_zona(zona)
            if not resultado["janelas_15min_consolidadas"] and not resultado["horas_consolidadas"]:
                break
        print(f"  zona {zona_id}: agregados de 15 min e resumos horários refeitos")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--aplicar", action="store_true", help="grava (padrão: só mostra)")
    argumentos = parser.parse_args(argv)

    zonas_afetadas: set[int] = set()
    for alvo in ALVOS:
        esquema, tabela = alvo[0], alvo[1]
        lidas, mudar, transicoes, zonas = _recalcular_tabela(*alvo, aplicar=argumentos.aplicar)
        verbo = "atualizadas" if argumentos.aplicar else "a atualizar"
        print(f"{esquema}.{tabela}: {lidas} linhas de {INDICE}, {mudar} {verbo}")
        for (de, para), total in sorted(transicoes.items()):
            print(f"    {de} -> {para}: {total}")
        if tabela in {"leituras", "leituras_recentes_zona"}:
            zonas_afetadas |= zonas

    if argumentos.aplicar and zonas_afetadas:
        _refazer_agregados(zonas_afetadas)
    if not argumentos.aplicar:
        print("Nada foi gravado. Use --aplicar para gravar.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
