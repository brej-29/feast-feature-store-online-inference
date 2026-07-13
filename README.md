# Feast Fraud Feature Store Skeleton

Step 0–2 scaffold for a free-tier friendly, production-grade feature store stack:

- **Feast Feature Store** with Postgres online store
- **Postgres** for online feature storage
- **Kafka/Redpanda** for streaming events and real-time feature updates
- **FastAPI** backend exposing prediction, health/metrics, and basic Feast endpoints
- **Gradio** UI deployed on **Hugging Face Spaces**
- **Prometheus** metrics and **Nginx** reverse proxy inside the single app container

This repository is intentionally minimal but _runnable_ so that future steps (feature engineering, richer features, training, etc.) stay grounded and consistent.

---

## 1. What this repo provides (Steps 0–3)

### 1.1. Context system

A **context system** under `./context/` that documents:

- Project goal and success metrics
- High-level architecture and request flow
- Free-tier constraints for HF Spaces, Neon/Supabase, and CloudKarafka
- Dataset plan for Kaggle "Online Payments Fraud Detection Dataset"
- Metrics and evaluation plan
- Task protocol for future Cosine AI tasks
- Decisions and change log templates
- Step log tracking major changes

### 1.2. Services and infra

- **FastAPI service** (`services/api/app/main.py`) exposing:
  - `GET /health` and `GET /api/health` → `{"status": "ok"}`
  - `GET /metrics` → Prometheus metrics (via `prometheus_client`)
  - `POST /api/predict` → model-backed fraud prediction with latency breakdowns
  - `GET /api/feast/health` → checks basic Feast/registry wiring
  - `POST /api/features/online` → debug endpoint for fetching online features
  - `POST /api/push` → push realtime customer events into Feast `PushSource`

- **Gradio app** (`app.py`) that:
  - Renders a fraud prediction form (amount, type, origin/destination accounts)
  - Maps raw inputs into entity IDs consistent with the offline pipeline
  - Calls the `/api/predict` endpoint and displays prediction + latency details
  - Handles errors gracefully and logs failures

- **Prometheus config** (`monitoring/prometheus.yml`) to scrape FastAPI `/metrics`.

- **Nginx reverse proxy** (`deploy/nginx/nginx.conf`) that routes:
  - `/` → Gradio UI
  - `/api/*` → FastAPI
  - `/prom/*` → Prometheus UI

- A **single launcher script** (`deploy/run.sh`) that starts:
  - FastAPI
  - Gradio
  - Prometheus
  - Nginx (as the foreground process)

- **Local dev tooling**:
  - `docker-compose.yml` (local only): Postgres + Redpanda + stack container (+ optional consumer)
  - `Makefile`: common commands (`setup`, `lint`, `test`, `docker-up`, `docker-down`)
  - `requirements.txt` and `requirements-dev.txt`
  - `pyproject.toml` with basic formatter/linter configuration
  - `notebooks/00_eda_feature_store_story.ipynb` (architecture/story scaffold)
  - `notebooks/01_kaggle_eda_and_baseline.ipynb` (actual EDA + baseline modeling)

### 1.3. Step 1 – Kaggle ingestion and entity tables

- `scripts/kaggle_download.sh` and `scripts/kaggle_download.md`:
  - Explain how to configure Kaggle API (`kaggle.json`, permissions).
  - Provide a one-liner to download:
    - `rupakroy/online-payments-fraud-detection-dataset` → `data/raw/`.

- `pipelines/data_ingest.py`:
  - CLI to ingest raw CSV into cleaned parquet:
    - Enforces schema and dtypes.
    - Adds `event_timestamp` from `step` (base time `2017-01-01T00:00:00Z` + hours).
    - Drops impossible rows (negative amounts/balances), logging counts.
    - Derives entity IDs:
      - `customer_id` = `nameOrig`
      - `account_id` = `nameOrig`
      - `merchant_id` = `nameDest`
      - `geo_cell_id` = deterministic hash of `nameDest`
      - `device_id` = deterministic hash of `nameOrig + "|" + nameDest`
    - Writes:
      - `data/processed/transactions_clean.parquet`
      - `data/processed/transactions_full_schema.json`
      - `data/processed/data_profile.json`
    - Supports chunk-based sampling with `--sample_rows` (default 200k) and `--seed`.

