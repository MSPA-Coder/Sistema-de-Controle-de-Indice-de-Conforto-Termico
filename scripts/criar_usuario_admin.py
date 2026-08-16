"""Cria um usuário administrador diretamente no banco -- sem passar pelo
HTTP (que exigiria já estar logado como administrador para acessar
`/usuarios`).

Numa instalação nova, a tabela `usuarios` está vazia e NINGUÉM consegue
logar: `/usuarios` (onde se cadastra gente) exige estar logado como
administrador, e não existe nenhum administrador ainda. Este script existe
para quebrar esse ciclo -- rode uma vez, logo após a primeira instalação:

    python scripts/criar_usuario_admin.py

Ele pede nome, login e senha interativamente (a senha não aparece no
terminal, via `getpass`) e cria o usuário com perfil "administrador". Se já
existir algum administrador ativo, avisa e pede confirmação antes de
continuar -- criar administradores adicionais não tem risco (ao contrário
de excluir o último, que `database.py` já recusa sozinho), então este
script nunca IMPEDE a criação, só confirma que é intencional.

Depois do primeiro administrador criado, use a tela /usuarios (dentro do
próprio sistema, logado) para cadastrar o resto da equipe -- ver README.md,
seção "Perfis de usuário e autenticação"."""

from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app import auth
from app import database as db


def _ler_login(argumento: str | None) -> str:
    if argumento:
        return argumento.strip()
    valor = input("Login: ").strip()
    while not valor:
        valor = input("Login (obrigatório): ").strip()
    return valor


def _ler_nome(argumento: str | None) -> str:
    if argumento:
        return argumento.strip()
    valor = input("Nome completo: ").strip()
    while not valor:
        valor = input("Nome completo (obrigatório): ").strip()
    return valor


def _ler_senha() -> str:
    while True:
        senha = getpass.getpass(f"Senha (mínimo {auth.SENHA_TAMANHO_MINIMO} caracteres): ")
        if len(senha) < auth.SENHA_TAMANHO_MINIMO:
            print(f"A senha precisa ter pelo menos {auth.SENHA_TAMANHO_MINIMO} caracteres.")
            continue
        confirmacao = getpass.getpass("Confirme a senha: ")
        if senha != confirmacao:
            print("As senhas não coincidem. Tente de novo.")
            continue
        return senha


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nome", help="Nome completo (pede interativamente se omitido)")
    parser.add_argument("--login", help="Login (pede interativamente se omitido)")
    parser.add_argument(
        "--senha",
        help=(
            "Senha em texto puro (NAO recomendado -- fica no histórico do "
            "shell; prefira deixar de fora e digitar quando pedido)."
        ),
    )
    parser.add_argument(
        "--sim",
        action="store_true",
        help="Não pede confirmação ao criar um administrador adicional.",
    )
    argumentos = parser.parse_args()

    db.iniciar_banco()

    administradores_ativos = db.contar_usuarios_ativos_por_perfil("administrador")
    if administradores_ativos > 0 and not argumentos.sim:
        print(f"Já existe {administradores_ativos} administrador(es) ativo(s) cadastrado(s).")
        resposta = input("Criar mais um mesmo assim? [s/N] ").strip().lower()
        if resposta != "s":
            print("Cancelado.")
            return 1

    nome = _ler_nome(argumentos.nome)
    login = _ler_login(argumentos.login)
    senha = argumentos.senha or _ler_senha()
    if len(senha) < auth.SENHA_TAMANHO_MINIMO:
        print(
            f"A senha precisa ter pelo menos {auth.SENHA_TAMANHO_MINIMO} caracteres.",
            file=sys.stderr,
        )
        return 1

    try:
        usuario = db.criar_usuario(
            {
                "nome": nome,
                "login": login,
                "perfil": "administrador",
                "senha_hash": auth.gerar_hash_senha(senha),
            }
        )
    except db.UsuarioInvalidoError as erro:
        print(f"Não foi possível criar o usuário: {erro}", file=sys.stderr)
        return 1

    print(f"Usuário administrador '{usuario['login']}' criado com sucesso (id {usuario['id']}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
