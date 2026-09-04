"""A conversao de `?` para `%s` nao pode corromper consulta em silencio.

Ate 2026-08-21 a conversao era `sql.replace("?", "%s")`, com um comentario
dizendo que "as consultas do projeto nao contem o caractere '?' em literais
SQL". O invariante estava garantido por um comentario, e comentario nao
executa. Estes testes o tornam executavel.

O risco nao era teorico: `?`, `?|` e `?&` sao operadores de `jsonb` no
PostgreSQL, e este projeto ja consulta `jsonb` em `app/database/leituras.py`.
"""

from __future__ import annotations

import pytest

from app.nucleo.db_backend import _adaptar_placeholders, _conferir_aridade


def converter(sql: str) -> str:
    return _adaptar_placeholders(sql)[0]


def contar(sql: str) -> int:
    return _adaptar_placeholders(sql)[1]


# ---------------------------------------------------------------------------
# O caso comum continua funcionando
# ---------------------------------------------------------------------------


def test_marcadores_comuns_viram_por_cento_s():
    sql = "SELECT * FROM zonas WHERE id = ? AND ativo = ?"
    assert converter(sql) == "SELECT * FROM zonas WHERE id = %s AND ativo = %s"
    assert contar(sql) == 2


def test_sql_sem_marcador_fica_intacto():
    sql = "SELECT count(*) FROM leituras"
    assert converter(sql) == sql
    assert contar(sql) == 0


# ---------------------------------------------------------------------------
# O que a substituicao cega corrompia
# ---------------------------------------------------------------------------


def test_interrogacao_dentro_de_literal_nao_e_marcador():
    # `sql.replace` transformava isto em `= '%s'` e a consulta passava a
    # procurar a string literal "%s".
    sql = "SELECT * FROM zonas WHERE nome = 'e agora?'"
    assert converter(sql) == sql
    assert contar(sql) == 0


def test_aspa_simples_dobrada_nao_encerra_o_literal():
    sql = "SELECT * FROM zonas WHERE nome = 'aspa '' e ? dentro' AND id = ?"
    convertido, quantos = _adaptar_placeholders(sql)
    assert quantos == 1
    assert "'aspa '' e ? dentro'" in convertido
    assert convertido.endswith("id = %s")


def test_operador_jsonb_de_dois_caracteres_e_preservado():
    # `?|` pergunta se QUALQUER uma das chaves existe. Virar `%s|` seria erro
    # de sintaxe -- ou, pior, sintaxe valida com outro sentido.
    sql = "SELECT * FROM leituras WHERE entradas::jsonb ?| array['a','b']"
    assert converter(sql) == sql
    assert contar(sql) == 0

    sql_e = "SELECT * FROM leituras WHERE entradas::jsonb ?& array['a','b']"
    assert converter(sql_e) == sql_e


def test_identificador_entre_aspas_duplas_nao_e_tocado():
    sql = 'SELECT "coluna?estranha" FROM zonas WHERE id = ?'
    convertido, quantos = _adaptar_placeholders(sql)
    assert quantos == 1
    assert '"coluna?estranha"' in convertido


def test_comentario_de_linha_nao_e_tocado():
    sql = "SELECT 1 -- isto conta? nao\nWHERE id = ?"
    convertido, quantos = _adaptar_placeholders(sql)
    assert quantos == 1
    assert "-- isto conta? nao" in convertido


def test_comentario_de_bloco_aninhado_nao_e_tocado():
    # No PostgreSQL comentario de bloco aninha, ao contrario de outras
    # linguagens: o primeiro `*/` nao encerra os dois niveis.
    sql = "SELECT 1 /* fora /* dentro ? */ ainda ? */ WHERE id = ?"
    convertido, quantos = _adaptar_placeholders(sql)
    assert quantos == 1
    assert "/* fora /* dentro ? */ ainda ? */" in convertido


def test_literal_com_cifrao_nao_e_tocado():
    sql = "SELECT $tag$ tudo ? aqui e literal $tag$ WHERE id = ?"
    convertido, quantos = _adaptar_placeholders(sql)
    assert quantos == 1
    assert "$tag$ tudo ? aqui e literal $tag$" in convertido


# ---------------------------------------------------------------------------
# A rede: recusar em vez de mandar consulta torta para o banco
# ---------------------------------------------------------------------------


def test_aridade_correta_nao_levanta():
    _conferir_aridade("SELECT ? , ?", 2, 2)


def test_aridade_divergente_recusa_com_causa_provavel():
    # O `?` solto de jsonb (`coluna ? 'chave'`) e indistinguivel de um marcador
    # olhando so o texto -- por isso a decisao vem da contagem.
    with pytest.raises(ValueError) as erro:
        _conferir_aridade("SELECT * FROM l WHERE entradas ? 'chave' AND id = ?", 2, 1)

    mensagem = str(erro.value)
    assert "jsonb" in mensagem
    assert "jsonb_exists" in mensagem, "a mensagem precisa dizer como contornar"


def test_aridade_recusa_tambem_quando_faltam_marcadores():
    with pytest.raises(ValueError):
        _conferir_aridade("SELECT * FROM zonas WHERE id = ?", 1, 3)
