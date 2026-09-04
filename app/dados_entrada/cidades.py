"""Referencias municipais e zootecnicas usadas no gerador.

Os rankings municipais sao da PPM 2024/IBGE (SIDRA): galinaceos - total
(frangos), vacas ordenhadas (bovinos leiteiros) e suinos - total. As
coordenadas, altitudes e fusos sao do geocodificador Open-Meteo.
"""

from __future__ import annotations

import math
from types import MappingProxyType
from typing import Any, cast

PESO_MEDIO_ESTIMADO_KG = MappingProxyType(
    {
        "frangos": 2.5,
        "bovinos": 600.0,
        "suinos": 100.0,
    }
)

# Os fatores transformam a lotação de referência em cenários comparáveis.
# "Acima" e "muito acima" são cenários de estresse, não recomendações.
CATEGORIAS_DENSIDADE = (
    MappingProxyType({"valor": "abaixo_media", "rotulo": "Abaixo da média", "fator": 0.75}),
    MappingProxyType({"valor": "media", "rotulo": "Na média", "fator": 1.0}),
    MappingProxyType({"valor": "acima_media", "rotulo": "Acima da média", "fator": 1.18}),
    MappingProxyType(
        {"valor": "muito_acima_media", "rotulo": "Muito acima da média", "fator": 1.27}
    ),
)

MODELOS_LOTACAO = MappingProxyType(
    {
        # Regra geral da Diretiva 2007/43/CE para frangos de corte.
        "frangos": MappingProxyType(
            {
                "tipo": "massa_viva",
                "referencia_kg_m2": 33.0,
                "fonte": "Diretiva 2007/43/CE (33 kg de peso vivo/m²)",
            }
        ),
        # Embrapa Gado de Corte: curral de confinamento com 15 m²/cabeça.
        "bovinos": MappingProxyType(
            {
                "tipo": "area_por_animal",
                "referencia_m2_animal": 15.0,
                "fonte": "Embrapa Gado de Corte (15 m²/cabeça em confinamento)",
            }
        ),
        # Diretiva 2008/120/CE, leitões e suínos de produção em grupo.
        "suinos": MappingProxyType(
            {
                "tipo": "faixas_area_por_animal",
                "faixas": (
                    MappingProxyType({"peso_max_kg": 10.0, "referencia_m2_animal": 0.15}),
                    MappingProxyType({"peso_max_kg": 20.0, "referencia_m2_animal": 0.20}),
                    MappingProxyType({"peso_max_kg": 30.0, "referencia_m2_animal": 0.30}),
                    MappingProxyType({"peso_max_kg": 50.0, "referencia_m2_animal": 0.40}),
                    MappingProxyType({"peso_max_kg": 85.0, "referencia_m2_animal": 0.55}),
                    MappingProxyType({"peso_max_kg": 110.0, "referencia_m2_animal": 0.65}),
                    MappingProxyType({"peso_max_kg": None, "referencia_m2_animal": 1.00}),
                ),
                "fonte": "Diretiva 2008/120/CE (faixas de área livre por peso)",
            }
        ),
    }
)


def calcular_lotacao(
    especie: str, peso_medio_kg: float, area_util_m2: float, categoria: str
) -> dict:
    fatores = {
        str(item["valor"]): float(cast("float", item["fator"])) for item in CATEGORIAS_DENSIDADE
    }
    if categoria not in fatores:
        raise ValueError("Categoria de densidade inválida.")
    modelo = cast("dict[str, Any]", MODELOS_LOTACAO[especie])
    peso = float(peso_medio_kg)
    area = float(area_util_m2)
    if peso <= 0 or area <= 0:
        raise ValueError("Peso e área útil devem ser positivos.")

    if modelo["tipo"] == "massa_viva":
        densidade_referencia = float(modelo["referencia_kg_m2"]) / peso
    elif modelo["tipo"] == "area_por_animal":
        densidade_referencia = 1.0 / float(modelo["referencia_m2_animal"])
    else:
        faixa = next(
            item
            for item in cast("tuple[dict[str, Any], ...]", modelo["faixas"])
            if item["peso_max_kg"] is None or peso <= item["peso_max_kg"]
        )
        densidade_referencia = 1.0 / float(faixa["referencia_m2_animal"])

    densidade_alvo = densidade_referencia * fatores[categoria]
    quantidade = math.floor(area * densidade_alvo + 1e-9)
    return {
        "quantidade_animais": quantidade,
        "densidade_animais_m2": quantidade / area,
        "densidade_alvo_animais_m2": densidade_alvo,
        "carga_viva_kg_m2": quantidade * peso / area,
    }


