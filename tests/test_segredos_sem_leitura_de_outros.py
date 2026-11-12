"""Nenhum segredo gerado por `configurar_segredos.py` é legível por "outros".

As senhas do PostgreSQL saíam 0444 (legíveis por qualquer usuário do VPS que
atravessasse o diretório). Quem as lê são o `postgres` (uid 70, dono) e a
aplicação (gid 10001): 0440 basta.
"""

from __future__ import annotations

from scripts import configurar_segredos as seg


def test_nenhum_segredo_e_legivel_por_outros():
    largos = {
        nome: oct(modo)
        for nome, (_, _, _, modo) in seg.ARQUIVOS.items()
        if modo & 0o007
    }
    assert not largos, f"segredos com permissão para 'outros': {largos}"


def test_as_senhas_do_postgres_sao_do_postgres_e_lidas_pelo_grupo_da_aplicacao():
    for nome in ("postgres_password.txt", "postgres_app_password.txt"):
        _, uid, gid, modo = seg.ARQUIVOS[nome]
        assert (uid, gid, modo) == (70, seg.APP_GID, 0o440), nome
