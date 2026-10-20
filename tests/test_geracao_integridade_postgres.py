"""Geração completa, proveniência, publicação idempotente e consolidação real."""

import copy
import datetime as dt
import io
import json
from urllib.parse import parse_qs, urlsplit

import pytest

from app import database as db
from app.dados_entrada import db as dados
from app.dados_entrada import gerador_dados as g
from app.dados_entrada.cidades import CIDADES_POR_ESPECIE
from app.termico import agregacao


@pytest.fixture
def ambiente(banco, monkeypatch):
    with dados._conexao() as conn:
        conn.execute("TRUNCATE execucoes, configuracoes_zona, cache_clima RESTART IDENTITY CASCADE")
    inicio = dt.datetime(2025, 12, 30, tzinfo=dt.UTC)
    tempos = [(inicio + dt.timedelta(hours=i)).isoformat() for i in range(144)]
    valores = {"temperature_2m": 25.0, "relative_humidity_2m": 60.0, "wind_speed_10m": 2.0,
               "precipitation": 1.0, "surface_pressure": 1000.0, "shortwave_radiation": 200.0, "cloud_cover": 50.0}
    controle = {"alterar": None, "falhar_segunda": False, "chamadas": []}

    def responder(requisicao, **kwargs):
        consulta = parse_qs(urlsplit(requisicao.full_url).query)
        controle["chamadas"].append(consulta)
        payload = {"hourly": {"time": tempos, **{nome: [valor] * len(tempos) for nome, valor in valores.items()}}}
        if controle["falhar_segunda"] and float(consulta["latitude"][0]) == -21:
            payload = {"error": True, "reason": "fonte sintética indisponível"}
        elif controle["alterar"]:
            controle["alterar"](payload)
        return io.BytesIO(json.dumps(payload).encode())

    monkeypatch.setattr(g.urllib.request, "urlopen", responder)
    yield controle
    with dados._conexao() as conn:
        conn.execute("TRUNCATE execucoes, configuracoes_zona, cache_clima RESTART IDENTITY CASCADE")


def configurar(especie="frangos", latitude=-20):
    z = db.criar_zona({"nome": "Pesquisa " + especie, "especie": especie, "indice": "ITU"})
    cidade = CIDADES_POR_ESPECIE[especie][0]
    config = {"zona_id": z["id"], "cidade_codigo_ibge": cidade["codigo_ibge"],
              "latitude": latitude, "longitude": -50, "fuso_horario": "America/Sao_Paulo",
              "altitude_m": 400, "peso_medio_kg": {"frangos": 2.5, "bovinos": 600, "suinos": 100}[especie],
              "area_util_m2": 150, "densidade_categoria": "media", "producao_leite_kg_dia": 0, "ordenhas_dia": 0}
    dados.salvar_configuracoes_zonas([config], [z])
    return z, config


def parametros():
    return {"dias": 1, "intervalo_minutos": 60, "data_final": "2026-01-01", "semente": 42}


