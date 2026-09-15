"""Caracterização das equações e dos limites científicos implementados.

Estes testes preservam o comportamento atribuído no código à dissertação de
Angelo (UNIP, 2013), com uma divergência declarada: o IGNU segue Buffington et
al. (1981), e não a Eq. 6 da dissertação (docs/adr/009-ignu-segue-buffington.md).
Eles são uma proteção contra regressões de software; não substituem validação
acadêmica das fontes nem validação experimental em campo.
"""

import math

import pytest

from app.termico import thermal_indices as ti


@pytest.mark.parametrize(
    ("calculadora", "argumentos", "publicado"),
    [
        (ti.calcular_itu, (27, 19), 73.72),
        # Confere a aritmética da Eq. 5, mas o ponto não é físico: a 22 °C o
        # bulbo úmido não desce de ~6,7 °C nem com 5% de umidade relativa, e
        # `validar_entradas` recusaria tbu acima de tbs.
        (ti.calcular_ituv, (22, 1, 4), 17.39),
    ],
    ids=("ITU-tabela-5", "ITUV-tabela-7"),
)
def test_equacoes_reproduzem_exemplos_numericos_da_dissertacao(
    calculadora, argumentos, publicado
):
    assert calculadora(*argumentos) == pytest.approx(publicado, abs=0.01)


def test_ignu_segue_buffington_e_nao_a_eq_6_da_dissertacao():
    """Referência: BGHI = Tgn + 0,36.Tpo + 41,5 (Buffington et al., 1981).

    O exemplo da Tabela 6 da dissertação (Tgn 42, Tpo 8) dava 69,58 com 0,6.Tgn;
    pela forma publicada, o mesmo ponto dá 86,38. O segundo assert fica para a
    divergência não voltar por engano -- mudar isto exige citar outra fonte.
    """
    assert ti.calcular_ignu(42, 8) == pytest.approx(42 + 0.36 * 8 + 41.5, abs=1e-9)
    assert ti.calcular_ignu(42, 8) != pytest.approx(69.58, abs=0.01)


@pytest.mark.parametrize(
    ("especie", "tgn", "tpo", "status"),
    [
        # Os pontos do laudo de 15/09/2026. Com 0,6.Tgn os três saíam Conforto.
        ("bovinos", 30, 20, "Perigo"),
        ("bovinos", 35, 22, "Emergencia"),
        ("bovinos", 42, 8, "Emergencia"),
        ("frangos", 30, 20, "Emergencia"),
        # E o lado de baixo continua em Conforto: a correção não empurra tudo.
        ("bovinos", 22, 12, "Conforto"),
    ],
)
def test_ignu_classifica_calor_de_globo_negro_como_estresse(especie, tgn, tpo, status):
    _, obtido = ti.calcular_e_classificar(especie, "IGNU", {"tgn": tgn, "tpo": tpo})

    assert obtido == status


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
    return "Emergencia"


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
        ("frangos", math.nextafter(76, math.inf), "Emergencia"),
        ("suinos", 82.6, "Alerta"),
        ("suinos", math.nextafter(82.6, math.inf), "Emergencia"),
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


@pytest.mark.parametrize(
    ("indice", "entradas"),
    [
        ("ITU", {"tbs": 22, "tbu": 25}),
        ("ITUV", {"tbs": 22, "tbu": "22,1", "v": 1}),
    ],
)
def test_validacao_rejeita_bulbo_umido_acima_do_seco(indice, entradas):
    """Sensores trocados: cada valor cabe na sua faixa, a combinação não existe."""
    with pytest.raises(ti.EntradaInvalidaError, match="bulbo úmido"):
        ti.validar_entradas(indice, entradas)


def test_validacao_aceita_bulbo_umido_igual_ao_seco():
    """Ar saturado: as duas temperaturas coincidem, e isso é físico."""
    assert ti.validar_entradas("ITU", {"tbs": 22, "tbu": 22}) == {"tbs": 22.0, "tbu": 22.0}


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


def test_token_de_status_e_sempre_ascii():
    """O token canonico e persistido e comparado como literal; acento nele
    quebra filtro de historico, contagem de percentuais e a migracao. O
    acento vive so no rotulo de exibicao."""
    for token in ti.STATUS_ORDEM:
        assert token.isascii(), f"token de status com caractere nao-ASCII: {token!r}"
    assert ti.classificar_status(1e9, "frangos", "ITU").isascii()
    assert ti.rotulo_do_status("Emergencia") == "Emergência"
    assert ti.rotulo_do_status("Conforto") == "Conforto"


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("Emergência", "Emergencia"),
        ("emergencia", "Emergencia"),
        ("EMERGÊNCIA", "Emergencia"),
        ("Perigo", "Perigo"),
        ("  ", None),
        ("inexistente", None),
    ],
)
def test_canonizar_status_aceita_qualquer_grafia(entrada, esperado):
    assert ti.canonizar_status(entrada) == esperado
