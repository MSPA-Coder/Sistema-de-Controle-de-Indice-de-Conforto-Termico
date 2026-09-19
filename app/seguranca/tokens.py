"""Tokens de capacidade usados na API privada do coletor.

O token bruto é somente a raiz de provisionamento. Nunca é enviado por HTTP:
o valor apresentado ao coletor é derivado com um rótulo de capacidade, de
modo que um token de leitura não seja aceito em uma rota de controle mesmo
quando ambos os processos ainda usam o arquivo de segredo legado durante a
transição do provisionador.
"""

from __future__ import annotations

import contextlib
import hashlib
import hmac
import os
import secrets
from pathlib import Path

from sharedauth.secrets import DIRETORIO_SECRETS_COMPOSE, resolver_segredo

from .. import database as db

CAPACIDADE_LEITURA = "leitura"
CAPACIDADE_CONTROLE = "controle"
CAPACIDADES_INTERNAS = frozenset({CAPACIDADE_LEITURA, CAPACIDADE_CONTROLE})

_ENV_DIRETO = {
    CAPACIDADE_LEITURA: "CONFORTO_INTERNO_TOKEN_LEITURA",
    CAPACIDADE_CONTROLE: "CONFORTO_INTERNO_TOKEN_CONTROLE",
}
_ENV_ARQUIVO = {nome: f"{nome}_FILE" for nome in _ENV_DIRETO.values()}
_ARQUIVO_COMPOSE = {
    CAPACIDADE_LEITURA: DIRETORIO_SECRETS_COMPOSE / "internal_read_token",
    CAPACIDADE_CONTROLE: DIRETORIO_SECRETS_COMPOSE / "internal_control_token",
}


def _validar_capacidade(capacidade: str) -> str:
    if capacidade not in CAPACIDADES_INTERNAS:
        raise ValueError(f"Capacidade interna desconhecida: {capacidade!r}.")
    return capacidade


def _ambiente_permite_gerar() -> bool:
    return any(
        os.environ.get(nome, "").strip().lower() in {"1", "true", "sim", "on"}
        for nome in ("CONFORTO_DEVELOPMENT", "CONFORTO_TESTING")
    )


def _ler_raiz_configurada(capacidade: str) -> str | None:
    nome = _ENV_DIRETO[capacidade]
    valor = os.environ.get(nome)
    if valor:
        return valor.strip()

    arquivo = resolver_segredo(
        nome,
        aceitar_variavel=False,
        caminho_esperado=_ARQUIVO_COMPOSE[capacidade],
    )
    return arquivo.strip() if arquivo else None


def _caminho_desenvolvimento(capacidade: str) -> Path:
    return Path(db.INSTANCE_DIR) / f"interno_token_{capacidade}.txt"


def _obter_raiz(capacidade: str) -> str:
    raiz = _ler_raiz_configurada(capacidade)
    if raiz:
        return raiz

    if not _ambiente_permite_gerar():
        nome = _ENV_DIRETO[capacidade]
        arquivo = _ENV_ARQUIVO[nome]
        raise RuntimeError(
            f"Token interno de {capacidade} ausente. Em produção, defina "
            f"{arquivo} apontando para /run/secrets/"
            f"{'internal_read_token' if capacidade == CAPACIDADE_LEITURA else 'internal_control_token'} "
            f"ou {nome}. Não há fallback para o token da outra capacidade."
        )

    caminho = _caminho_desenvolvimento(capacidade)
    try:
        existente = caminho.read_text(encoding="utf-8").strip()
    except OSError:
        existente = ""
    if existente:
        return existente

    novo = secrets.token_urlsafe(48)
    try:
        caminho.parent.mkdir(parents=True, exist_ok=True)
        caminho.write_text(novo, encoding="utf-8")
        with contextlib.suppress(OSError):
            os.chmod(caminho, 0o600)
    except OSError:
        # Em um filesystem somente leitura, o valor continua válido para o
        # processo de desenvolvimento atual; produção já falha acima.
        pass
    return novo


def obter_token_interno(capacidade: str) -> str:
    """Retorna o bearer derivado exclusivamente para ``capacidade``."""
    capacidade = _validar_capacidade(capacidade)
    raiz = _obter_raiz(capacidade).encode("utf-8")
    rotulo = f"conforto-termico/api-interna/{capacidade}/v1".encode("ascii")
    return hmac.new(raiz, rotulo, hashlib.sha256).hexdigest()


def tokens_de_capacidade_diferentes() -> bool:
    """Confere a propriedade estrutural usada pelos testes de segurança."""
    return obter_token_interno(CAPACIDADE_LEITURA) != obter_token_interno(CAPACIDADE_CONTROLE)
