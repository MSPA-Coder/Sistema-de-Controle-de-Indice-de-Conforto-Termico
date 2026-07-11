# -*- coding: utf-8 -*-
"""
thermal_indices.py
===================
Nucleo de calculo do Sistema de Controle dos Indices de Conforto Termico.

Implementa fielmente as tres equacoes que a dissertacao define como as
REALMENTE utilizadas no software (Capitulo III, Tabela 3 - "Algoritmos para
determinacao dos Indices de Conforto Termico"), e nao as equacoes alternativas
apenas citadas na revisao bibliografica (Eq. 2, 3 e 4, nao implementadas):

    ITU  = 0,72 . (tbs + tbu) + 40,6                  Eq. 1 (KELLY; BOND, 1971)
    ITUV = (0,85.Tbs + 0,15.Tbu) . V^(-0,058)         Eq. 5 (TAO; XIN, 2003)
    IGNU = 0,6.Tgn + 0,36.Tpo + 41,5                  Eq. 6 (BUFFINGTON et al., 1981)

Todas as tres formulas foram conferidas manualmente contra os exemplos
numericos do Capitulo IV da propria dissertacao (Tabelas 5, 6 e 7 e secao 4.3)
e reproduzem os valores publicados (ex.: tbs=27, tbu=19 -> ITU=73,72;
Tgn=42, Tpo=8 -> IGNU=69,58; tbs=22, tbu=1, V=4 -> ITUV=17,39) -- ver
test_thermal_indices.py.

Origem: dissertacao de mestrado "Programa Computacional para o Calculo de
Indices de Conforto Termico na Producao Industrial de Animais para Carne e
Leite", Mariano Sergio Pacheco de Angelo, UNIP, 2013 (orientador: Prof. Dr.
Oduvaldo Vendrametto).
"""

from __future__ import annotations

import math
import unicodedata
from types import MappingProxyType
from typing import Any


def normalizar_chave_texto(valor: str) -> str:
    return unicodedata.normalize("NFD", str(valor)).encode("ascii", "ignore").decode("ascii")


def _congelar(estrutura: Any) -> Any:
    """Congela recursivamente dicts (e dicts aninhados) em MappingProxyType.

    NOTA DE ESTABILIDADE: os dicionarios abaixo (LIMITES, INDICES_POR_ESPECIE,
    CAMPOS_POR_INDICE, etc.) sao estado compartilhado por TODAS as
    requisicoes HTTP, ja que o processo Flask e de longa duracao. Um dict
    mutavel aqui e uma superficie de bug silenciosa: um `item["chave"] = x`
    acidental em qualquer parte do codigo (presente ou futura) corromperia a
    configuracao para todos os usuarios ate o processo reiniciar, sem
    lancar excecao nenhuma. Congelar com MappingProxyType transforma esse
    erro de programacao em um TypeError imediato e barulhento, no lugar de
    uma corrupcao de estado silenciosa em producao."""
    if isinstance(estrutura, dict):
        return MappingProxyType({chave: _congelar(valor) for chave, valor in estrutura.items()})
    return estrutura


# ---------------------------------------------------------------------------
# Especies e indices disponiveis (secao 4.3: "ITU: Avicultura, bovinocultura e
# suinocultura; ITUV: Avicultura; IGNU: Avicultura, bovinocultura e
# suinocultura.")
# ---------------------------------------------------------------------------
ESPECIES_VALIDAS: tuple[str, ...] = ("frangos", "bovinos", "suinos")

NOME_ESPECIE = _congelar({
    "frangos": "Avicultura (frangos de corte)",
    "bovinos": "Bovinocultura (bovinos de leite)",
    "suinos": "Suinocultura (suínos)",
})

INDICES_POR_ESPECIE = _congelar({
    "frangos": ("ITU", "ITUV", "IGNU"),
    "bovinos": ("ITU", "IGNU"),
    "suinos": ("ITU", "IGNU"),
})

