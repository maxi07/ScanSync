#!/bin/bash

set -e

COMPOSE_FILE="docker-compose.test.yml"
TEST_SERVICE_NAME="test_service"
export COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-scansync-test}"

cleanup() {
  docker compose -f "$COMPOSE_FILE" down -v
}
trap cleanup EXIT

echo "🧪 Running JS tests..."
npm run test:js

echo "🧪 Starting tests with Docker Compose..."

BUILD_FLAG=--build
if [[ "${SCANSYNC_PREBUILT:-0}" == "1" ]]; then
  BUILD_FLAG=--no-build
fi
docker compose -f "$COMPOSE_FILE" up "$BUILD_FLAG" --abort-on-container-exit --exit-code-from "$TEST_SERVICE_NAME"

echo "Tests successful!"