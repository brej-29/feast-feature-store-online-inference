.PHONY: help setup lint format test docker-up docker-down demo

PYTHON := python
PIP := pip
RAW_CSV := $(firstword $(wildcard data/raw/*.csv))

help:
	@echo "Available targets:"
	@echo "  setup        - Create virtual env and install dependencies"
	@echo "  lint         - Run Ruff linting"
	@echo "  format       - Run Black code formatter"
	@echo "  test         - Run pytest test suite (unit only; see 'test-integration')"
	@echo "  test-integration - Run Testcontainers-backed Feast integration test (needs Docker)"
	@echo "  docker-up    - Build and start local Docker stack"
	@echo "  docker-down  - Stop local Docker stack and remove volumes"
	@echo "  demo         - One-command local demo: ingest -> features -> Feast apply/materialize -> train -> serve"

setup:
	$(PYTHON) -m venv .venv
	. .venv/bin/activate && $(PIP) install --upgrade pip
	. .venv/bin/activate && $(PIP) install -r requirements.txt -r requirements-dev.txt

lint:
	. .venv/bin/activate && ruff check .

format:
	. .venv/bin/activate && black .

test:
	. .venv/bin/activate && pytest -m "not integration"

test-integration:
	. .venv/bin/activate && pytest -m integration

docker-up:
	docker compose up --build

docker-down:
	docker compose down -v

# One-command reproducible demo. Idempotent: each stage is skipped if its
# output already exists, so re-running after a partial failure just resumes.
# Requires: raw Kaggle CSV under data/raw/ (see scripts/kaggle_download.md)
# and Docker (for the local Postgres online store).
demo:
	@echo "==> Starting local Postgres (docker compose)..."
	docker compose up -d postgres
	@if [ ! -f data/processed/transactions_clean.parquet ]; then \
		if [ -z "$(RAW_CSV)" ]; then \
			echo "No raw CSV found under data/raw/. See scripts/kaggle_download.md, then re-run 'make demo'."; \
			exit 1; \
		fi; \
		echo "==> Ingesting $(RAW_CSV)..."; \
		. .venv/bin/activate && python -m pipelines.data_ingest --raw_path $(RAW_CSV) --sample_rows 300000; \
	else \
		echo "==> data/processed/transactions_clean.parquet exists, skipping ingest."; \
	fi
	@if [ ! -f data/processed/customer_features.parquet ]; then \
		echo "==> Building point-in-time entity feature tables..."; \
		. .venv/bin/activate && python -m pipelines.build_entity_tables; \
	else \
		echo "==> Entity feature tables exist, skipping."; \
	fi
	@echo "==> Applying Feast feature definitions..."
	. .venv/bin/activate && bash scripts/feast_apply.sh
	@echo "==> Materializing features to the online store..."
	. .venv/bin/activate && bash scripts/feast_materialize.sh
	@if [ ! -f models/fraud_model_v2.joblib ]; then \
		echo "==> Training model..."; \
		. .venv/bin/activate && python -m pipelines.train_model; \
	else \
		echo "==> models/fraud_model_v2.joblib exists, skipping training."; \
	fi
	@echo "==> Starting app on http://localhost:8000 (UI at /, API at /api/) ..."
	. .venv/bin/activate && uvicorn services.api.app.main:app --host 0.0.0.0 --port 8000