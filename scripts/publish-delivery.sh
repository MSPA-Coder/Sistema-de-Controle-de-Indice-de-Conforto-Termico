#!/usr/bin/env bash
# Publica os IDs aprovados. Sem build ou troca de tag candidata.
set -euo pipefail
: "${DELIVERY_APP_ID:?}" "${DELIVERY_POSTGRES_ID:?}" "${ARTIFACT_RUN:?}"
test "${GITHUB_REF:?}" = refs/heads/main
test "${GITHUB_EVENT_NAME:?}" != pull_request
registry=ghcr.io/mspa-coder/conforto-termico
test "$(docker image inspect --format '{{.Id}}' conforto-termico:local)" = "$DELIVERY_APP_ID"
test "$(docker image inspect --format '{{.Id}}' mspa-postgres:17-alpine)" = "$DELIVERY_POSTGRES_ID"
auth_dir="${RUNNER_TEMP:?}/registry-auth"
install -d -m 700 "$auth_dir"
trap 'docker --config "$auth_dir" logout ghcr.io >/dev/null; rm -f "$auth_dir/config.json"' EXIT
printf '%s' "${REGISTRY_TOKEN:?}" | docker --config "$auth_dir" login ghcr.io --username "${GITHUB_ACTOR:?}" --password-stdin
for pair in "$DELIVERY_APP_ID $registry" "$DELIVERY_POSTGRES_ID $registry-postgres"; do
    read -r id destination <<<"$pair"
    tag="$destination:run-$ARTIFACT_RUN"
    test "$(docker image inspect --format '{{index .Config.Labels "org.opencontainers.image.revision"}} {{index .Config.Labels "br.com.mspa.ci-run"}}' "$id")" = "$ARTIFACT_REVISION $ARTIFACT_RUN"
    docker tag "$id" "$tag"
    docker --config "$auth_dir" push "$tag"
    test "$(docker image inspect --format '{{.Id}}' "$tag")" = "$id"
    printf '%s\n' "$tag" >> "${GITHUB_STEP_SUMMARY:?}"
done
