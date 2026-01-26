# 06 — Step Log

This file tracks major steps in the evolution of the project. Each entry should describe:

- What was done
- When it was done
- Who/what did it
- Which context files were used
- Any key decisions (with links to `context/07_DECISIONS.md`)

Use reverse chronological order (newest at the top).

---

## Template

```markdown
## Step X – <short title>
- **Date**: YYYY-MM-DD
- **Agent**: <human or Cosine AI identifier>
- **Context used**:
  - context/00_PROJECT_GOAL.md
  - context/01_ARCHITECTURE.md
  - context/02_FREE_TIER_CONSTRAINTS.md
  - context/03_COSINE_TASK_PROTOCOL.md
  - <any others>
- **Summary**:
  - <bullet list of key changes>
- **Files touched (high level)**:
  - <path 1>
  - <path 2>
- **Decisions referenced/added**:
  - D00X – <short description>
```

---

## Step 2 – Feast + Postgres + Kafka baseline wiring

- **Date**: 2026-01-24
- **Agent**: Cosine AI (Genie)
- **Context used**:
  - context/00_PROJECT_GOAL.md
  - context/01_ARCHITECTURE.md
  - context/02_FREE_TIER_CONSTRAINTS.md
  - context/03_COSINE_TASK_PROTOCOL.md
  - context/04_DATASET_PLAN.md
  - context/05_METRICS_AND_EVAL.md
  - context/07_DECISIONS.md
- **Summary**:
  - Introduced Feast feature repository under `feature_repo/` with entities, data sources, feature views, and feature services.
  - Configured Postgres online store via `feature_store.yaml` using environment-driven connection settings.
  - Added PushSource and streaming FeatureView for minimal real-time customer features.
  - Implemented Kafka producer/consumer modules and a Feast push helper for real-time updates.
  - Extended FastAPI API with `/api/feast/health` and `/api/features/online` endpoints, including logging and graceful error handling.
  - Updated Docker compose and scripts for local testing of Feast, Postgres, and Kafka streaming.
- **Files touched (high level)**:
  - `requirements.txt`
  - `feature_repo/feature_store.yaml`
  - `feature_repo/entities.py`
  - `feature_repo/data_sources.py`
  - `feature_repo/feature_views.py`
  - `feature_repo/feature_services.py`
  - `services/streaming/*.py`
  - `services/api/app/main.py`
  - `docker-compose.yml`
  - `scripts/feast_apply.sh`
  - `scripts/feast_materialize.sh`
  - `scripts/kafka_seed.sh`
  - `tests/test_feature_repo_imports.py`
  - `tests/test_api_routes.py`
- **Decisions referenced/added**:
  - D002 – Local-only docker-compose for Postgres + Redpanda + stack.
  - D004 – Entity and timestamp mapping for Feast.
  - (Feast and Kafka integration stays within single-container HF model per D001/D002.)

---

## Step 1 – Kaggle ingestion, entity tables, and EDA baseline

- **Date**: 2026-01-24
- **Agent**: Cosine AI (Genie)
- **Context used**:
  - context/00_PROJECT_GOAL.md
  - context/01_ARCHITECTURE.md
  - context/02_FREE_TIER_CONSTRAINTS.md
  - context/03_COSINE_TASK_PROTOCOL.md
  - context/04_DATASET_PLAN.md
  - context/05_METRICS_AND_EVAL.md
- **Summary**:
  - Added Kaggle download documentation and helper script targeting `rupakroy/online-payments-fraud-detection-dataset`.
  - Implemented `pipelines/data_ingest.py` CLI to load raw CSV, enforce schema, clean, add entity IDs, and write:
    - `transactions_clean.parquet`
    - `transactions_full_schema.json`
    - `data_profile.json`
  - Implemented `pipelines/build_entity_tables.py` CLI to build entity-level aggregate parquet tables:
    - `customer_features.parquet`
    - `merchant_features.parquet`
    - `device_features.parquet`
    - `account_features.parquet`
    - `geocell_features.parquet`
  - Added tests for processed transactions and entity tables, skipping gracefully when data is absent.
  - Created `notebooks/01_kaggle_eda_and_baseline.ipynb` with a full EDA and baseline modeling narrative (PR-AUC, ROC-AUC, threshold metrics, permutation importance).
  - Updated dataset plan and decisions documents to capture sampling strategy and entity/timestamp mapping.
- **Files touched (high level)**:
  - `.gitignore`
  - `scripts/kaggle_download.sh`
  - `scripts/kaggle_download.md`
  - `pipelines/data_ingest.py`
  - `pipelines/build_entity_tables.py`
  - `tests/test_data_ingest.py`
  - `tests/test_entity_tables.py`
  - `notebooks/01_kaggle_eda_and_baseline.ipynb`
  - `context/04_DATASET_PLAN.md`
  - `context/06_STEP_LOG.md`
  - `context/07_DECISIONS.md`
- **Decisions referenced/added**:
  - D003 – Sampling strategy for Kaggle ingestion.
  - D004 – Entity and timestamp mapping for Feast.

---

## Step 0 – Scaffold free-tier-first repo

- **Date**: 2026-01-24
- **Agent**: Cosine AI (Genie)
- **Context used**:
  - context/00_PROJECT_GOAL.md
  - context/01_ARCHITECTURE.md
  - context/02_FREE_TIER_CONSTRAINTS.md
  - context/03_COSINE_TASK_PROTOCOL.md
  - context/04_DATASET_PLAN.md
  - context/05_METRICS_AND_EVAL.md
- **Summary**:
  - Created initial repository structure and context documents.
  - Implemented minimal FastAPI service with `/health`, `/metrics`, and stub `/api/predict`.
  - Implemented Gradio UI calling the local `/api/predict` endpoint.
  - Added Prometheus configuration and Nginx reverse proxy config.
  - Added `deploy/run.sh` to start FastAPI, Gradio, Prometheus, and Nginx in a single container.
  - Added local `docker-compose.yml` for Postgres, Redpanda, and the stack container.
  - Added notebook scaffold for EDA and feature store story.
- **Files touched (high level)**:
  - `README.md`
  - `context/*.md`
  - `services/api/app/main.py`
  - `services/api/tests/test_health.py`
  - `app.py`
  - `Dockerfile`
  - `docker-compose.yml`
  - `deploy/run.sh`
  - `deploy/nginx/nginx.conf`
  - `monitoring/prometheus.yml`
  - `notebooks/00_eda_feature_store_story.ipynb`
- **Decisions referenced/added**:
  - D001 – Single-container HF deployment with Nginx + Prometheus inside.
  - D002 – Use local-only docker-compose for Postgres + Redpanda + stack.