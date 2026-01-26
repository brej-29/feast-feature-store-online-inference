.PHONY: help setup lint format test docker-up docker-down

PYTHON := python
PIP := pip

help:
	@echo "Available targets:"
	@echo "  setup        - Create virtual env and install dependencies"
	@echo "  lint         - Run Ruff linting"
	@echo "  format       - Run Black code formatter"
	@echo "  test         - Run pytest test suite"
	@echo "  docker-up    - Build and start local Docker stack"
	@echo "  docker-down  - Stop local Docker stack and remove volumes"

setup:
	$(PYTHON) -m venv .venv
	. .venv/bin/activate && $(PIP) install --upgrade pip
	. .venv/bin/activate && $(PIP) install -r requirements.txt -r requirements-dev.txt

lint:
	. .venv/bin/activate && ruff check .

format:
	. .venv/bin/activate && black .

test:
	. .venv/bin/activate && pytest

docker-up:
	docker compose up --build

docker-down:
	docker compose down -v