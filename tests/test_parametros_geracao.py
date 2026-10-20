"""Recusas de entrada e propriedades físicas da série de pesquisa."""

import datetime as dt

import pytest

from app.dados_entrada.gerador_dados import (
    GeracaoDadosError,
    calcular_bulbo_umido,
    calcular_ponto_orvalho,
    estimar_globo_negro,
    validar_parametros,
)


def parametros(**campos):
    return {"dias": 1, "intervalo_minutos": 60, "data_final": "2026-01-01", **campos}


@pytest.mark.parametrize("campo", ["dias", "intervalo_minutos"])
@pytest.mark.parametrize("valor", [1.5, True, float("inf")])
def test_quantidade_inteira_nao_trunca_fracao_nem_aceita_booleano(campo, valor):
    with pytest.raises(GeracaoDadosError):
        validar_parametros(parametros(**{campo: valor}), total_zonas=1)


def test_periodo_inclui_data_final_e_preserva_semente():
    resultado = validar_parametros(parametros(dias="3", semente="42"), total_zonas=2)
    assert resultado.data_inicio == dt.date(2025, 12, 30)
    assert resultado.data_final == dt.date(2026, 1, 1)
    assert resultado.semente == 42


def test_limite_de_consolidacao_aceita_ultimo_dia_e_recusa_dia_seguinte():
    limite = dt.date.today() - dt.timedelta(days=8)
    assert validar_parametros(parametros(data_final=limite.isoformat()), 1).data_final == limite
    with pytest.raises(GeracaoDadosError):
        validar_parametros(parametros(data_final=(limite + dt.timedelta(days=1)).isoformat()), 1)


def test_volume_maximo_e_calculado_antes_de_iniciar_trabalho():
    assert validar_parametros(parametros(intervalo_minutos=1440), 2_000_000).dias == 1
    with pytest.raises(GeracaoDadosError):
        validar_parametros(parametros(intervalo_minutos=1440), 2_000_001)


@pytest.mark.parametrize("umidade", [0, -1, 101, float("nan"), float("inf")])
def test_umidade_invalida_e_recusada_sem_fallback(umidade):
    for calcular in (calcular_ponto_orvalho, calcular_bulbo_umido):
        with pytest.raises(GeracaoDadosError):
            calcular(30, umidade)


def test_orvalho_na_saturacao_coincide_com_temperatura_e_cresce_com_umidade():
    assert calcular_ponto_orvalho(25, 100) == pytest.approx(25)
    assert calcular_ponto_orvalho(25, 40) < calcular_ponto_orvalho(25, 80) < 25


def test_bulbo_umido_permanece_abaixo_do_seco_no_cenario_de_pesquisa():
    assert 0 < calcular_bulbo_umido(30, 40) < calcular_bulbo_umido(30, 80) < 30


def test_globo_sem_radiacao_preserva_temperatura_e_vento_reduz_ganho():
    assert estimar_globo_negro(25, None, 0) == 25
    assert estimar_globo_negro(25, 0, 2) == 25
    assert 25 < estimar_globo_negro(25, 500, 4) < estimar_globo_negro(25, 500, 1)
    assert estimar_globo_negro(25, 10_000, 0) == 50


@pytest.mark.parametrize(("radiacao", "vento"), [(-1, 1), (1, -1), (float("nan"), 1), (1, float("inf"))])
def test_fonte_meteorologica_invalida_nao_gera_globo(radiacao, vento):
    with pytest.raises(GeracaoDadosError):
        estimar_globo_negro(25, radiacao, vento)