- `pipelines/build_entity_tables.py`:
  - CLI to create entity-level snapshot aggregates from `transactions_clean.parquet`:
    - `customer_features.parquet`
    - `merchant_features.parquet`
    - `device_features.parquet`
    - `account_features.parquet`
    - `geocell_features.parquet`
  - Each table includes:
    - Entity key (e.g., `customer_id`)
    - `event_timestamp` (max per entity)
    - Simple aggregates:
      - `txn_count_total`
      - `amount_sum_total`
      - `amount_mean`
      - `amount_max`
      - `fraud_rate`
      - `flagged_rate`
      - `unique_counterparty_count`
  - Logs runtime and output row counts.

- Tests:
  - `tests/test_data_ingest.py`:
    - Validates schema of `transactions_clean.parquet` (if present).
  - `tests/test_entity_tables.py`:
    - Validates basic schema of entity feature tables (if present).

- EDA notebook:
  - `notebooks/01_kaggle_eda_and_baseline.ipynb`:
    - Loads `data/processed/transactions_clean.parquet`.
    - Analyzes target imbalance.
    - Discusses leakage.
    - Trains a simple logistic regression baseline:
      - Reports PR-AUC, ROC-AUC.
      - Computes recall@precision and precision@recall.
    - Computes permutation feature importance.
    - Explains decisions around sampling, metrics, and initial features.

### 1.4. Step 2 – Feast + Postgres + Kafka baseline

- Feast feature repo under `feature_repo/`:
  - `feature_repo/feature_store.yaml`:
    - `project: fraud_feature_store`
    - `provider: local`
    - `registry: feature_repo/data/registry.db`
    - `online_store` configured for Postgres:
      - Uses `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`.
  - `feature_repo/entities.py`:
    - Entities: `customer`, `merchant`, `device`, `account`, `geocell`.
  - `feature_repo/data_sources.py`:
    - `FileSource`s for each entity parquet in `data/processed/`.
  - `feature_repo/feature_views.py`:
    - Snapshot `FeatureView`s for each entity (`*_profile_v1`).
    - Realtime `PushSource` (`customer_realtime_push`) and `FeatureView` (`customer_realtime_v1`)
      for last-transaction features.
  - `feature_repo/feature_services.py`:
    - Bundles views into simple `FeatureService`s (e.g., `customer_risk_service_v1`).

- Feast CLI helpers:
  - `scripts/feast_apply.sh` → `feast -c feature_repo apply`
  - `scripts/feast_materialize.sh` → `feast -c feature_repo materialize-incremental <now>`

- Streaming & Feast push:
  - `services/streaming/feast_push.py`:
    - Helper `push_customer_realtime(df)` that calls `FeatureStore.push(...)` on
      `"customer_realtime_push"` using `FEAST_REPO_PATH` (default `feature_repo`).
  - `services/streaming/kafka_consumer.py`:
    - Consumes JSON events from `KAFKA_BROKERS` / `KAFKA_TOPIC` (default `txn_events`).
    - Builds a dataframe for realtime customer features:
      - `last_txn_amount`
      - `last_txn_type_code`
      - `last_txn_hour`
      - `last_txn_is_flagged`
    - Calls `push_customer_realtime(...)`.
    - Commits offsets only after successful pushes, with logging and exponential backoff on failures.
  - `services/streaming/kafka_producer.py`:
    - Seeds synthetic events to a Kafka topic for local testing.

- Kafka helpers:
  - `scripts/kafka_seed.sh`:
    - Runs `python -m services.streaming.kafka_producer` against local Redpanda (by default).
  - `scripts/kafka_seed_events.py`:
    - Simple Python CLI to seed `N` sample events into a Kafka topic.

- Tests:
  - `tests/test_feature_repo_imports.py`:
    - Imports `feature_repo` modules (including on-demand views) to catch structural errors.
  - `tests/test_api_routes.py`:
    - Checks that core routes exist.
    - Feast-dependent checks are skipped if `POSTGRES_HOST` is not configured.
  - `tests/test_api_contracts.py`:
    - Validates the `PredictionRequest` / `PredictionResponse` Pydantic models.
  - `tests/test_predict_route_smoke.py`:
    - Optional smoke test for `/api/predict` when a trained model artifact is present.

---

## 2. Local development

### 2.1. Python environment

