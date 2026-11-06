# Git Version (Tag or Commit-Hash)
GIT_VERSION := $(shell git describe --tags --always --dirty 2>/dev/null || echo "dev")
APP_VERSION ?= $(GIT_VERSION)
export APP_VERSION

# Variables
DOCKER_COMPOSE = docker compose -f docker-compose.yml
DEV_COMPOSE = $(DOCKER_COMPOSE) -f docker-compose.dev.yml
PYTHON ?= python3
REQUIREMENT_INPUTS = $(sort $(wildcard *_service/requirements.txt) tests/requirements.txt) scansynclib/pyproject.toml
OCR_TEST_IMAGE ?= scansync-ocr-regression

# Help (default target)
.PHONY: help
help:
	@echo "ScanSync - Makefile Commands"
	@echo "================================"
	@echo ""
	@echo "  Current version: $(GIT_VERSION)"
	@echo ""
	@echo "🚀 Production:"
	@echo "  start         - Alias for prod-start"
	@echo "  prod-start    - Start images (build only if missing)"
	@echo "  prod-build    - Build images with cache and fresh base images"
	@echo "  prod-refresh  - Refresh base images and system packages, then start"
	@echo "  stop          - Stop all services"
	@echo "  restart       - Restart all services"
	@echo "  logs          - Show live logs"
	@echo "  build         - Build all images"
	@echo ""
	@echo "Development:"
	@echo "  dev-start     - Cached build and start with mounted source and Flask reload"
	@echo "  dev-restart   - Restart workers after source changes"
	@echo "  dev-stop      - Stop development services"
	@echo "  dev-logs      - Show development logs"
	@echo "  dev-refresh   - Refresh development base images and system packages"
	@echo "  deps-lock     - Resolve pinned Python inputs and refresh transitive versions"
	@echo ""
	@echo "🔧 General:"
	@echo "  status        - Show the status of all containers"
	@echo "  clean         - Stop all containers and remove unused images"
	@echo "  clean-all     - Full cleanup (containers, images, volumes)"
	@echo "  test          - Run the tests"
	@echo "  test-ocr      - Run the real Ghostscript/PDF-A regression test"
	@echo "  test-e2e      - Run real browser/SMB/OCR end-to-end scenarios"
	@echo ""

# Production
.PHONY: start
start: prod-start

.PHONY: prod-start
prod-start:
	@echo "Starting ScanSync (Version: $(GIT_VERSION))..."
	$(DOCKER_COMPOSE) up -d

.PHONY: stop
stop:
	$(DOCKER_COMPOSE) down

.PHONY: restart
restart:
	$(DOCKER_COMPOSE) restart

.PHONY: logs
logs:
	$(DOCKER_COMPOSE) logs -f

.PHONY: build
build: prod-build

.PHONY: prod-build
prod-build:
	@echo "Building ScanSync (Version: $(GIT_VERSION))..."
	$(DOCKER_COMPOSE) build --pull

.PHONY: prod-refresh dev-start dev-restart dev-stop dev-logs dev-refresh deps-lock
prod-refresh:
	$(DOCKER_COMPOSE) pull --ignore-buildable
	$(DOCKER_COMPOSE) build --pull --no-cache
	$(DOCKER_COMPOSE) up -d

dev-start:
	$(DEV_COMPOSE) up --build -d

dev-restart:
	$(DEV_COMPOSE) restart

dev-stop:
	$(DEV_COMPOSE) down

dev-logs:
	$(DEV_COMPOSE) logs -f

dev-refresh:
	$(DEV_COMPOSE) pull --ignore-buildable
	$(DEV_COMPOSE) build --pull --no-cache
	$(DEV_COMPOSE) up -d

deps-lock:
	$(PYTHON) -m piptools compile --upgrade --strip-extras --output-file=requirements-dev.txt $(REQUIREMENT_INPUTS)

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
test: test-ocr
	./run-tests.sh

.PHONY: test-ocr
test-ocr:
	@if test "$(SCANSYNC_PREBUILT)" != "1"; then docker build -f ocr_service/Dockerfile -t $(OCR_TEST_IMAGE) .; fi
	docker run --rm --entrypoint sh -v "$(CURDIR)/tests:/tests:ro" -w /tmp $(OCR_TEST_IMAGE) -c 'pip install -c /tmp/constraints.txt pytest && pytest /tests/test_ocr_verification.py::test_pdfa_preserves_multicharacter_tounicode -q -p no:cacheprovider'

.PHONY: test-e2e
test-e2e:
	bash ./run-e2e-tests.sh $(E2E_ARGS)
