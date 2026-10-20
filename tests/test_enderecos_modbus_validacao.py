"""Cadastro de hardware nunca arredonda um endereço nem admite escala não finita."""

import pytest

from app import database as db
from app.database.equipamentos import validar_equipamento


def dados(**mudancas):
    return {"tipo": "sensor", "nome": "QA", "campo_medido": "tbs", "modo_conexao": "tcp",
            "host": "sensor.invalid", "tipo_registrador": "holding", "endereco_registrador": 7, **mudancas}


@pytest.mark.parametrize("campo,valor", [
    ("endereco_registrador", 7.5), ("endereco_registrador", -0.1),
    ("porta", "502,5"), ("unidade_id", "1.9"), ("endereco_registrador", "inf"),
    ("fator_escala", "NaN"), ("fator_escala", "inf"),
])
def test_cadastro_recusa_valor_que_mudaria_endereco_ou_inviabilizaria_leitura(campo, valor):
    with pytest.raises(db.ZonaInvalidaError):
        validar_equipamento(dados(**{campo: valor}))


def test_endereco_inteiro_regional_e_escala_fracionaria_sao_preservados():
    validado = validar_equipamento(dados(endereco_registrador="7,0", fator_escala="0,1"))
    assert validado["endereco_registrador"] == 7
    assert validado["fator_escala"] == 0.1


def test_cadastro_invalido_nao_grava_equipamento_e_zona_permanece(banco):
    zona = db.criar_zona({"nome": "QA", "especie": "frangos", "indice": "ITU"})
    with pytest.raises(db.ZonaInvalidaError):
        db.criar_equipamento(zona["id"], dados(endereco_registrador=7.5))
    assert db.obter_zona(zona["id"])["equipamentos"] == []
