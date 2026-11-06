#!/usr/bin/env bash

set -Eeuo pipefail
cd "$(dirname "$0")"

project="${E2E_PROJECT_NAME:-scansync-e2e-$$}"
artifacts="$PWD/tests/e2e/artifacts"
compose=(docker compose -p "$project" -f docker-compose.e2e.yml)

mkdir -p "$artifacts"
find "$artifacts" -type f -delete

cleanup() {
    exit_code=$?
    trap - EXIT
    "${compose[@]}" ps -a > "$artifacts/compose-ps.txt" 2>&1 || true
    "${compose[@]}" logs --no-color > "$artifacts/compose.log" 2>&1 || true
    "${compose[@]}" down --volumes --remove-orphans || true
    exit "$exit_code"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

"${compose[@]}" config --quiet
build_flag=--build
if [[ "${SCANSYNC_PREBUILT:-0}" == "1" ]]; then
    build_flag=--no-build
fi
"${compose[@]}" up "$build_flag" -d --wait --wait-timeout 180 --scale e2e=0
"${compose[@]}" run --rm --no-deps e2e "$@"
