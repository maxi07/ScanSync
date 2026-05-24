# Copilot Instructions for ScanSync

## Project Overview

ScanSync is a Python-based document management application that uses Docker microservices to scan, OCR, rename, and sync documents to OneDrive. It consists of several services communicating via RabbitMQ.

## Architecture

The project is a multi-service architecture with each service in its own directory:

- **`web_service/`** – Flask web UI and API (Python + Jinja2 + JS/CSS frontend)
- **`detection_service/`** – Monitors for new scanned documents
- **`ocr_service/`** – Performs OCR using OCRmyPDF
- **`metadata_service/`** – Extracts and stores PDF metadata
- **`file_naming_service/`** – AI-powered file renaming (OpenAI / Ollama)
- **`upload_service/`** – Uploads processed files to OneDrive
- **`smb_service/`** – SMB server for scanner connectivity
- **`scansynclib/`** – Shared Python library (installed as a package) with helpers, config, DB wrapper, settings, and API clients
- **`tests/`** – Pytest test suite

Services communicate through **RabbitMQ** message queues and share state via an **SQLite** database (through `scansynclib`). **Redis** is used for caching in the file naming service.

## Languages & Frameworks

- **Backend**: Python 3.13, Flask, Gunicorn, Gevent
- **Frontend**: JavaScript, HTML (Jinja2 templates), CSS
- **Infrastructure**: Docker, Docker Compose

## Development Commands

### Testing
- Tests run inside Docker: `./run-tests.sh` (uses `docker-compose.test.yml`)
- Direct pytest (if dependencies installed): `pytest` (configured in `pytest.ini`, test directory is `tests/`)

### Linting
- **Python**: `flake8` (config in `.flake8`, max line length 150)
- **JavaScript/CSS/JSON/Markdown**: `npx eslint` (config in `eslint.config.mjs`)

### Building
- `docker compose up --build -d` to build and start all services

## Coding Conventions

### Python
- Follow PEP 8 with a max line length of 150 characters
- Use the shared library `scansynclib` for cross-service functionality (logging, config, DB access, settings)
- Use `scansynclib.logging` for consistent log formatting across services
- Flake8 ignores: E501 (line too long), F403/F405 (wildcard imports), E402 (module-level import order)

### JavaScript
- Use 4-space indentation
- Always use semicolons
- Use `const`/`let` instead of `var` (`no-var` rule enforced)
- Object curly spacing enabled
- No space before function parentheses

### General
- Each microservice has its own `Dockerfile` and `requirements.txt`
- Shared Python code goes in `scansynclib/`
- Frontend static assets live in `web_service/src/static/`
- Flask routes are organized in `web_service/src/routes/`
