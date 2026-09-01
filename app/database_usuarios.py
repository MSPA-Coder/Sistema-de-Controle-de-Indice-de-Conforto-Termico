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
    # Mesma coagir-para-bool de `ativo`: a coluna e INTEGER 0/1 no banco (ver
    # a migration `20260830_0001_trocar_senha`), e quem le espera booleano.
    usuario["trocar_senha"] = bool(usuario.get("trocar_senha", 0))
    return usuario


def criar_usuario(dados: dict, *, exigir_troca: bool = True) -> dict:
    """Cria a conta. Por padrao, ja nasce com a obrigacao de trocar a senha.

    `exigir_troca=False` existe para o bootstrap por CLI
    (`scripts/criar_usuario_admin.py`): quem roda aquele script escolheu a
    propria senha e nao existe o terceiro que a criacao pela tela pressupoe.
    Obrigar a trocar ali transformaria o primeiro acesso num passo a mais sem
    ganho. O padrao continua sendo `True` para que a tela -- e qualquer
    caminho novo -- nasca protegida.
    """
    validado = _validar_usuario(dados, exigir_senha=True)
    agora = datetime.datetime.now().replace(microsecond=0).isoformat(timespec="seconds")
    with conexao() as conn:
        existe = conn.execute(
            "SELECT 1 FROM usuarios WHERE login = ?", (validado["login"],)
        ).fetchone()
        if existe is not None:
            raise UsuarioInvalidoError(f"Já existe um usuário com o login '{validado['login']}'.")
        cursor = conn.execute(
            "INSERT INTO usuarios "
            "(nome, login, senha_hash, perfil, ativo, trocar_senha, criado_em, atualizado_em) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                validado["nome"],
                validado["login"],
                validado["senha_hash"],
                validado["perfil"],
                int(validado["ativo"]),
                int(exigir_troca),
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


def obter_hash_de_senha(usuario_id: int) -> str | None:
    """Hash da senha em vigor, para amarrar a sessao a ela.

    `obter_usuario` remove o hash de proposito (`_linha_usuario_publica`), e e
    o que deve continuar acontecendo: aquele dicionario vira `g.usuario` e
    chega perto de template. Este caminho existe so para o carregamento da
    sessao conferir a marca, e devolve o hash e nada mais.
    """
    with conexao(escrita=False) as conn:
        linha = conn.execute(
            "SELECT senha_hash FROM usuarios WHERE id = ?", (usuario_id,)
        ).fetchone()
    return linha["senha_hash"] if linha else None


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
            # Senha vinda daqui e senha que outra pessoa escolheu: liga a
            # obrigacao de trocar, como a redefinicao faz. A tela de edicao
            # nao expoe mais esse campo, mas a funcao continua aceitando-o --
            # e um caminho que deixasse a senha alheia valendo para sempre
            # seria uma porta dos fundos silenciosa.
            conn.execute(
                "UPDATE usuarios SET nome = ?, login = ?, perfil = ?, ativo = ?, senha_hash = ?, trocar_senha = 1, atualizado_em = ? WHERE id = ?",
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


def redefinir_senha_usuario(usuario_id: int, senha_hash: str) -> dict:
    """Grava a senha temporaria de outra conta e liga a obrigacao de trocar.

    Separada de `atualizar_usuario` de proposito: aquilo edita nome, login,
    perfil e estado, e um caminho que faz as duas coisas juntas convida a
    redefinir senha sem querer ao salvar um formulario de cadastro.
    """
    agora = datetime.datetime.now().replace(microsecond=0).isoformat(timespec="seconds")
    with conexao() as conn:
        atual = conn.execute("SELECT 1 FROM usuarios WHERE id = ?", (usuario_id,)).fetchone()
        if atual is None:
            raise UsuarioNaoEncontradoError(f"Usuário {usuario_id} não encontrado.")
        conn.execute(
            "UPDATE usuarios SET senha_hash = ?, trocar_senha = 1, atualizado_em = ? WHERE id = ?",
            (senha_hash, agora, usuario_id),
        )
        linha = conn.execute("SELECT * FROM usuarios WHERE id = ?", (usuario_id,)).fetchone()
    return _linha_usuario_publica(linha)


def trocar_senha_propria(usuario_id: int, senha_hash: str) -> dict:
    """Grava a senha escolhida pelo proprio dono e desliga a obrigacao."""
    agora = datetime.datetime.now().replace(microsecond=0).isoformat(timespec="seconds")
    with conexao() as conn:
        atual = conn.execute("SELECT 1 FROM usuarios WHERE id = ?", (usuario_id,)).fetchone()
        if atual is None:
            raise UsuarioNaoEncontradoError(f"Usuário {usuario_id} não encontrado.")
        conn.execute(
            "UPDATE usuarios SET senha_hash = ?, trocar_senha = 0, atualizado_em = ? WHERE id = ?",
            (senha_hash, agora, usuario_id),
        )
        linha = conn.execute("SELECT * FROM usuarios WHERE id = ?", (usuario_id,)).fetchone()
    return _linha_usuario_publica(linha)


def registrar_login_usuario(usuario_id: int) -> None:
    agora = datetime.datetime.now().replace(microsecond=0).isoformat(timespec="seconds")
    with conexao() as conn:
        conn.execute("UPDATE usuarios SET ultimo_login_em = ? WHERE id = ?", (agora, usuario_id))
