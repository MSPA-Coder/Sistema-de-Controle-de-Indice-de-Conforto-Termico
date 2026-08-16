"""Persistência e invariantes do agregado de usuários."""

from __future__ import annotations

import datetime

from .database_comum import PERFIS_VALIDOS, coagir_booleano, conexao


class UsuarioInvalidoError(ValueError):
    """Dados de usuário inválidos."""


class UsuarioNaoEncontradoError(UsuarioInvalidoError):
    """Operação que referenciou um usuário inexistente."""


class UltimoAdministradorError(UsuarioInvalidoError):
    """Operação que removeria o último administrador ativo."""


def _bloquear_administradores(conn) -> None:
    conn.execute("SELECT pg_advisory_xact_lock(hashtext('conforto:administradores'))")


def _validar_usuario(dados: dict, *, exigir_senha: bool) -> dict:
    nome = str(dados.get("nome", "")).strip()
    if not nome:
        raise UsuarioInvalidoError("Informe o nome do usuário.")
    login = str(dados.get("login", "")).strip()
    if not login:
        raise UsuarioInvalidoError("Informe o login do usuário.")
    if len(login) > 80:
        raise UsuarioInvalidoError("O login pode ter no máximo 80 caracteres.")
    if any(caractere.isspace() for caractere in login):
        raise UsuarioInvalidoError("O login não pode conter espaços.")
    perfil = dados.get("perfil")
    if perfil not in PERFIS_VALIDOS:
        raise UsuarioInvalidoError(
            f"Perfil inválido: {perfil!r} (esperado um de {PERFIS_VALIDOS})."
        )
    resultado = {
        "nome": nome[:255],
        "login": login,
        "perfil": perfil,
        "ativo": coagir_booleano(dados.get("ativo", True), True),
    }
    senha_hash = dados.get("senha_hash")
    if exigir_senha and not senha_hash:
        raise UsuarioInvalidoError("Informe uma senha para o usuário.")
    if senha_hash:
        resultado["senha_hash"] = senha_hash
    return resultado


def _linha_usuario_publica(linha) -> dict:
    usuario = dict(linha)
    usuario.pop("senha_hash", None)
    usuario["ativo"] = bool(usuario["ativo"])
    return usuario


def criar_usuario(dados: dict) -> dict:
    validado = _validar_usuario(dados, exigir_senha=True)
    agora = datetime.datetime.now().replace(microsecond=0).isoformat(timespec="seconds")
    with conexao() as conn:
        existe = conn.execute(
            "SELECT 1 FROM usuarios WHERE login = ?", (validado["login"],)
        ).fetchone()
        if existe is not None:
            raise UsuarioInvalidoError(f"Já existe um usuário com o login '{validado['login']}'.")
        cursor = conn.execute(
            "INSERT INTO usuarios (nome, login, senha_hash, perfil, ativo, criado_em, atualizado_em) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                validado["nome"],
                validado["login"],
                validado["senha_hash"],
                validado["perfil"],
                int(validado["ativo"]),
                agora,
                agora,
            ),
        )
        linha = conn.execute("SELECT * FROM usuarios WHERE id = ?", (cursor.lastrowid,)).fetchone()
    return _linha_usuario_publica(linha)


def listar_usuarios() -> list[dict]:
    with conexao(escrita=False) as conn:
        linhas = conn.execute("SELECT * FROM usuarios ORDER BY nome").fetchall()
    return [_linha_usuario_publica(linha) for linha in linhas]


def obter_usuario(usuario_id: int) -> dict | None:
    with conexao(escrita=False) as conn:
        linha = conn.execute("SELECT * FROM usuarios WHERE id = ?", (usuario_id,)).fetchone()
    return _linha_usuario_publica(linha) if linha else None


def obter_usuario_por_login(login: str) -> dict | None:
    login = str(login or "").strip()
    if not login:
        return None
    with conexao(escrita=False) as conn:
        linha = conn.execute("SELECT * FROM usuarios WHERE login = ?", (login,)).fetchone()
    return dict(linha) if linha else None