NOME_INDICE = _congelar({
    "ITU": "Índice de Temperatura e Umidade",
    "ITUV": "Índice de Temperatura, Umidade e Velocidade",
    "IGNU": "Índice de Globo Negro e Umidade",
})

# Campos de entrada exigidos por indice (nomes conforme a propria dissertacao)
CAMPOS_POR_INDICE = _congelar({
    "ITU": ("tbs", "tbu"),
    "ITUV": ("tbs", "tbu", "v"),
    "IGNU": ("tgn", "tpo"),
})

CAMPO_METADADOS = _congelar({
    "tbs": {"label": "Temperatura de Bulbo Seco / Ambiente", "unidade": "°C", "min": -10, "max": 55, "passo": 0.1},
    "tbu": {"label": "Temperatura de Bulbo Úmido", "unidade": "°C", "min": -10, "max": 55, "passo": 0.1},
    "ur": {"label": "Umidade Relativa do Ar", "unidade": "%", "min": 0, "max": 100, "passo": 0.1},
    "v": {"label": "Velocidade do Ar", "unidade": "m/s", "min": 0.01, "max": 15, "passo": 0.01},
    "tgn": {"label": "Temperatura de Globo Negro", "unidade": "°C", "min": -10, "max": 65, "passo": 0.1},
    "tpo": {"label": "Temperatura de Ponto de Orvalho", "unidade": "°C", "min": -20, "max": 45, "passo": 0.1},
})

RANGE_VALIDACAO = _congelar({
    # (minimo, maximo) - a dissertacao valida o programa gerando dados
    # aleatorios entre 0 e 45°C para temperaturas e 0,01 a 5,00 m/s para
    # velocidade do ar (secao 4.2). Aqui aceitamos uma folga adicional para
    # nao travar leituras de campo ligeiramente fora da faixa validada.
    "tbs": (-10.0, 55.0),
    "tbu": (-10.0, 55.0),
    "tgn": (-10.0, 65.0),
    "tpo": (-20.0, 45.0),
    "v": (0.01, 15.0),
})


class EntradaInvalidaError(ValueError):
    """Erro de validacao de uma variavel de entrada fora da faixa aceitavel."""


# ---------------------------------------------------------------------------
# Equacoes (Tabela 3 da dissertacao)
# ---------------------------------------------------------------------------
def calcular_itu(tbs: float, tbu: float) -> float:
    """ITU - Eq. 1 (Kelly & Bond, 1971). Usado para frangos, bovinos e suinos."""
    return 0.72 * (tbs + tbu) + 40.6


def calcular_ituv(tbs: float, tbu: float, v: float) -> float:
    """ITUV - Eq. 5 (Tao & Xin, 2003). Usado apenas para frangos (aves de corte)."""
    v = v if v > 0 else 0.01  # base da potencia nao pode ser <= 0
    return (0.85 * tbs + 0.15 * tbu) * (v ** -0.058)


def calcular_ignu(tgn: float, tpo: float) -> float:
    """IGNU - Eq. 6 (Buffington et al., 1981)."""
    return 0.6 * tgn + 0.36 * tpo + 41.5


def calcular_pressao_atmosferica(altitude_m: float = 0.0) -> float:
    """Pressao atmosferica local estimada pela altitude, em kPa."""
    altitude = max(-500.0, min(9000.0, float(altitude_m)))
    return 101.325 * ((1 - 2.25577e-5 * altitude) ** 5.2559)


def calcular_pressao_vapor_saturado(temperatura_c: float) -> float:
    """Pressao de vapor saturado pela forma de Magnus, em kPa."""
    temperatura = float(temperatura_c)
    return 0.61078 * math.exp((17.27 * temperatura) / (temperatura + 237.3))


def calcular_pressao_vapor_atual(tbs: float, tbu: float, altitude_m: float = 0.0) -> float:
    """Pressao parcial de vapor a partir de bulbo seco/umido, em kPa."""
    tbs = float(tbs)
    tbu = float(tbu)
    if tbu > tbs:
        raise EntradaInvalidaError(
            "A temperatura de bulbo umido nao pode ser maior que a temperatura de bulbo seco."
        )

    pressao = calcular_pressao_atmosferica(altitude_m)
    constante_psicrometrica = 0.00066 * (1 + 0.00115 * tbu)
    vapor = calcular_pressao_vapor_saturado(tbu) - constante_psicrometrica * pressao * (tbs - tbu)
    return max(0.001, vapor)


