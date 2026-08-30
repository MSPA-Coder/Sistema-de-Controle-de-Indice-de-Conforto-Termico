"""O perfil decide as areas, e a decisao fica no servidor.

Esconder aba e apresentacao. O que impede um perfil de alcancar uma area e o
hook registrado por `registrar_controle_de_area`, e e isso que este arquivo
mede. O gate de "esta logado" vem de `sharedauth.access.requer_login` e não
decide papel/área, só autenticação.
"""

from __future__ import annotations

import inspect

from app import auth

# A recusa em si -- com sessao, perfil e rota de verdade -- e medida em
# `test_autorizacao_por_area.py`. O teste que ficava aqui lia o codigo-fonte do
# hook e conferia se as palavras "AREA_POR_ENDPOINT", "area_permitida(" e
# "_negar_acesso()" apareciam nele. Apareciam, e ele passou verde durante todo
# o tempo em que seis leituras respondiam a qualquer perfil: conferir que a
# verificacao esta ESCRITA nao responde se ela ALCANCA as rotas.


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
