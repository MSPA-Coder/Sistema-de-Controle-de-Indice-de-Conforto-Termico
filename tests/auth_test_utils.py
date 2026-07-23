# -*- coding: utf-8 -*-
"""
auth_test_utils.py
=====================
Autentica clientes de teste. O padrao e usar o perfil administrador;
testes especificos de controle de acesso informam o perfil explicitamente.
"""

from __future__ import annotations

import itertools

from app import auth
from app import database as db

SENHA_TESTE = "senha-de-teste-1234"

_contador_login = itertools.count(1)


def criar_usuario_teste(perfil: str = "administrador", *, ativo: bool = True) -> dict:
    """Cria (e persiste no banco corrente -- ver `db.DB_PATH`) um usuario
    novo do perfil pedido, com login unico dentro do processo de teste."""
    login = f"teste_{perfil}_{next(_contador_login)}"
    return db.criar_usuario(
        {
            "nome": f"Usuário de teste ({perfil})",
            "login": login,
            "perfil": perfil,
            "ativo": ativo,
            "senha_hash": auth.gerar_hash_senha(SENHA_TESTE),
        }
    )


def cliente_autenticado(app, perfil: str = "administrador"):
    """Devolve um test client do Flask com uma sessao ja logada para um
    usuario novo do perfil pedido.

    Grava a sessao diretamente via `session_transaction` em vez de um POST
    /login de verdade: mais rapido e evita duplicar, em toda `setUp` deste
    projeto, a cobertura que o fluxo de login em si ja tem em
    test_auth.py."""
    usuario = criar_usuario_teste(perfil)
    client = app.test_client()
    with client.session_transaction() as sessao:
        sessao["usuario_id"] = usuario["id"]
    return client
