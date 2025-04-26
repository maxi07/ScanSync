#!/bin/bash

set -e

COMPOSE_FILE="docker-compose.test.yml"
TEST_SERVICE_NAME="test_service"

echo "🧪 Starting tests with Docker Compose..."

docker-compose -f $COMPOSE_FILE up --build --abort-on-container-exit --exit-code-from $TEST_SERVICE_NAME

EXIT_CODE=$?

echo "🧹 Shutting down containers..."
docker-compose -f $COMPOSE_FILE down -v

if [ $EXIT_CODE -eq 0 ]; then
  echo "✅ Tests successful!"
else
  echo "❌ Tests failed!"
fi

exit $EXIT_CODE