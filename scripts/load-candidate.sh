#!/usr/bin/env bash
# O manifesto contém só IDs; nunca executar seu conteúdo como shell.
set -euo pipefail
app_id=
pg_id=
while IFS='=' read -r key id; do
    [[ "$id" =~ ^sha256:[a-f0-9]{64}$ ]] || exit 1
    case "$key" in
        app) app_id=$id ;;
        postgres) pg_id=$id ;;
        *) exit 1 ;;
    esac
done < "${RUNNER_TEMP:?}/candidate.env"
test -n "$app_id" && test -n "$pg_id"
docker load -i "$RUNNER_TEMP/imagem.tar"
docker load -i "$RUNNER_TEMP/postgres.tar"
for id in "$app_id" "$pg_id"; do
    test "$(docker image inspect --format '{{.Id}}' "$id")" = "$id"
    test "$(docker image inspect --format '{{.Os}}/{{.Architecture}}' "$id")" = "${EXPECTED_PLATFORM:-linux/arm64}"
    test "$(docker image inspect --format '{{index .Config.Labels "org.opencontainers.image.revision"}} {{index .Config.Labels "br.com.mspa.ci-run"}}' "$id")" = "$ARTIFACT_REVISION $ARTIFACT_RUN"
done
docker tag "$app_id" conforto-termico:local
docker tag "$pg_id" mspa-postgres:17-alpine
printf 'DELIVERY_APP_ID=%s\nDELIVERY_POSTGRES_ID=%s\n' "$app_id" "$pg_id" >> "${GITHUB_ENV:?}"
