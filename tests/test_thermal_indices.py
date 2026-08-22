"""Caracterização das equações e dos limites científicos implementados.

Estes testes preservam o comportamento atribuído no código à dissertação de
Angelo (UNIP, 2013). Eles são uma proteção contra regressões de software; não
substituem validação acadêmica das fontes nem validação experimental em campo.
"""

import math

import pytest

from app import thermal_indices as ti


@pytest.mark.parametrize(
    ("calculadora", "argumentos", "publicado"),
    [
        (ti.calcular_itu, (27, 19), 73.72),
        (ti.calcular_ignu, (42, 8), 69.58),
        (ti.calcular_ituv, (22, 1, 4), 17.39),
    ],
    ids=("ITU-tabela-5", "IGNU-tabela-6", "ITUV-tabela-7"),
)
def test_equacoes_reproduzem_exemplos_numericos_da_dissertacao(
    calculadora, argumentos, publicado
):
    assert calculadora(*argumentos) == pytest.approx(publicado, abs=0.01)


@pytest.mark.parametrize(
    ("especie", "indice", "disponivel"),
    [
        ("frangos", "ITU", True),
        ("frangos", "ITUV", True),
        ("frangos", "IGNU", True),
        ("bovinos", "ITU", True),
        ("bovinos", "ITUV", False),
        ("bovinos", "IGNU", True),
        ("suinos", "ITU", True),
        ("suinos", "ITUV", False),
        ("suinos", "IGNU", True),
        ("especie-inexistente", "ITU", False),
        ("frangos", "INDICE-INEXISTENTE", False),
    ],
)
def test_disponibilidade_documentada_dos_indices(especie, indice, disponivel):
    assert ti.indice_disponivel(especie, indice) is disponivel


LIMITES_DOCUMENTADOS = (
    ("frangos", "ITU", 74, 79, 84),
    ("bovinos", "ITU", 70, 78, 83),
    ("suinos", "ITU", 65, 69, 73),
    ("frangos", "ITUV", 24, 34, 39),
    ("frangos", "IGNU", 76, 76, 76),
    ("bovinos", "IGNU", 74, 78, 84),
    ("suinos", "IGNU", 69.6, 82.6, 82.6),
)


def _status_esperado(valor, conforto, alerta, perigo):
    if valor <= conforto:
        return "Conforto"
    if valor <= alerta:
        return "Alerta"
    if valor <= perigo:
        return "Perigo"
    return "Emergência"


@pytest.mark.parametrize(
    ("especie", "indice", "conforto", "alerta", "perigo"),
    LIMITES_DOCUMENTADOS,
)
@pytest.mark.parametrize("nome_limite", ("conforto", "alerta", "perigo"))
def test_classificacao_na_igualdade_e_imediatamente_acima_de_cada_limite(
    especie, indice, conforto, alerta, perigo, nome_limite
):
    limites = {"conforto": conforto, "alerta": alerta, "perigo": perigo}
    limite = limites[nome_limite]
    imediatamente_acima = math.nextafter(limite, math.inf)

    assert ti.classificar_status(limite, especie, indice) == _status_esperado(
        limite, conforto, alerta, perigo
    )
    assert ti.classificar_status(imediatamente_acima, especie, indice) == _status_esperado(
        imediatamente_acima, conforto, alerta, perigo
    )


@pytest.mark.parametrize(
    ("especie", "valor", "status"),
    [
        ("frangos", 76, "Conforto"),
        ("frangos", math.nextafter(76, math.inf), "Emergência"),
        ("suinos", 82.6, "Alerta"),
        ("suinos", math.nextafter(82.6, math.inf), "Emergência"),
    ],
)
def test_ignu_preserva_faixas_colapsadas_sem_inventar_categorias(especie, valor, status):
    assert ti.classificar_status(valor, especie, "IGNU") == status


@pytest.mark.parametrize(
    ("indice", "entradas", "campo_ausente"),
    [
        ("ITU", {"tbs": 27}, "tbu"),
        ("ITUV", {"tbs": 22, "tbu": 1}, "v"),
        ("IGNU", {"tgn": 42, "tpo": ""}, "tpo"),
    ],
)
def test_validacao_rejeita_campos_ausentes(indice, entradas, campo_ausente):
    with pytest.raises(ti.EntradaInvalidaError, match=campo_ausente):
        ti.validar_entradas(indice, entradas)


def test_validacao_rejeita_texto_nao_numerico():
    with pytest.raises(ti.EntradaInvalidaError, match="numérico"):
        ti.validar_entradas("ITU", {"tbs": "vinte", "tbu": 19})


@pytest.mark.parametrize(
    ("indice", "entradas", "campo"),
    [
        ("ITU", {"tbs": math.nan, "tbu": 19}, "tbs"),
        ("ITU", {"tbs": math.inf, "tbu": 19}, "tbs"),
        ("ITU", {"tbs": 55.1, "tbu": 19}, "tbs"),
        ("IGNU", {"tgn": 42, "tpo": -20.1}, "tpo"),
        ("ITUV", {"tbs": 22, "tbu": 1, "v": 15.1}, "v"),
    ],
)
def test_validacao_rejeita_valores_nao_finitos_ou_fora_da_faixa(indice, entradas, campo):
    with pytest.raises(ti.EntradaInvalidaError, match=campo):
        ti.validar_entradas(indice, entradas)


@pytest.mark.parametrize("velocidade", (0, -0.01))
def test_equacao_ituv_rejeita_velocidade_nao_positiva(velocidade):
    with pytest.raises(ti.EntradaInvalidaError, match="maior que zero"):
        ti.calcular_ituv(22, 1, velocidade)


def test_validacao_rejeita_velocidade_abaixo_da_faixa_documentada():
    with pytest.raises(ti.EntradaInvalidaError, match="fora da faixa"):
        ti.validar_entradas("ITUV", {"tbs": 22, "tbu": 1, "v": 0})


@pytest.mark.parametrize(
    "rotina",
    (
        ti.calcular_pressao_vapor_atual,
        ti.calcular_umidade_relativa,
        ti.calcular_ponto_orvalho,
    ),
)
def test_rotinas_psicrometricas_rejeitam_bulbo_umido_acima_do_seco(rotina):
    with pytest.raises(ti.EntradaInvalidaError, match="bulbo umido"):
        rotina(20, 21)


def test_decimal_com_virgula_e_fluxo_integrado_de_calculo_e_classificacao():
    entradas = {"tbs": "27,0", "tbu": "19,0"}

    assert ti.validar_entradas("ITU", entradas) == {"tbs": 27.0, "tbu": 19.0}
    assert ti.calcular_e_classificar("frangos", "ITU", entradas) == (73.72, "Conforto")


@pytest.mark.parametrize(
    ("tabela", "chave", "novo_valor"),
    [
        (ti.INDICES_POR_ESPECIE, "frangos", ()),
        (ti.CAMPOS_POR_INDICE, "ITU", ()),
        (ti.RANGE_VALIDACAO, "tbs", (0.0, 1.0)),
        (ti.LIMITES["ITU"]["frangos"], "conforto", 999),
        (ti.CAMPO_METADADOS["tbs"], "min", -999),
    ],
)
def test_tabelas_compartilhadas_sao_imutaveis(tabela, chave, novo_valor):
    with pytest.raises(TypeError):
        tabela[chave] = novo_valor
