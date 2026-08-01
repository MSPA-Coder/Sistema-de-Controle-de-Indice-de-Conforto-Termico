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

COPY --chown=app:app alembic.ini run_ict.py run_coletor.py ./
COPY --chown=app:app app ./app
COPY --chown=app:app config ./config
COPY --chown=app:app migrations ./migrations
COPY --chown=app:app scripts ./scripts

EXPOSE 5000
USER app
CMD ["python", "run_ict.py"]

FROM runtime AS quality
USER root
COPY requirements-dev.txt .
RUN python -m pip install --no-cache-dir -r requirements-dev.txt
COPY --chown=app:app tests ./tests
COPY --chown=app:app ruff.toml mypy.ini ./
USER app
