# -*- coding: utf-8 -*-
"""
thermal_indices.py
===================
Núcleo de cálculo do Sistema de Controle dos Índices de Conforto Térmico.

Implementa fielmente as três equações que a dissertação define como as
REALMENTE utilizadas no software (Capítulo III, Tabela 3 - "Algoritmos para
determinação dos Índices de Conforto Térmico"), e não as equações alternativas
apenas citadas na revisão bibliográfica (Eq. 2, 3 e 4, não implementadas):

    ITU  = 0,72 . (tbs + tbu) + 40,6                  Eq. 1 (KELLY; BOND, 1971)
    ITUV = (0,85.Tbs + 0,15.Tbu) . V^(-0,058)         Eq. 5 (TAO; XIN, 2003)
    IGNU = 0,6.Tgn + 0,36.Tpo + 41,5                  Eq. 6 (BUFFINGTON et al., 1981)

Todas as três fórmulas foram conferidas manualmente contra os exemplos
numéricos do Capítulo IV da própria dissertação (Tabelas 5, 6 e 7 e seção 4.3)
e reproduzem os valores publicados (ex.: tbs=27, tbu=19 -> ITU=73,72;
Tgn=42, Tpo=8 -> IGNU=69,58; tbs=22, tbu=1, V=4 -> ITUV=17,39) -- ver
test_thermal_indices.py.

Origem: dissertação de mestrado "Programa Computacional para o Cálculo de
Índices de Conforto Térmico na Produção Industrial de Animais para Carne e
Leite", Mariano Sergio Pacheco de Angelo, UNIP, 2013 (orientador: Prof. Dr.
Oduvaldo Vendrametto).
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Espécies e índices disponíveis (seção 4.3: "ITU: Avicultura, bovinocultura e
# suinocultura; ITUV: Avicultura; IGNU: Avicultura, bovinocultura e
# suinocultura.")
# ---------------------------------------------------------------------------
ESPECIES_VALIDAS: tuple[str, ...] = ("frangos", "bovinos", "suinos")

NOME_ESPECIE = {
    "frangos": "Avicultura (frangos de corte)",
    "bovinos": "Bovinocultura (bovinos de leite)",
    "suinos": "Suinocultura (suínos)",
}

INDICES_POR_ESPECIE: dict[str, tuple[str, ...]] = {
    "frangos": ("ITU", "ITUV", "IGNU"),
    "bovinos": ("ITU", "IGNU"),
    "suinos": ("ITU", "IGNU"),
}

NOME_INDICE = {
    "ITU": "Índice de Temperatura e Umidade",
    "ITUV": "Índice de Temperatura, Umidade e Velocidade",
    "IGNU": "Índice de Globo Negro e Umidade",
}

# Campos de entrada exigidos por índice (nomes conforme a própria dissertação)
CAMPOS_POR_INDICE: dict[str, tuple[str, ...]] = {
    "ITU": ("tbs", "tbu"),
    "ITUV": ("tbs", "tbu", "v"),
    "IGNU": ("tgn", "tpo"),
}

CAMPO_METADADOS: dict[str, dict] = {
    "tbs": {"label": "Temperatura de Bulbo Seco / Ambiente", "unidade": "°C", "min": -10, "max": 55, "passo": 0.1},
    "tbu": {"label": "Temperatura de Bulbo Úmido", "unidade": "°C", "min": -10, "max": 55, "passo": 0.1},
    "v": {"label": "Velocidade do Ar", "unidade": "m/s", "min": 0.01, "max": 15, "passo": 0.01},
    "tgn": {"label": "Temperatura de Globo Negro", "unidade": "°C", "min": -10, "max": 65, "passo": 0.1},
    "tpo": {"label": "Temperatura de Ponto de Orvalho", "unidade": "°C", "min": -20, "max": 45, "passo": 0.1},
}

RANGE_VALIDACAO = {
    # (mínimo, máximo) - a dissertação valida o programa gerando dados
    # aleatórios entre 0 e 45°C para temperaturas e 0,01 a 5,00 m/s para
    # velocidade do ar (seção 4.2). Aqui aceitamos uma folga adicional para
    # não travar leituras de campo ligeiramente fora da faixa validada.
    "tbs": (-10.0, 55.0),
    "tbu": (-10.0, 55.0),
    "tgn": (-10.0, 65.0),
    "tpo": (-20.0, 45.0),
    "v": (0.01, 15.0),
}


class EntradaInvalidaError(ValueError):
    """Erro de validação de uma variável de entrada fora da faixa aceitável."""


# ---------------------------------------------------------------------------
# Equações (Tabela 3 da dissertação)
# ---------------------------------------------------------------------------
def calcular_itu(tbs: float, tbu: float) -> float:
    """ITU - Eq. 1 (Kelly & Bond, 1971). Usado para frangos, bovinos e suínos."""
    return 0.72 * (tbs + tbu) + 40.6


def calcular_ituv(tbs: float, tbu: float, v: float) -> float:
    """ITUV - Eq. 5 (Tao & Xin, 2003). Usado apenas para frangos (aves de corte)."""
    v = v if v > 0 else 0.01  # base da potência não pode ser <= 0
    return (0.85 * tbs + 0.15 * tbu) * (v ** -0.058)


def calcular_ignu(tgn: float, tpo: float) -> float:
    """IGNU - Eq. 6 (Buffington et al., 1981)."""
    return 0.6 * tgn + 0.36 * tpo + 41.5


CALCULADORAS = {
    "ITU": calcular_itu,
    "ITUV": calcular_ituv,
    "IGNU": calcular_ignu,
}


def validar_entradas(indice: str, entradas: dict) -> dict:
    """Confere se todos os campos exigidos estão presentes e dentro da faixa
    aceitável, lançando EntradaInvalidaError com mensagem em português caso
    contrário. Retorna o dicionário de entradas já convertido para float."""
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
# Tabela 4 da dissertação - "Valores limites de ITU, ITUV e IGNU"
# ---------------------------------------------------------------------------
# Cada entrada guarda o limite SUPERIOR de "conforto", "alerta" e "perigo";
# qualquer valor acima do limite de "perigo" cai em "emergência". Os números
# abaixo foram lidos diretamente da Tabela 4 e conferidos contra os exemplos
# numéricos do Capítulo IV (ver test_thermal_indices.py).
#
# (*) IMPORTANTE: as linhas "suínos" de ITU (Sales et al., 2006) e de IGNU
# (Ferreira, 2001) vieram incompletas na tabela de origem (e essas duas
# referências, note-se, também não aparecem na lista de Referências
# Bibliográficas da própria dissertação). Para essas duas células, foi feita
# uma interpretação monotônica razoável, seguindo o mesmo padrão das demais
# linhas da tabela. Se você tiver os valores exatos de Sales et al. (2006) e
# Ferreira (2001), é só ajustar os números abaixo.
LIMITES = {
    "ITU": {
        "frangos": {"conforto": 74, "alerta": 79, "perigo": 84},  # Thom, 1959
        "bovinos": {"conforto": 70, "alerta": 78, "perigo": 83},  # Hahn, 1985
        "suinos": {"conforto": 61, "alerta": 65, "perigo": 69},  # Sales et al., 2006 (*)
    },
    "ITUV": {
        "frangos": {"conforto": 24, "alerta": 34, "perigo": 39},  # Xiao & Xin, 2003
    },
    "IGNU": {
        # Teixeira (1983): a tabela original só define "conforto" (<=76) e
        # ">76"; por isso alerta/perigo repetem o mesmo limite (o índice pula
        # direto para "Emergência" acima de 76 - confirmado pela Tabela 7).
        "frangos": {"conforto": 76, "alerta": 76, "perigo": 76},  # Teixeira, 1983
        "bovinos": {"conforto": 74, "alerta": 78, "perigo": 84},  # Baêta, 1985
        "suinos": {"conforto": 69.6, "alerta": 82.6, "perigo": 82.6},  # Ferreira, 2001 (*)
    },
}

STATUS_ORDEM = ("Conforto", "Alerta", "Perigo", "Emergência")

CORES_STATUS = {
    "Conforto": "#3E8E5B",
    "Alerta": "#E3A73E",
    "Perigo": "#C1443C",
    "Emergência": "#171512",
}

# Mensagens de orientação - reproduzidas das telas do próprio programa
# descrito na dissertação (Figuras 17/19, 20/22, 16/25 e 18).
MENSAGENS_STATUS = {
    "Conforto": "As condições de temperatura são adequadas.",
    "Alerta": "São necessárias medidas para a diminuição da temperatura.",
    "Perigo": (
        "As condições de temperatura exigem atenção imediata. "
        "Caso seja possível, ligue ventiladores ou nebulizadores."
    ),
    "Emergência": (
        "Condições extremas. Abaixe a temperatura imediatamente. "
        "Ligue ventiladores e nebulizadores e considere a retirada dos animais."
    ),
}

# Intensidade de acionamento dos equipamentos remotos (seção 4.3): em
# "Conforto" os equipamentos ficam desligados; a intensidade cresce com a
# gravidade, chegando ao nível máximo (com todos os equipamentos disponíveis)
# em "Emergência".
INTENSIDADE_EQUIPAMENTO = {
    "Conforto": None,
    "Alerta": "baixa",
    "Perigo": "média",
    "Emergência": "máxima",
}


def indice_disponivel(especie: str, indice: str) -> bool:
    return especie in ESPECIES_VALIDAS and indice in INDICES_POR_ESPECIE.get(especie, ())


def classificar_status(valor: float, especie: str, indice: str) -> str:
    """Classifica um valor de índice em Conforto / Alerta / Perigo / Emergência
    conforme a Tabela 4 da dissertação, para a espécie e índice informados."""
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
    """Função de conveniência: valida, calcula e classifica em um só passo."""
    if not indice_disponivel(especie, indice):
        raise EntradaInvalidaError(
            f"O índice {indice} não é aplicável à espécie '{especie}'."
        )
    entradas_validas = validar_entradas(indice, entradas)
    valor = round(CALCULADORAS[indice](**entradas_validas), 2)
    status = classificar_status(valor, especie, indice)
    return valor, status
