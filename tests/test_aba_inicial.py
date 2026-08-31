"""A aplicacao abre com uma aba aberta.

Este arquivo existe por causa de um defeito que so aparecia usando o sistema:
`rotas_comuns.index` renderizava `index.html` SEM passar `aba_inicial`, e o
template compara essa variavel com o nome da aba em quatro lugares. Comparacao
com o Undefined do Jinja da False em silencio -- entao nenhuma aba nascia
marcada, todos os paineis nasciam com `oculto`, e a tela abria vazia. So
aparecia conteudo depois do primeiro clique.

Nada apanhava isso: `ativarAba` (app.js) so esta ligada ao clique, nao ao
carregamento; a variavel nao existia, entao nao havia o que quebrar; e a suite
nao olhava o HTML renderizado. Um Jinja com `StrictUndefined` teria gritado, e
vale considerar -- mas o que fecha o buraco de verdade e medir o resultado.

Mede-se o HTML de verdade, para cada perfil, porque a pergunta e sobre o que a
pessoa ve.
"""

from __future__ import annotations

import re

import pytest
from sharedauth.session import marca_de_sessao

from app import auth

#: Qualquer atributo `data-aba="x"` de botao de aba no HTML renderizado.
_BOTAO_ATIVO = re.compile(r'<button class="aba-botao ativo"[^>]*data-aba="([^"]+)"')
_PAINEL_VISIVEL = re.compile(r'class="[^"]*aba-conteudo"[^>]*data-aba-conteudo="([^"]+)"')


@pytest.fixture
def abrir(app, client, monkeypatch):
    """Carrega a pagina inicial como um perfil, sem tocar o banco."""

    def carregar(perfil: str) -> str:
        monkeypatch.setattr(
            auth.db,
            "obter_usuario",
            lambda _id: {
                "id": 1,
                "nome": "Fulano",
                "login": "fulano",
                "perfil": perfil,
                "ativo": True,
            },
        )
        # A sessao carrega tambem a marca da senha em vigor: sem ela, o
        # carregamento a recusa (ver `registrar_carregamento_usuario`). O hash
        # e substituido junto, para a marca ser calculavel sem banco.
        monkeypatch.setattr(auth.db, "obter_hash_de_senha", lambda _id: "hash-de-teste")
        with client.session_transaction() as sessao:
            sessao["usuario_id"] = 1
            sessao[auth.CHAVE_MARCA_DE_SENHA] = marca_de_sessao(
                "hash-de-teste", chave_secreta=app.secret_key
            )
        resposta = client.get("/")
        assert resposta.status_code == 200
        return resposta.get_data(as_text=True)

    return carregar


@pytest.mark.parametrize("perfil", sorted(auth.AREAS_POR_PERFIL))
def test_cada_perfil_abre_com_exatamente_uma_aba(abrir, perfil):
    html = abrir(perfil)

    ativos = _BOTAO_ATIVO.findall(html)
    visiveis = _PAINEL_VISIVEL.findall(html)

    assert len(ativos) == 1, f"{perfil} abriu com {len(ativos)} abas marcadas: {ativos}"
    assert len(visiveis) == 1, f"{perfil} abriu com {len(visiveis)} paineis visiveis: {visiveis}"
    assert ativos == visiveis, (
        f"{perfil} marcou a aba {ativos} e mostrou o painel {visiveis} -- precisam ser a mesma."
    )


@pytest.mark.parametrize("perfil", sorted(auth.AREAS_POR_PERFIL))
def test_a_aba_que_abre_e_uma_que_o_perfil_pode_ver(abrir, perfil):
    aba = _BOTAO_ATIVO.findall(abrir(perfil))[0]
    area = dict(auth.ABAS_NA_ORDEM)[aba]

    assert auth.area_permitida(perfil, area), (
        f"{perfil} abriu na aba {aba}, que exige a area {area} -- que ele nao tem."
    )


@pytest.mark.parametrize("perfil", sorted(auth.AREAS_POR_PERFIL))
def test_nenhum_perfil_fica_sem_aba(perfil):
    assert auth.primeira_aba_permitida(perfil) is not None, (
        f"{perfil} nao tem nenhuma aba: a tela abriria vazia de novo."
    )


#: Areas que existem sem virar aba da SPA, com o motivo.
AREAS_SEM_ABA: dict[str, str] = {
    "usuarios": (
        "a administracao de usuarios e uma pagina propria (`usuarios_bp`), "
        "fora da SPA -- chega pelo link 'Gerenciar usuarios' no cabecalho, "
        "nao por aba."
    ),
}


def test_o_mapa_de_abas_cobre_as_areas_que_viram_aba():
    """As abas e as areas nao podem divergir em silencio.

    `ABAS_NA_ORDEM` e a traducao area -> aba. Uma area nova que ganhe aba sem
    entrar aqui volta ao problema: a aba existe no template e nunca e
    escolhida como inicial. E uma area que deixe de ter aba precisa dizer
    para onde foi, em vez de sumir da lista sem explicacao.
    """
    areas_das_abas = {area for _, area in auth.ABAS_NA_ORDEM}
    areas_dos_perfis = set().union(*auth.AREAS_POR_PERFIL.values())

    inventadas = sorted(areas_das_abas - areas_dos_perfis)
    assert not inventadas, f"Abas exigem areas que nao existem: {inventadas}"

    sem_aba = sorted(areas_dos_perfis - areas_das_abas)
    assert sem_aba == sorted(AREAS_SEM_ABA), (
        f"Areas sem aba mudaram: {sem_aba}. Se a area ganhou aba, "
        "acrescente-a a ABAS_NA_ORDEM; se ela vive fora da SPA, declare-a "
        "em AREAS_SEM_ABA com o motivo."
    )


def test_perfil_desconhecido_nao_recebe_aba():
    # Mesmo padrao do resto do modulo: perfil fora do mapa cai no mais
    # restritivo. Aqui isso significa nenhuma aba, nao a primeira da lista.
    assert auth.primeira_aba_permitida("perfil-que-nao-existe") is None
