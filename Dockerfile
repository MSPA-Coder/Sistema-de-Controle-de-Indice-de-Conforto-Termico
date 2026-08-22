# syntax=docker/dockerfile:1.7
FROM python:3.14-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONFAULTHANDLER=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /workspace

RUN --mount=type=secret,id=local_ca,required=false \
    if [ -f /run/secrets/local_ca ]; then \
        cp /run/secrets/local_ca /usr/local/share/ca-certificates/local-root-ca.crt; \
        update-ca-certificates; \
    fi

# Correcoes de seguranca da base e das ferramentas de empacotamento.
#
# `apt-get upgrade` porque a `python:3.14-slim` publicada carrega pacotes do
# Debian com CVE ja corrigido a montante; sem isto a correcao so chega quando a
# imagem oficial for republicada. O `setuptools` que vem na base tambem fica
# para tras -- o 70.3.0 tinha CVE-2025-47273, travessia de caminho.
#
# A varredura Trivy exige que a imagem servida incorpore correcoes de CVE já
# publicadas para os pacotes do sistema.
RUN apt-get update \
    && apt-get upgrade -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/* \
    && python -m pip install --no-cache-dir --upgrade pip setuptools

RUN apt-get update \
    && apt-get install --no-install-recommends -y postgresql-client git \
    && rm -rf /var/lib/apt/lists/*

FROM base AS runtime-dependencies
COPY requirements.txt .
# `requirements.txt` inclui `sharedauth` de um repositório Git privado
# (github.com/MSPA-Coder/SharedAuth) -- o secret `github_token` (BuildKit,
# nunca vira camada da imagem) autentica só para este RUN; `git config
# --unset` no fim da mesma instrução remove o token do `.gitconfig` antes de
# commitar a camada. Mesmo mecanismo do MegaSena e do ControleRendaVariavel.
RUN --mount=type=secret,id=github_token \
    git config --global url."https://x-access-token:$(cat /run/secrets/github_token)@github.com/".insteadOf "https://github.com/" \
    && python -m pip install --no-cache-dir -r requirements.txt \
    && git config --global --unset url."https://x-access-token:$(cat /run/secrets/github_token)@github.com/".insteadOf

FROM runtime-dependencies AS runtime
ARG APP_UID=10001
ARG APP_GID=10001
RUN groupadd --gid "${APP_GID}" app \
    && useradd --uid "${APP_UID}" --gid app --no-log-init --create-home app \
    && mkdir -p /workspace/instance \
    && chown app:app /workspace/instance

COPY alembic.ini run_ict.py run_coletor.py ./
COPY app ./app
COPY config ./config
COPY migrations ./migrations
COPY scripts ./scripts

EXPOSE 5000
# Tira `pip` e `setuptools` da imagem SERVIDA.
#
# Sao ferramenta de build e nao tem uso aqui -- e o mesmo raciocinio que ja
# mantem `gcc`, `make` e `wget` fora do runtime, o que os testes de contrato
# deste projeto verificam.
#
# Nao e higiene abstrata: a varredura de vulnerabilidade acusa
# CVE-2025-47273 no `setuptools` e GHSA-6v7p-g79w-8964 no `msgpack` que
# o `pip` carrega vendorizado em `pip/_vendor/`. Nenhum dos dois chega a ser
# executado nesta imagem. Remover apaga as duas descobertas E a superficie,
# em vez de ficar perseguindo versao de pacote que ninguem invoca.
#
# Seguro por medicao, nao por suposicao: os quatro conteineres em producao ja
# rodavam sem `setuptools` antes desta mudanca.
#
# A ultima linha e a propria verificacao: se `pip` continuar no PATH, o build
# falha aqui em vez de entregar uma imagem que so parece limpa.
RUN set -eu; \
    python -m pip check; \
    for raiz in /usr/local/lib/python*/site-packages /opt/venv/lib/python*/site-packages; do \
      [ -d "$raiz" ] || continue; \
      rm -rf "$raiz"/pip "$raiz"/pip-*.dist-info \
             "$raiz"/setuptools "$raiz"/setuptools-*.dist-info \
             "$raiz"/pkg_resources "$raiz"/_distutils_hack \
             "$raiz"/distutils-precedence.pth \
             "$raiz"/wheel "$raiz"/wheel-*.dist-info; \
    done; \
    rm -f /usr/local/bin/pip /usr/local/bin/pip3 /usr/local/bin/pip3.* \
          /opt/venv/bin/pip /opt/venv/bin/pip3 /opt/venv/bin/pip3.*; \
    ! command -v pip

USER app
CMD ["python", "run_ict.py"]

# -----------------------------------------------------------------------
# quality: Ruff e a suite minima de seguranca. Nunca e a imagem servida --
# `compose.yaml` usa `runtime` para schema, coletor e ict.
# -----------------------------------------------------------------------
FROM runtime AS quality
USER root
# O estágio `runtime` acima remove o `pip` da imagem. Este estágio herda dela e
# precisa dele de volta para instalar as dependências de teste. `ensurepip` é o
# mecanismo do próprio Python para isso, não uma gambiarra.
#
# A imagem SERVIDA continua sem `pip`: `quality` está atrás do profile do mesmo
# nome e nunca vai para produção.
RUN python -m ensurepip --upgrade \
    && python -m pip --version
COPY requirements-dev.txt .
RUN --mount=type=secret,id=github_token \
    git config --global url."https://x-access-token:$(cat /run/secrets/github_token)@github.com/".insteadOf "https://github.com/" \
    && python -m pip install --no-cache-dir -r requirements-dev.txt \
    && git config --global --unset url."https://x-access-token:$(cat /run/secrets/github_token)@github.com/".insteadOf
COPY --chown=app:app pyproject.toml ./
COPY --chown=app:app tests ./tests
ENV RUFF_CACHE_DIR=/tmp/ruff-cache \
    PYTEST_ADDOPTS="-o cache_dir=/tmp/pytest-cache"
USER app
CMD ["sh", "-c", "ruff check . && pytest"]