def calcular_umidade_relativa(tbs: float, tbu: float, altitude_m: float = 0.0) -> float:
    """Umidade relativa do ar calculada de tbs/tbu e altitude, em porcentagem."""
    vapor_atual = calcular_pressao_vapor_atual(tbs, tbu, altitude_m)
    vapor_saturado = calcular_pressao_vapor_saturado(float(tbs))
    return max(0.0, min(100.0, 100 * vapor_atual / vapor_saturado))


def calcular_ponto_orvalho(tbs: float, tbu: float, altitude_m: float = 0.0) -> float:
    """Temperatura de ponto de orvalho calculada de tbs/tbu e altitude, em graus C."""
    vapor_atual = calcular_pressao_vapor_atual(tbs, tbu, altitude_m)
    fator = math.log(vapor_atual / 0.61078)
    return (237.3 * fator) / (17.27 - fator)


CALCULADORAS = _congelar({
    "ITU": calcular_itu,
    "ITUV": calcular_ituv,
    "IGNU": calcular_ignu,
})


def validar_entradas(indice: str, entradas: dict) -> dict:
    """Confere se todos os campos exigidos estao presentes e dentro da faixa
    aceitavel, lancando EntradaInvalidaError com mensagem em portugues caso
    contrario. Retorna o dicionario de entradas ja convertido para float."""
    campos = CAMPOS_POR_INDICE[indice]
    faltando = [c for c in campos if c not in entradas or entradas[c] in (None, "")]
    if faltando:
        raise EntradaInvalidaError(
            f"Preencha todos os campos exigidos: {', '.join(faltando)}."
        )

    convertidas = {}
    for campo in campos:
        try:
            valor = float(str(entradas[campo]).replace(",", "."))
        except (TypeError, ValueError):
            raise EntradaInvalidaError(f"O valor de '{campo}' precisa ser numérico.")
        minimo, maximo = RANGE_VALIDACAO[campo]
        if not (minimo <= valor <= maximo):
            raise EntradaInvalidaError(
                f"O valor de '{campo}' ({valor}) está fora da faixa esperada "
                f"({minimo} a {maximo})."
            )
        if campo == "v" and valor <= 0:
            raise EntradaInvalidaError("A velocidade do ar deve ser maior que zero.")
        convertidas[campo] = valor
    return convertidas


# ---------------------------------------------------------------------------
# Tabela 4 da dissertacao - "Valores limites de ITU, ITUV e IGNU"
# ---------------------------------------------------------------------------
# Cada entrada guarda o limite SUPERIOR de "conforto", "alerta" e "perigo";
# qualquer valor acima do limite de "perigo" cai em "emergencia". Os numeros
# abaixo foram lidos diretamente da Tabela 4 e conferidos contra os exemplos
# numericos do Capitulo IV (ver test_thermal_indices.py).
#
# (*) IMPORTANTE: as linhas "suinos" de ITU (Sales et al., 2006) e de IGNU
# (Ferreira, 2001) vieram incompletas na tabela de origem (e essas duas
# referencias, note-se, tambem nao aparecem na lista de Referencias
# Bibliograficas da propria dissertacao). Para essas duas celulas, foi feita
# uma interpretacao monotonica razoavel, seguindo o mesmo padrao das demais
# linhas da tabela. Se voce tiver os valores exatos de Sales et al. (2006) e
# Ferreira (2001), e so ajustar os numeros abaixo.
LIMITES = _congelar({
    "ITU": {
        "frangos": {"conforto": 74, "alerta": 79, "perigo": 84},  # Thom, 1959
        "bovinos": {"conforto": 70, "alerta": 78, "perigo": 83},  # Hahn, 1985
        "suinos": {"conforto": 61, "alerta": 65, "perigo": 69},  # Sales et al., 2006 (*)
    },
    "ITUV": {
        "frangos": {"conforto": 24, "alerta": 34, "perigo": 39},  # Xiao & Xin, 2003
    },
    "IGNU": {
        # Teixeira (1983): a tabela original so define "conforto" (<=76) e
        # ">76"; por isso alerta/perigo repetem o mesmo limite (o indice pula
        # direto para "Emergencia" acima de 76 - confirmado pela Tabela 7).
        "frangos": {"conforto": 76, "alerta": 76, "perigo": 76},  # Teixeira, 1983
        "bovinos": {"conforto": 74, "alerta": 78, "perigo": 84},  # Baeta, 1985
        "suinos": {"conforto": 69.6, "alerta": 82.6, "perigo": 82.6},  # Ferreira, 2001 (*)
    },
})

