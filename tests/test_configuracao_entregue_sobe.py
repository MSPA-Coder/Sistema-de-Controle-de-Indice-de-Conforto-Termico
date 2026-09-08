"""O que o repositório entrega tem de ser inicializável, não só seguro.

POR QUE ESTE ARQUIVO EXISTE

Em 02/09/2026 a correção CT-02 acrescentou `app_factory._validar_transporte`,
que recusa a inicialização quando o cookie de sessão sairia sem `Secure` e a
escuta não é loopback. A guarda está certa.

O que ninguém revisitou foi o outro lado: o `compose.yaml` fixa
`CONFORTO_HOST: 0.0.0.0` -- e não há alternativa, porque em contêiner escutar
em loopback torna a porta publicada inalcançável --, enquanto o padrão de
`CONFORTO_COOKIE_SEGURO` continuava `0`, de 19/08. A combinação que o
repositório entregava, portanto, **não subia**: o `ict` morria no arranque.

O defeito passou despercebido por três semanas, e a razão importa mais que o
defeito: a CI executa o estágio `quality`, que roda testes e linters mas
**não levanta o `ict`**; e a pilha local de quem desenvolve seguia servindo uma
imagem construída antes da guarda, porque `docker compose up -d` sem `--build`
reaproveita a imagem que já existe. Nenhum dos dois caminhos jamais executou a
configuração entregue.

Este teste executa. Não sobe contêiner: lê os valores que o repositório
declara e submete a combinação à mesma função que decide no arranque real.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from sharedauth.config import ler_flag

from app.app_factory import HOSTS_LOOPBACK, AppConfig, _validar_transporte

RAIZ = Path(__file__).resolve().parents[1]

#: `${VAR:-padrao}` do Compose: o que vale quando ninguém define a variável.
PADRAO_COMPOSE = re.compile(
    r"CONFORTO_COOKIE_SEGURO:\s*\$\{CONFORTO_COOKIE_SEGURO:-([^}]*)\}"
)
VALOR_ENV = re.compile(r"^CONFORTO_COOKIE_SEGURO=(.*)$", re.M)
HOST_COMPOSE = re.compile(r"CONFORTO_HOST:\s*(\S+)")


def _bool_declarado(bruto: str, monkeypatch) -> bool:
    """Interpreta o valor com a MESMA função que a aplicação usa.

    Não vale codificar aqui o que conta como verdadeiro: se `ler_flag` mudar de
    ideia sobre `"0"`, `"nao"` ou `""`, este teste tem de mudar junto.
    """
    monkeypatch.setenv("CONFORTO_COOKIE_SEGURO", bruto.strip())
    return ler_flag("CONFORTO_COOKIE_SEGURO", padrao=False, estrito=False)


def _config(host: str) -> AppConfig:
    # Só `host` importa para `_validar_transporte`; o resto é o mínimo que o
    # dataclass exige.
    return AppConfig(
        debug=False,
        host=host,
        port=5000,
        threaded=True,
        max_content_length=1024 * 1024,
    )


def test_o_compose_declara_escuta_fora_de_loopback():
    """Controle: se um dia o compose escutar em loopback, o resto muda de sentido."""
    hosts = HOST_COMPOSE.findall((RAIZ / "compose.yaml").read_text(encoding="utf-8"))

    assert hosts, "nenhum CONFORTO_HOST no compose.yaml -- o arquivo mudou de forma"
    assert all(h not in HOSTS_LOOPBACK for h in hosts), (
        f"CONFORTO_HOST em loopback no compose: {hosts}. Em contêiner isso torna "
        "a porta publicada inalcançável; se foi deliberado, este arquivo inteiro "
        "precisa ser reavaliado."
    )


def test_o_padrao_do_compose_consegue_iniciar(monkeypatch):
    texto = (RAIZ / "compose.yaml").read_text(encoding="utf-8")
    padroes = PADRAO_COMPOSE.findall(texto)
    hosts = HOST_COMPOSE.findall(texto)

    assert padroes, "o compose deixou de declarar padrão para CONFORTO_COOKIE_SEGURO"

    for padrao in padroes:
        seguro = _bool_declarado(padrao, monkeypatch)
        for host in hosts:
            _validar_transporte(_config(host), seguro)


def test_o_env_de_exemplo_local_consegue_iniciar(monkeypatch):
    """É o arquivo que a pessoa copia para `.env.docker` antes do primeiro `up`."""
    achados = VALOR_ENV.findall((RAIZ / ".env.docker.example").read_text(encoding="utf-8"))

    assert len(achados) == 1, f"esperava uma declaração, achei {len(achados)}"

    seguro = _bool_declarado(achados[0], monkeypatch)
    for host in HOST_COMPOSE.findall((RAIZ / "compose.yaml").read_text(encoding="utf-8")):
        _validar_transporte(_config(host), seguro)


def test_a_guarda_continua_recusando_o_que_deve_recusar():
    """Controle negativo: sem ele, os dois acima passariam com a guarda morta."""
    with pytest.raises(RuntimeError, match="CONFORTO_COOKIE_SEGURO"):
        _validar_transporte(_config("0.0.0.0"), False)
