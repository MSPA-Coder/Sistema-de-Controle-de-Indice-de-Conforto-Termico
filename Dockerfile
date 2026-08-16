# syntax=docker/dockerfile:1.7
FROM python:3.13-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONFAULTHANDLER=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /workspace

RUN --mount=type=secret,id=local_ca,required=false \
    if [ -f /run/secrets/local_ca ]; then \
        cp /run/secrets/local_ca /usr/local/share/ca-certificates/local-root-ca.crt; \
    fi \
    && apt-get update \
    && apt-get install --no-install-recommends -y postgresql-client \
    && update-ca-certificates \
    && rm -rf /var/lib/apt/lists/*

FROM base AS runtime-dependencies
COPY requirements.txt .
RUN python -m pip install --no-cache-dir -r requirements.txt

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
USER app
CMD ["python", "run_ict.py"]

# -----------------------------------------------------------------------
# quality: Ruff e a suite minima de seguranca. Nunca e a imagem servida --
# `compose.yaml` usa `runtime` para schema, coletor e ict.
# -----------------------------------------------------------------------
FROM runtime AS quality
USER root
COPY requirements-dev.txt .
RUN python -m pip install --no-cache-dir -r requirements-dev.txt
COPY --chown=app:app pyproject.toml ./
COPY --chown=app:app tests ./tests
ENV RUFF_CACHE_DIR=/tmp/ruff-cache \
    PYTEST_ADDOPTS="-o cache_dir=/tmp/pytest-cache"
USER app
CMD ["sh", "-c", "ruff check . && pytest"]
