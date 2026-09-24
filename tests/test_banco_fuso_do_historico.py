"""O filtro de/até e os agregados respeitam o dia do usuário, não o dia UTC.

O banco guarda instantes UTC em texto ISO. A tela manda datas do calendário de
Brasília. Até 24/09/2026 o filtro comparava `2026-09-23 00:00:00` direto com o
texto gravado: o "dia 23" ia das 21h do dia 22 às 21h do dia 23. E janelas e
horas agregadas saíam sem offset, que o navegador lê como hora local -- os
gráficos ficavam 3 h fora do lugar.

Só o PostgreSQL prova isto: a comparação é de texto, a agregação usa
`date_bin`/`date_trunc` sobre `::timestamp`. Por isso esta é uma camada com
banco (ver `banco` no conftest).
"""

from __future__ import annotations

import json

import pytest

from app.database import leituras, zonas

pytestmark = pytest.mark.usefixtures("banco")


@pytest.fixture
def zona(monkeypatch):
    monkeypatch.setenv("TZ", "America/Sao_Paulo")
    return zonas.criar_zona({"nome": "Galpão fuso", "especie": "frangos", "indice": "ITU"})


def _leitura(banco, zona, criado_em: str, valor: float = 70.0) -> None:
    with banco() as conn:
        conn.execute(
            "INSERT INTO leituras (especie, indice, valor, status, entradas, criado_em, zona_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("frangos", "ITU", valor, "conforto", json.dumps({"tbs": 25.0}), criado_em, zona["id"]),
        )


def _datas(resultado) -> list[str]:
    return [item["criado_em"] for item in resultado["leituras"]]


def test_leitura_das_22h30_de_brasilia_pertence_ao_dia_local(banco, zona):
    # 24/09 01:30 UTC = 23/09 22:30 em Brasília.
    _leitura(banco, zona, "2026-09-24T01:30:00+00:00")

    do_dia_23 = leituras.obter_historico_leituras(data_inicio="2026-09-23", data_fim="2026-09-23")
    do_dia_24 = leituras.obter_historico_leituras(data_inicio="2026-09-24", data_fim="2026-09-24")

    assert _datas(do_dia_23) == ["2026-09-24T01:30:00+00:00"]
    assert _datas(do_dia_24) == []


def test_limites_do_dia_local_sao_meia_noite_de_brasilia(banco, zona):
    # 03:00 UTC é a meia-noite local: abre o dia 23 e fecha o dia 22.
    _leitura(banco, zona, "2026-09-23T02:59:59+00:00")
    _leitura(banco, zona, "2026-09-23T03:00:00+00:00")

    do_dia_22 = leituras.obter_historico_leituras(data_inicio="2026-09-22", data_fim="2026-09-22")
    do_dia_23 = leituras.obter_historico_leituras(data_inicio="2026-09-23", data_fim="2026-09-23")

    assert _datas(do_dia_22) == ["2026-09-23T02:59:59+00:00"]
    assert _datas(do_dia_23) == ["2026-09-23T03:00:00+00:00"]


def test_linha_antiga_sem_offset_e_lida_como_utc(banco, zona):
    _leitura(banco, zona, "2026-09-24T01:30:00")

    resultado = leituras.obter_historico_leituras(data_inicio="2026-09-23", data_fim="2026-09-23")

    assert _datas(resultado) == ["2026-09-24T01:30:00+00:00"]


def test_agregados_e_resumos_saem_com_offset_e_no_dia_local(banco, zona):
    for minuto in ("05", "20", "35"):
        _leitura(banco, zona, f"2026-09-24T01:{minuto}:00+00:00", valor=72.0)

    for janela in leituras.janelas_15min_pendentes(zona["id"], "ITU"):
        leituras.agregar_janela_15min(zona["id"], "frangos", "ITU", janela)
    for hora in leituras.horas_pendentes(zona["id"], "ITU"):
        leituras.consolidar_resumo_horario(zona["id"], "frangos", "ITU", hora)

    janelas = [item["janela_inicio"] for item in leituras.obter_agregados_15min(zona["id"])]
    resumos = leituras.obter_resumos_horarios(zona["id"], data_inicio="2026-09-23", data_fim="2026-09-23")

    assert janelas == [
        "2026-09-24T01:00:00+00:00",
        "2026-09-24T01:15:00+00:00",
        "2026-09-24T01:30:00+00:00",
    ]
    assert [item["hora_inicio"] for item in resumos] == ["2026-09-24T01:00:00+00:00"]
    assert resumos[0]["amostras"] == 3
    assert leituras.obter_resumos_horarios(zona["id"], data_inicio="2026-09-24", data_fim="2026-09-24") == []
