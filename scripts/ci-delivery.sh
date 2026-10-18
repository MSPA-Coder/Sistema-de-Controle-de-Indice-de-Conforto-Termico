#!/usr/bin/env bash
# Runner da CI; ferramentas e verificações de projeto somente em Docker.
set -euo pipefail
: "${ARTIFACT_REVISION:?}" "${ARTIFACT_RUN:?}" "${RUNNER_TEMP:?}"
app=conforto-termico:local
pg=mspa-postgres:17-alpine
quality=conforto-termico-quality:ci
compose=(docker compose -p conforto-termico-ci -f compose.yaml -f compose.ci.yaml --profile quality)
browser=(docker compose -p conforto-termico-browser-ci -f compose.browser.yaml)
cleanup() {
    "${browser[@]}" down --remove-orphans
    "${compose[@]}" down --remove-orphans
}
trap cleanup EXIT
"${compose[@]}" config --quiet
docker build --pull --no-cache --target runtime \
    --secret id=local_ca,src=.certs/local-root-ca.crt \
    --build-arg "ARTIFACT_REVISION=$ARTIFACT_REVISION" --build-arg "ARTIFACT_RUN=$ARTIFACT_RUN" -t "$app" .
docker build --pull --no-cache -f docker/sandbox-postgres/Dockerfile \
    --build-arg "ARTIFACT_REVISION=$ARTIFACT_REVISION" --build-arg "ARTIFACT_RUN=$ARTIFACT_RUN" -t "$pg" .
app_id=$(docker image inspect --format '{{.Id}}' "$app")
pg_id=$(docker image inspect --format '{{.Id}}' "$pg")
for image in "$app" "$pg"; do
    test "$(docker image inspect --format '{{.Os}}/{{.Architecture}}' "$image")" = "${EXPECTED_PLATFORM:-linux/arm64}"
done
# Ferramentas SOBRE a candidata. A suíte compara com o inventário anterior.
docker build -f Dockerfile.verify --build-arg "RUNTIME_IMAGE=$app" -t "$quality" .
"${compose[@]}" up -d --no-build --pull never --wait --wait-timeout 120 postgres-teste
"${compose[@]}" run --rm --no-deps quality
"${compose[@]}" run --rm --no-deps quality pip-audit --progress-spinner=off --cache-dir /tmp/pip-audit-cache
export BROWSER_APP_IMAGE="$app" BROWSER_POSTGRES_IMAGE="$pg"
"${browser[@]}" build browser-tests
"${browser[@]}" up -d --no-build --pull never --wait --wait-timeout 120 browser-coletor
"${browser[@]}" run --rm browser-tests
for pair in "$app_id imagem" "$pg_id postgres"; do
    read -r id file <<<"$pair"
    docker save "$id" -o "$RUNNER_TEMP/$file.tar"
    chmod 0644 "$RUNNER_TEMP/$file.tar"
    docker compose -f .github/docker-compose.yml run --rm trivy \
        --cache-dir /tmp/trivy-cache image --input "/varredura/$file.tar" \
        --scanners vuln --severity HIGH,CRITICAL --ignore-unfixed --exit-code 1 --format table
done
test "$(docker image inspect --format '{{.Id}}' "$app")" = "$app_id"
test "$(docker image inspect --format '{{.Id}}' "$pg")" = "$pg_id"
printf 'app=%s\npostgres=%s\n' "$app_id" "$pg_id" > "$RUNNER_TEMP/candidate.env"
