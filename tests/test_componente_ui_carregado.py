"""O atributo de confirmacao so vale se o script estiver na pagina.

`data-sa-confirmar` nao e um handler: e um dado que o `sharedauth-ui.js` le
num listener delegado. Se o script nao chegar ao documento, o atributo fica
inerte, o formulario envia direto e a exclusao acontece sem perguntar -- sem
erro no console, sem nada quebrado na tela. Foi o que aconteceu com
`usuarios.html` entre a Fase 9 e 2026-08-22: o botao tinha os quatro
atributos e `_layout_auth.html` nao carregava o componente.

E a segunda forma do mesmo defeito no mesmo botao. A primeira foi
`onsubmit="return confirm(...)"`, que a CSP (`script-src 'self'`, sem
`unsafe-inline`) bloqueava. Nos dois casos a protecao existia no fonte e nao
existia no navegador, e nos dois casos um grep pelo atributo dizia que estava
tudo certo.

A causa comum e estrutural: este projeto tem DUAS cadeias de layout
(`index.html`, que monta a propria, e `_layout_auth.html`), enquanto os outros
tres apps do mantenedor tem um `base.html` unico por onde tudo passa. Uma
terceira cadeia nasceria com o mesmo buraco, por isso o teste abaixo varre os
templates em vez de conferir so o par conhecido.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

TEMPLATES = Path(__file__).resolve().parents[1] / "app" / "templates"

ARQUIVO_JS = "sharedauth-ui.js"
ARQUIVO_CSS = "sharedauth-ui.css"

_EXTENDS = re.compile(r"{%-?\s*extends\s+[\"']([^\"']+)[\"']")
_INCLUDE = re.compile(r"{%-?\s*include\s+[\"']([^\"']+)[\"']")
_BLOCO_VAZIO = re.compile(r"{%-?\s*block\s+(\w+)\s*-?%}\s*{%-?\s*endblock")


def _blocos_anulados(fonte: str) -> set[str]:
    """Blocos que este template sobrescreve com conteudo vazio.

    Sem isto o teste teria um ponto cego proprio: `login.html` declara
    `{% block componente_ui_js %}{% endblock %}` para nao pedir um arquivo que
    responde 302, e uma busca ingenua pelo texto no layout pai diria que o
    script chega -- verde para uma pagina que nao carrega nada. Um teste que
    erra da mesma forma que o defeito que procura nao serve.
    """
    return set(_BLOCO_VAZIO.findall(fonte))


def _sem_blocos(fonte: str, nomes: set[str]) -> str:
    """A fonte do layout menos os blocos que o filho anulou."""
    for nome in nomes:
        fonte = re.sub(
            r"{%-?\s*block\s+" + re.escape(nome) + r"\s*-?%}.*?{%-?\s*endblock[^%]*%}",
            "",
            fonte,
            flags=re.DOTALL,
        )
    return fonte


def _fontes() -> dict[str, str]:
    return {
        str(caminho.relative_to(TEMPLATES)).replace("\\", "/"): caminho.read_text(encoding="utf-8")
        for caminho in TEMPLATES.rglob("*.html")
    }


def _alcanca(nome: str, alvo: str, fontes: dict[str, str], vistos: set[str]) -> bool:
    """O `alvo` aparece neste template ou em algum que o envolve.

    Sobe por `extends` (o layout carrega o script) e tambem aceita ser
    alcancado por quem faz `include` deste arquivo: um fragmento trocado por
    htmx nao carrega script nenhum, quem carrega e a pagina que o contem.
    """
    if nome in vistos:
        return False
    vistos.add(nome)

    fonte = fontes.get(nome, "")
    if alvo in fonte:
        return True

    anulados = _blocos_anulados(fonte)
    for pai in _EXTENDS.findall(fonte):
        herdado = {
            outro: (_sem_blocos(f, anulados) if outro == pai else f) for outro, f in fontes.items()
        }
        if _alcanca(pai, alvo, herdado, vistos):
            return True

    for outro, fonte_outro in fontes.items():
        if nome in _INCLUDE.findall(fonte_outro) and _alcanca(outro, alvo, fontes, vistos):
            return True

    return False


_COMENTARIO = re.compile(r"{#.*?#}", re.DOTALL)


def _sem_comentarios(fonte: str) -> str:
    """Comentario Jinja nao e marcacao.

    Sem isto, um comentario que EXPLICA a ausencia do atributo faz o template
    entrar na lista dos que o usam -- foi o que aconteceu com `login.html`, que
    documenta justamente por que nao carrega o componente. E a mesma armadilha
    de um teste de CSS deste conjunto de projetos que casou com o comentario
    dizendo nao haver `url()`: procurar texto em fonte, sem descontar o que e
    prosa, mede a documentacao em vez do codigo.
    """
    return _COMENTARIO.sub("", fonte)


def _templates_com_atributo() -> list[str]:
    return sorted(
        nome for nome, fonte in _fontes().items() if "data-sa-" in _sem_comentarios(fonte)
    )


def test_existe_template_com_atributo_para_verificar():
    # Sem esta guarda o teste abaixo passa sozinho no dia em que alguem
    # renomear o atributo -- verde por nao ter encontrado nada para conferir.
    assert _templates_com_atributo()


@pytest.mark.parametrize("nome", _templates_com_atributo())
def test_template_com_atributo_alcanca_o_script(nome):
    fontes = _fontes()
    assert _alcanca(nome, ARQUIVO_JS, fontes, set()), (
        f"{nome} usa data-sa-* mas nem ele nem seus layouts carregam "
        f"{ARQUIVO_JS}: o atributo fica inerte e a acao ocorre sem confirmar"
    )


@pytest.mark.parametrize("nome", _templates_com_atributo())
def test_template_com_atributo_alcanca_o_css(nome):
    fontes = _fontes()
    assert _alcanca(nome, ARQUIVO_CSS, fontes, set()), (
        f"{nome} usa data-sa-* mas nao alcanca {ARQUIVO_CSS}"
    )


def test_pagina_de_usuarios_renderiza_com_o_script(app):
    """Prova no HTML final, nao no fonte do template.

    Os testes acima leem `{% extends %}` com expressao regular; este resolve a
    cadeia pelo Jinja de verdade e confere o resultado -- que e o que o
    navegador recebe.
    """

    class _Usuario:
        id = 1
        nome = "Fulano"
        login = "fulano"
        perfil = "admin"
        ativo = True
        ultimo_login_em = None

    outro = _Usuario()
    outro.id = 2
    outro.nome = "Beltrano"

    with app.test_request_context("/usuarios"):
        html = app.jinja_env.get_template("usuarios.html").render(
            usuarios=[outro],
            usuario_atual=_Usuario(),
            perfil_label={"admin": "Administrador"},
        )

    assert ARQUIVO_JS in html, "a pagina renderizada nao carrega o componente"
    assert "data-sa-confirmar" in html, "o botao de excluir perdeu a confirmacao"
    # A ordem importa menos que a presenca (o script e `defer`), mas o botao
    # sem atributo e o atributo sem script sao ambos silenciosos -- conferir os
    # dois juntos e o que distingue "confirma" de "parece que confirma".


def test_login_nao_pede_o_componente(app):
    """A pagina de login dispensa o componente, e isso e deliberado.

    `sharedauth_ui.static` nao e isento de login: para quem ainda nao entrou os
    dois arquivos respondem 302 para o proprio login, e o navegador recusa
    `text/html` onde esperava CSS e JS. Pedi-los ali produz dois erros de
    console a cada carga e nenhum beneficio -- a pagina nao tem `data-sa-`.

    O teste existe para que a remocao continue sendo uma decisao. Se alguem
    puser confirmacao no login, este teste reprova e obriga a escolha certa:
    isentar o endpoint, e nao voltar com o pedido que redireciona.
    """
    with app.test_request_context("/login"):
        html = app.jinja_env.get_template("login.html").render(erro=None, proxima="/")

    assert ARQUIVO_JS not in html
    assert ARQUIVO_CSS not in html
    assert "data-sa-" not in html, (
        "o login ganhou confirmacao: isente `sharedauth_ui.static` em "
        "ENDPOINTS_ISENTOS_DE_LOGIN antes de voltar a carregar o componente"
    )