STATUS_ORDEM = ("Conforto", "Alerta", "Perigo", "Emergência")

CORES_STATUS = _congelar({
    "Conforto": "#3E8E5B",
    "Alerta": "#E3A73E",
    "Perigo": "#C1443C",
    "Emergencia": "#171512",
})

# Mensagens de orientacao - reproduzidas das telas do proprio programa
# descrito na dissertacao (Figuras 17/19, 20/22, 16/25 e 18).
MENSAGENS_STATUS = _congelar({
    "Conforto": "As condições de temperatura são adequadas.",
    "Alerta": "São necessárias medidas para a diminuição da temperatura.",
    "Perigo": (
        "As condições de temperatura exigem atenção imediata. "
        "Caso seja possível, ligue ventiladores ou nebulizadores."
    ),
    "Emergencia": (
        "Condições extremas. Abaixe a temperatura imediatamente. "
        "Ligue ventiladores e nebulizadores e considere a retirada dos animais."
    ),
})

# Intensidade de acionamento dos equipamentos remotos (secao 4.3): em
# "Conforto" os equipamentos ficam desligados; a intensidade cresce com a
# gravidade, chegando ao nivel maximo (com todos os equipamentos disponiveis)
# em "Emergencia".
INTENSIDADE_EQUIPAMENTO = _congelar({
    "Conforto": None,
    "Alerta": "baixa",
    "Perigo": "media",
    "Emergencia": "maxima",
})


def cor_do_status(status: str) -> str:
    return CORES_STATUS[normalizar_chave_texto(status)]


def mensagem_do_status(status: str) -> str:
    return MENSAGENS_STATUS[normalizar_chave_texto(status)]


def intensidade_do_status(status: str) -> str | None:
    return INTENSIDADE_EQUIPAMENTO[normalizar_chave_texto(status)]


def indice_disponivel(especie: str, indice: str) -> bool:
    return especie in ESPECIES_VALIDAS and indice in INDICES_POR_ESPECIE.get(especie, ())


def classificar_status(valor: float, especie: str, indice: str) -> str:
    """Classifica um valor de indice em Conforto / Alerta / Perigo / Emergencia
    conforme a Tabela 4 da dissertacao, para a especie e indice informados."""
    if not indice_disponivel(especie, indice):
        raise EntradaInvalidaError(
            f"O índice {indice} não é aplicável à espécie '{especie}'."
        )
    limites = LIMITES[indice][especie]
    if valor <= limites["conforto"]:
        return "Conforto"
    if valor <= limites["alerta"]:
        return "Alerta"
    if valor <= limites["perigo"]:
        return "Perigo"
    return "Emergência"


def calcular_e_classificar(especie: str, indice: str, entradas: dict) -> tuple[float, str]:
    """Funcao de conveniencia: valida, calcula e classifica em um so passo."""
    if not indice_disponivel(especie, indice):
        raise EntradaInvalidaError(
            f"O índice {indice} não é aplicável à espécie '{especie}'."
        )
    entradas_validas = validar_entradas(indice, entradas)
    valor = round(CALCULADORAS[indice](**entradas_validas), 2)
    status = classificar_status(valor, especie, indice)
    return valor, status
