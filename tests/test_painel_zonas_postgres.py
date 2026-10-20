"""O painel precisa consumir exatamente os instantes UTC gravados pelo coletor."""

import datetime
import json
from types import SimpleNamespace

import pytest

from app import database as db
from app.database import zonas
from app.models import agora_utc

pytestmark = pytest.mark.usefixtures("banco")


def test_painel_rele_leitura_real_utc_e_estatistica_do_indice_atual():
    zona = db.criar_zona({"nome": "QA", "especie": "frangos", "indice": "ITU"})
    assert db.salvar_leitura("frangos", "ITU", 72.5, "Conforto", {"tbs": 25, "tbu": 20}, zona_id=zona["id"])
    painel = db.obter_painel_zonas()[0]
    assert painel["valor_atual"] == 72.5
    assert painel["percentual_conforto_24h"] == 100
    assert painel["tempo_continuo_status_minutos"] >= 0
    assert painel["tendencias"] == {"15min": None, "30min": None, "60min": None}
    estatisticas = db.obter_estatisticas_zonas()[0]
    assert estatisticas["total_leituras"] == 1
    assert estatisticas["media"] == 72.5
    # Reconfigurar a zona não pode misturar valores de índices diferentes.
    db.atualizar_zona(zona["id"], {"nome": "QA", "especie": "frangos", "indice": "IGNU"})
    assert db.obter_painel_zonas()[0]["valor_atual"] is None
    assert db.obter_estatisticas_zonas()[0]["total_leituras"] == 0


@pytest.mark.parametrize("diferenca,tendencia", [(2, "subindo"), (-2, "descendo"), (0.1, "estavel")])
def test_painel_consolida_tendencia_sem_cruzar_zonas(banco, diferenca, tendencia):
    zona = db.criar_zona({"nome": "Ativa", "especie": "frangos", "indice": "ITU"})
    vazia = db.criar_zona({"nome": "Vazia", "especie": "frangos", "indice": "ITU"})
    agora = agora_utc()
    with banco() as conn:
        for minutos, valor in [(20, 80), (0, 80 + diferenca)]:
            instante = (agora - datetime.timedelta(minutes=minutos)).isoformat()
            conn.execute("INSERT INTO leituras(especie,indice,valor,status,entradas,criado_em,zona_id) VALUES(?,?,?,?,?,?,?)",
                         ("frangos", "ITU", valor, "Perigo", json.dumps({"tbs": 35, "tbu": 25}), instante, zona["id"]))
    paineis = {p["zona_id"]: p for p in db.obter_painel_zonas()}
    assert paineis[zona["id"]]["tendencias"]["15min"] == tendencia
    assert paineis[vazia["id"]]["valor_atual"] is None
    assert paineis[zona["id"]]["valor_atual"] == round(80 + diferenca, 2)


def test_dia_do_painel_usa_fuso_local_na_virada_utc(banco, monkeypatch):
    instante = datetime.datetime(2026, 10, 19, 3, 30, tzinfo=datetime.UTC)

    class Relogio(datetime.datetime):
        @classmethod
        def now(cls, tz=None):
            return instante.astimezone(tz) if tz else instante.replace(tzinfo=None)

    monkeypatch.setenv("TZ", "America/Sao_Paulo")
    monkeypatch.setattr(zonas, "datetime", SimpleNamespace(datetime=Relogio, timedelta=datetime.timedelta))
    zona = db.criar_zona({"nome": "Virada", "especie": "frangos", "indice": "ITU"})
    with banco() as conn:
        for data, status, valor in [("2026-10-19T02:30:00+00:00", "Emergencia", 90),
                                    ("2026-10-19T00:00:00-03:00", "Perigo", 80)]:
            conn.execute("INSERT INTO leituras(especie,indice,valor,status,entradas,criado_em,zona_id) VALUES(?,?,?,?,?,?,?)",
                         ("frangos", "ITU", valor, status, json.dumps({"tbs": 35, "tbu": 25}), data, zona["id"]))
    painel = db.obter_painel_zonas()[0]
    assert painel["nivel_maximo_dia"] == "Perigo"
    assert painel["minutos_emergencia_dia"] == 0
    assert painel["minutos_perigo_dia"] == 30
    assert painel["tempo_continuo_status_minutos"] == 30