```bash
python -m venv .venv
source .venv/bin/activate        # On Windows: .venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

Run the FastAPI backend:

```bash
uvicorn services.api.app.main:app --host 0.0.0.0 --port 8000 --reload
```

Run the Gradio frontend in another terminal:

```bash
python app.py
```

You should be able to hit:

- FastAPI health: http://127.0.0.1:8000/health
- FastAPI metrics: http://127.0.0.1:8000/metrics
- Gradio UI: http://127.0.0.1:7861/

### 2.2. Local Docker stack

For local experiments (not HF Spaces), use Docker Compose to run:

- Postgres (for future Feast online store)
- Redpanda (Kafka-compatible broker)
- Stack container (FastAPI + Gradio + Prometheus + Nginx)

```bash
docker compose up --build
```

The stack container exposes Nginx on port `7860` by default, routing:

- `http://localhost:7860/` → Gradio UI
- `http://localhost:7860/api/` → FastAPI
- `http://localhost:7860/prom/` → Prometheus UI

To tear down:

```bash
docker compose down -v
```

---

## 3. Hugging Face Spaces deployment (conceptual)

For HF Spaces (Docker):

- **Single container only**, no `docker-compose` inside the Space.
- The root `Dockerfile` builds an image that:
  - Installs Python dependencies, Nginx, and Prometheus
  - Copies the repo into `/app`
  - Uses `deploy/run.sh` as the container entrypoint
- HF Spaces provides a `$PORT` environment variable. Nginx listens on `$PORT` and proxies to:
  - Gradio on `7861`
  - FastAPI on `8000`
  - Prometheus on `9090`

When deployed on HF Spaces:

- The **user-facing endpoint** will be the Nginx port (`$PORT`), not the raw Gradio/FastAPI ports.
- Gradio should be accessed at `https://&lt;space-url&gt;/`
- API at `https://&lt;space-url&gt;/api/predict`
- Prometheus UI at `https://&lt;space-url&gt;/prom/`

---

## 4. Context grounding system

All substantial changes to this repository should be grounded in the `./context` directory.

Before implementing a new feature or refactor:

1. Read the relevant context documents:
   - `context/00_PROJECT_GOAL.md`
   - `context/01_ARCHITECTURE.md`
   - `context/02_FREE_TIER_CONSTRAINTS.md`
   - `context/03_COSINE_TASK_PROTOCOL.md`
   - Any other files related to the area you're touching

2. For Cosine AI assisted changes:
   - Follow the protocol in `context/03_COSINE_TASK_PROTOCOL.md`
   - Update:
     - `context/06_STEP_LOG.md` with the step description
     - `context/07_DECISIONS.md` with any architecture/product decisions
   - Quote which context files were read and how they influenced the changes

This ensures that the repo remains intelligible and evolvable across multiple tasks and agents.

---

## 5. Feature store & fraud detection roadmap (high level)

Later steps (not implemented in Step 0) will include:

- Initial **Feast feature repo** under `./feature_repo`:
  - Entity definitions (customers, counterparties, accounts, devices, geo cells)
  - Batch ingestion from the Kaggle fraud dataset
  - Streaming ingestion from Kafka/Redpanda

- Offline training pipeline:
  - EDA and leakage checks in `notebooks/00_eda_feature_store_story.ipynb`
  - Baseline models (e.g., tree-based) with metrics:
    - PR-AUC, ROC-AUC
    - Recall at fixed precision thresholds
    - Calibration and cost-based evaluation

- Online serving:
  - Latency-aware feature retrieval from Postgres
  - Request-time feature construction and aggregation
  - Real-time monitoring of latency and prediction quality

The Step 0 scaffold is purposefully narrow: make **`/health`**, **`/metrics`**, and a stub **`/api/predict`** work reliably, then iterate from there.

---

## 6. Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for:

- How to run tests and linting
- How to structure changes with Cosine AI tasks
- How to update the context and decision logs

## 7. Feature catalog

A generated **feature catalog** is available at [`docs/feature_catalog.md`](docs/feature_catalog.md).

To regenerate it after changing Feast entities, FeatureViews, or FeatureServices:

```bash
python scripts/export_feature_catalog.py
```

This project is designed to remain free-tier compatible and reproducible on a small machine, while still pushing toward production-grade practices.