def contar_usuarios_ativos_por_perfil(perfil: str, *, excluir_id: int | None = None) -> int:
    with conexao(escrita=False) as conn:
        if excluir_id is None:
            linha = conn.execute(
                "SELECT COUNT(*) AS total FROM usuarios WHERE perfil = ? AND ativo = 1", (perfil,)
            ).fetchone()
        else:
            linha = conn.execute(
                "SELECT COUNT(*) AS total FROM usuarios WHERE perfil = ? AND ativo = 1 AND id != ?",
                (perfil, excluir_id),
            ).fetchone()
    return int(linha["total"])


def atualizar_usuario(usuario_id: int, dados: dict) -> dict:
    validado = _validar_usuario(dados, exigir_senha=False)
    with conexao() as conn:
        _bloquear_administradores(conn)
        atual = conn.execute("SELECT * FROM usuarios WHERE id = ?", (usuario_id,)).fetchone()
        if atual is None:
            raise UsuarioNaoEncontradoError(f"Usuário {usuario_id} não encontrado.")
        conflito = conn.execute(
            "SELECT 1 FROM usuarios WHERE login = ? AND id != ?", (validado["login"], usuario_id)
        ).fetchone()
        if conflito is not None:
            raise UsuarioInvalidoError(f"Já existe um usuário com o login '{validado['login']}'.")
        deixa_de_ser_admin_ativo = atual["perfil"] == "administrador" and (
            validado["perfil"] != "administrador" or not validado["ativo"]
        )
        if deixa_de_ser_admin_ativo:
            restantes = conn.execute(
                "SELECT COUNT(*) AS total FROM usuarios WHERE perfil = 'administrador' AND ativo = 1 AND id != ?",
                (usuario_id,),
            ).fetchone()
            if int(restantes["total"]) == 0:
                raise UltimoAdministradorError(
                    "Esta é a última conta de administrador ativa. Promova outro usuário a administrador antes de alterar esta."
                )
        agora = datetime.datetime.now().replace(microsecond=0).isoformat(timespec="seconds")
        if "senha_hash" in validado:
            conn.execute(
                "UPDATE usuarios SET nome = ?, login = ?, perfil = ?, ativo = ?, senha_hash = ?, atualizado_em = ? WHERE id = ?",
                (
                    validado["nome"],
                    validado["login"],
                    validado["perfil"],
                    int(validado["ativo"]),
                    validado["senha_hash"],
                    agora,
                    usuario_id,
                ),
            )
        else:
            conn.execute(
                "UPDATE usuarios SET nome = ?, login = ?, perfil = ?, ativo = ?, atualizado_em = ? WHERE id = ?",
                (
                    validado["nome"],
                    validado["login"],
                    validado["perfil"],
                    int(validado["ativo"]),
                    agora,
                    usuario_id,
                ),
            )
        linha = conn.execute("SELECT * FROM usuarios WHERE id = ?", (usuario_id,)).fetchone()
    return _linha_usuario_publica(linha)


def excluir_usuario(usuario_id: int) -> bool:
    with conexao() as conn:
        _bloquear_administradores(conn)
        atual = conn.execute("SELECT * FROM usuarios WHERE id = ?", (usuario_id,)).fetchone()
        if atual is None:
            return False
        if atual["perfil"] == "administrador" and atual["ativo"]:
            restantes = conn.execute(
                "SELECT COUNT(*) AS total FROM usuarios WHERE perfil = 'administrador' AND ativo = 1 AND id != ?",
                (usuario_id,),
            ).fetchone()
            if int(restantes["total"]) == 0:
                raise UltimoAdministradorError(
                    "Esta é a última conta de administrador ativa e não pode ser excluída."
                )
        cursor = conn.execute("DELETE FROM usuarios WHERE id = ?", (usuario_id,))
    return int(cursor.rowcount) > 0


def registrar_login_usuario(usuario_id: int) -> None:
    agora = datetime.datetime.now().replace(microsecond=0).isoformat(timespec="seconds")
    with conexao() as conn:
        conn.execute("UPDATE usuarios SET ultimo_login_em = ? WHERE id = ?", (agora, usuario_id))
