# syntax=docker/dockerfile:1.7
FROM python:3.15-slim AS base

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

# Cada build instala os pacotes Debian corrigidos disponíveis no momento. A CI
# semanal reconstrói com `--pull`, roda a suíte e bloqueia CVEs HIGH/CRITICAL
# corrigíveis antes que a imagem seja adotada.
RUN apt-get update \
    && apt-get upgrade -y --no-install-recommends \
    && apt-get install --no-install-recommends -y \
       ca-certificates git postgresql-client openssl openssl-provider-legacy libpcre2-8-0 \
    && rm -rf /var/lib/apt/lists/* \
    && python -m pip install --no-cache-dir --upgrade \
       pip setuptools

FROM base AS runtime-dependencies
COPY pyproject.toml README.md constraints.txt ./
COPY app ./app
# `sharedauth` é fixado por commit no pyproject.toml. O arquivo de constraints
# fixa os demais pacotes transitivos e de qualidade.
RUN --mount=type=cache,target=/root/.cache/pip \
    PIP_CONSTRAINT=/workspace/constraints.txt python -m pip install -c constraints.txt .

FROM runtime-dependencies AS runtime
ARG ARTIFACT_REVISION=local
ARG ARTIFACT_RUN=local
LABEL org.opencontainers.image.source="https://github.com/MSPA-Coder/Sistema-de-Controle-de-Indice-de-Conforto-Termico" \
      org.opencontainers.image.revision="${ARTIFACT_REVISION}" \
      br.com.mspa.ci-run="${ARTIFACT_RUN}"
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
# Tira pip e setuptools da imagem SERVIDA. São ferramentas de build e não têm
# uso no runtime; a verificação falha se qualquer executável continuar no PATH.
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
# quality: Ruff e a suíte mínima de segurança. Nunca é a imagem servida.
# -----------------------------------------------------------------------
FROM runtime AS quality
USER root
RUN python -m ensurepip --upgrade \
    && python -m pip --version
RUN --mount=type=cache,target=/root/.cache/pip \
    PIP_CONSTRAINT=/workspace/constraints.txt python -m pip install -c constraints.txt ".[dev]"
COPY --chown=app:app pyproject.toml ./
COPY --chown=app:app tests ./tests
COPY --chown=app:app compose.yaml .env.docker.example ./
ENV RUFF_CACHE_DIR=/tmp/ruff-cache \
    PYTEST_ADDOPTS="-o cache_dir=/tmp/pytest-cache"
USER app
CMD ["sh", "-c", "ruff check . && mypy && pytest"]