def _cidade(nome, uf, codigo_ibge, efetivo, latitude, longitude, altitude_m, fuso_horario):
    return MappingProxyType(
        {
            "nome": nome,
            "uf": uf,
            "codigo_ibge": codigo_ibge,
            "efetivo_2024": efetivo,
            "latitude": latitude,
            "longitude": longitude,
            "altitude_m": altitude_m,
            "fuso_horario": fuso_horario,
        }
    )


CIDADES_POR_ESPECIE = MappingProxyType(
    {
        "frangos": (
            _cidade(
                "Santa Maria de Jetibá",
                "ES",
                "3204559",
                17_477_126,
                -20.02745,
                -40.74336,
                713.0,
                "America/Sao_Paulo",
            ),
            _cidade(
                "São Bento do Una",
                "PE",
                "2613008",
                14_933_819,
                -8.52278,
                -36.44444,
                630.0,
                "America/Recife",
            ),
            _cidade(
                "Bastos",
                "SP",
                "3505807",
                13_650_920,
                -21.92194,
                -50.73389,
                460.0,
                "America/Sao_Paulo",
            ),
            _cidade(
                "Toledo",
                "PR",
                "4127700",
                12_071_286,
                -24.71361,
                -53.74306,
                562.0,
                "America/Sao_Paulo",
            ),
            _cidade(
                "Uberlândia",
                "MG",
                "3170206",
                12_040_000,
                -18.91861,
                -48.27722,
                867.0,
                "America/Sao_Paulo",
            ),
        ),
        "bovinos": (
            _cidade("Marabá", "PA", "1504208", 52_480, -5.38146, -49.13232, 95.0, "America/Belem"),
            _cidade(
                "Castro", "PR", "4104907", 47_033, -24.78927, -50.01225, 986.0, "America/Sao_Paulo"
            ),
            _cidade(
                "São Geraldo do Araguaia",
                "PA",
                "1507458",
                46_970,
                -6.40056,
                -48.555,
                131.0,
                "America/Belem",
            ),
            _cidade(
                "Patos de Minas",
                "MG",
                "3148004",
                45_434,
                -18.57889,
                -46.51806,
                842.0,
                "America/Sao_Paulo",
            ),
            _cidade(
                "Açailândia",
                "MA",
                "2100055",
                44_748,
                -4.94667,
                -47.50472,
                243.0,
                "America/Fortaleza",
            ),
        ),
        "suinos": (
            _cidade(
                "Toledo", "PR", "4127700", 949_984, -24.71361, -53.74306, 562.0, "America/Sao_Paulo"
            ),
            _cidade(
                "Uberlândia",
                "MG",
                "3170206",
                623_933,
                -18.91861,
                -48.27722,
                867.0,
                "America/Sao_Paulo",
            ),
            _cidade(
                "Marechal Cândido Rondon",
                "PR",
                "4114609",
                576_000,
                -24.55611,
                -54.05667,
                425.0,
                "America/Sao_Paulo",
            ),
            _cidade(
                "Concórdia",
                "SC",
                "4204301",
                517_700,
                -27.23417,
                -52.02778,
                592.0,
                "America/Sao_Paulo",
            ),
            _cidade(
                "Tapurah", "MT", "5108006", 407_087, -12.73714, -56.5136, 506.0, "America/Cuiaba"
            ),
        ),
    }
)


def referencias_publicas() -> dict:
    return {
        "ano_ranking": 2024,
        "fonte_ranking": "IBGE/SIDRA - Pesquisa da Pecuária Municipal 2024",
        "criterio_por_especie": {
            "frangos": "Galináceos - total",
            "bovinos": "Vacas ordenhadas",
            "suinos": "Suíno - total",
        },
        "fonte_localizacao": "Open-Meteo Geocoding API",
        "peso_medio_estimado_kg": dict(PESO_MEDIO_ESTIMADO_KG),
        "lotacao": {
            "categorias": [dict(item) for item in CATEGORIAS_DENSIDADE],
            "modelos": {
                especie: {
                    chave: ([dict(faixa) for faixa in valor] if chave == "faixas" else valor)
                    for chave, valor in cast("dict[str, Any]", modelo).items()
                }
                for especie, modelo in MODELOS_LOTACAO.items()
            },
        },
        "cidades_por_especie": {
            especie: [dict(cidade) for cidade in cidades]
            for especie, cidades in CIDADES_POR_ESPECIE.items()
        },
    }
