"""O perfil decide as areas, e a decisao fica no servidor.

Esconder aba e apresentacao. O que impede um perfil de alcancar uma area e o
`_exigir_login_e_area`, e e isso que este arquivo mede.
"""

from __future__ import annotations

import inspect

from app import auth


def test_perfil_sem_a_area_e_barrado_no_servidor():
    fonte = inspect.getsource(auth.registrar_autenticacao)
    assert "AREA_POR_ENDPOINT" in fonte
    assert "area_permitida(" in fonte
    assert "_negar_acesso()" in fonte


def test_area_permitida_decide_pelo_mapa_do_perfil():
    # A funcao e o unico ponto que traduz perfil em area; testa-la direto evita
    # depender de montar uma requisicao.
    assert auth.area_permitida("administrador", "sistema") is True
    assert auth.area_permitida("operador", "sistema") is False
    assert auth.area_permitida("perfil-que-nao-existe", "dashboard") is False


def test_operador_nao_alcanca_area_de_sistema():
    # O perfil mais restrito nao pode ter ganho acesso a administracao por
    # descuido em uma edicao do mapa.
    assert "sistema" not in auth.AREAS_POR_PERFIL["operador"]
    assert "cadastro" not in auth.AREAS_POR_PERFIL["operador"]


def test_administrador_alcanca_tudo():
    todas = set().union(*auth.AREAS_POR_PERFIL.values())
    assert set(auth.AREAS_POR_PERFIL["administrador"]) == todas


def test_perfil_desconhecido_nao_alcanca_nada():
    # `AREAS_POR_PERFIL.get(perfil, frozenset())` precisa ser o padrao: um
    # perfil que apareca no banco sem entrada no mapa tem de cair no mais
    # restritivo, nao no mais permissivo.
    fonte = inspect.getsource(auth)
    assert "AREAS_POR_PERFIL.get(" in fonte
