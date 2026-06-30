# Git Version (Tag or Commit-Hash)
GIT_VERSION := $(shell git describe --tags --always --dirty 2>/dev/null || echo "dev")
APP_VERSION ?= $(GIT_VERSION)
export APP_VERSION

# Variables
DOCKER_COMPOSE = docker compose -f docker-compose.yml

# Help (default target)
.PHONY: help
help:
	@echo "ScanSync - Makefile Commands"
	@echo "================================"
	@echo ""
	@echo "  Current version: $(GIT_VERSION)"
	@echo ""
	@echo "🚀 Production:"
	@echo "  start         - Build and start all services"
	@echo "  stop          - Stop all services"
	@echo "  restart       - Restart all services"
	@echo "  logs          - Show live logs"
	@echo "  build         - Build all images"
	@echo ""
	@echo "🔧 General:"
	@echo "  status        - Show the status of all containers"
	@echo "  clean         - Stop all containers and remove unused images"
	@echo "  clean-all     - Full cleanup (containers, images, volumes)"
	@echo "  test          - Run the tests"
	@echo ""

# Production
.PHONY: start
start:
	@echo "Starting ScanSync (Version: $(GIT_VERSION))..."
	$(DOCKER_COMPOSE) up --build -d

.PHONY: stop
stop:
	$(DOCKER_COMPOSE) down

.PHONY: restart
restart: stop start

.PHONY: logs
logs:
	$(DOCKER_COMPOSE) logs -f

.PHONY: build
build:
	@echo "Building ScanSync (Version: $(GIT_VERSION))..."
	$(DOCKER_COMPOSE) build

# General
.PHONY: status
status:
	$(DOCKER_COMPOSE) ps

.PHONY: clean
clean:
	$(DOCKER_COMPOSE) down --rmi local

.PHONY: clean-all
clean-all:
	$(DOCKER_COMPOSE) down --rmi all -v

.PHONY: test
test:
	./run-tests.sh
