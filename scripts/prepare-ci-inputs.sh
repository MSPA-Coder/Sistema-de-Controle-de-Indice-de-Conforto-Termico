#!/usr/bin/env bash
# Constantes públicas para contêineres descartáveis; nunca dados operacionais.
set -euo pipefail
: "${RUNNER_TEMP:?}"
umask 077
mkdir -p .certs .secrets .browser-results "$RUNNER_TEMP/trivy-cache"
openssl req -x509 -newkey rsa:2048 -nodes -days 1 \
    -keyout "$RUNNER_TEMP/ci-ca.key" -out .certs/local-root-ca.crt -subj "/CN=CI ephemeral CA"
rm -f "$RUNNER_TEMP/ci-ca.key"
for file in postgres_password postgres_app_password secret_key internal_read_token internal_control_token; do
    printf '%s\n' "synthetic-ci-only-$file-not-operational" > ".secrets/$file.txt"
done
chmod 0644 .secrets/*.txt
chmod 0777 .browser-results "$RUNNER_TEMP/trivy-cache"