@pytest.mark.parametrize("especie", ["frangos", "bovinos", "suinos"])
def test_geracao_reproduzivel_publicacao_e_consolidacao_preservam_amostras(ambiente, banco, especie):
    z, _ = configurar(especie)
    primeira = g.gerar(parametros(), [z])
    segunda = g.gerar(parametros(), [z])
    assert primeira["total_medicoes"] == segunda["total_medicoes"] == 24
    assert len(ambiente["chamadas"]) == 1  # A segunda execução usa o cache persistido.
    with dados._conexao(escrita=False) as conn:
        def medicoes(eid):
            return [dict(linha) for linha in conn.execute(
                "SELECT timestamp_utc, timestamp_local, animais_em_pe, animais_deitados, quantidade_animais, "
                "animais_em_ordenha, alimentacao_kg, consumo_agua_l, valor_indice, origem_variaveis "
                "FROM medicoes WHERE execucao_id=? ORDER BY timestamp_utc", (eid,)).fetchall()]
        a, b = medicoes(primeira["execucao_id"]), medicoes(segunda["execucao_id"])
    assert a == b and len(a) == 24
    assert dt.datetime.fromisoformat(str(a[0]["timestamp_utc"])).hour == 3
    for amostra in a:
        assert amostra["animais_em_pe"] + amostra["animais_deitados"] == amostra["quantidade_animais"]
        assert 0 <= amostra["animais_em_ordenha"] <= amostra["animais_em_pe"]
        assert amostra["consumo_agua_l"] > 0 and amostra["alimentacao_kg"] >= 0
        assert "ERA5" in str(amostra["origem_variaveis"])
    assert dados.copiar_medicoes_para_historico(primeira["execucao_id"])["novas_copiadas"] == 24
    assert dados.copiar_medicoes_para_historico(primeira["execucao_id"])["novas_copiadas"] == 0
    assert db.contar_leituras() == 24
    consolidado = agregacao.executar_para_zona(z)
    assert consolidado["janelas_15min_consolidadas"] == consolidado["horas_consolidadas"] == 24
    assert agregacao.executar_para_zona(z)["horas_consolidadas"] == 0
    assert db.contar_leituras() == 24  # Consolidar preserva a série bruta.


def test_falha_na_segunda_zona_limpa_lotes_ja_confirmados_e_permite_retry(ambiente):
    a, _ = configurar(latitude=-20)
    b, _ = configurar(latitude=-21)
    ambiente["falhar_segunda"] = True
    with pytest.raises(g.GeracaoDadosError):
        g.gerar(parametros(), [a, b])
    execucao = dados.listar_execucoes()[0]
    assert execucao["status"] == "falhou" and execucao["erro"]
    with dados._conexao(escrita=False) as conn:
        assert conn.execute("SELECT count(*) FROM medicoes").fetchone()[0] == 0
    with pytest.raises(dados.ConfiguracaoDadosEntradaError):
        dados.copiar_medicoes_para_historico(execucao["id"])
    ambiente["falhar_segunda"] = False
    assert g.gerar(parametros(), [a, b])["total_medicoes"] == 48


@pytest.mark.parametrize("defeito", ["sem_tempos", "variavel_ausente", "nulo", "nao_finito", "ur_zero", "periodo_incompleto"])
def test_fonte_invalida_nao_publica_nem_inventa_medicao(ambiente, defeito):
    def alterar(payload):
        hourly = payload["hourly"]
        if defeito == "sem_tempos":
            hourly["time"] = []
        elif defeito == "variavel_ausente":
            del hourly["wind_speed_10m"]
        elif defeito == "periodo_incompleto":
            for chave in hourly:
                hourly[chave] = hourly[chave][:3]
        else:
            campo, valor = {"nulo": ("temperature_2m", None), "nao_finito": ("relative_humidity_2m", float("nan")),
                            "ur_zero": ("relative_humidity_2m", 0)}[defeito]
            hourly[campo] = [valor] * len(hourly["time"])
    ambiente["alterar"] = alterar
    z, _ = configurar()
    with pytest.raises(g.GeracaoDadosError):
        g.gerar(parametros(), [z])
    assert dados.listar_execucoes()[0]["status"] == "falhou"
    assert db.contar_leituras() == 0
    with dados._conexao(escrita=False) as conn:
        assert conn.execute("SELECT count(*) FROM medicoes").fetchone()[0] == 0


def test_configuracao_em_lote_invalida_nao_salva_primeira_zona(ambiente):
    z, config = configurar()
    anterior = copy.deepcopy(dados.listar_configuracoes([z]))
    with pytest.raises(dados.ConfiguracaoDadosEntradaError):
        dados.salvar_configuracoes_zonas([{**config, "peso_medio_kg": 3}, {**config, "zona_id": 2147483647}], [z])
    assert dados.listar_configuracoes([z]) == anterior
