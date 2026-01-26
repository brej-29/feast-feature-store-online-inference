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
## Step X – &lt;short title&gt;
- **Date**: YYYY-MM-DD
- **Agent**: &lt;human or Cosine AI identifier&gt;
- **Context used**:
  - context/00_PROJECT_GOAL.md
  - context/01_ARCHITECTURE.md
  - context/02_FREE_TIER_CONSTRAINTS.md
  - context/03_COSINE_TASK_PROTOCOL.md
  - &lt;any others&gt;
- **Summary**:
  - &lt;bullet list of key changes&gt;
- **Files touched (high level)**:
  - &lt;path 1&gt;
  - &lt;path 2&gt;
- **Decisions referenced/added**:
  - D00X – &lt;short description&gt;
```

---

## Step 5–8 – Training pipeline, online serving, performance, and monitoring

- **Date**: 2026-01-26
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
  - Implemented `pipelines/train_model.py` to train a logistic regression model using Feast `risk_scoring_v1` features, with time-based train/validation split, PR-AUC/ROC-AUC metrics, threshold selection targeting high precision, and permutation feature importance.
  - Added model artifacts under `models/` (`model.joblib`, `model_metadata.json`, `feature_importance.csv`) and a lightweight model card; created tests to validate metadata schema.
  - Upgraded FastAPI `/api/predict` to use Feast online features + trained model, returning structured latency breakdowns and wiring to the Gradio UI; added `/api/health` and `/api/push` for scoped health checks and realtime Feast pushes.
  - Extended the Gradio app (`app.py`) to map raw inputs into entity IDs consistent with the offline pipeline and to display prediction + latency information.
  - Introduced load/performance tooling: `load_tests/locustfile.py`, `scripts/benchmark_predict.py`, and `docs/performance_testing.md`.
  - Added a drift reporting script (`monitoring/drift_report.py`) using Evidently, plus a GitHub Actions workflow (`.github/workflows/drift.yml`) that generates and uploads drift reports as artifacts.
  - Documented operational materialization (`docs/ops_materialization.md`), HF deployment (`docs/HF_DEPLOYMENT.md`, `deploy/SPACE_README.md`), and refined `.env.example` for local vs. managed Postgres/Kafka settings.
- **Files touched (high level)**:
  - `pipelines/train_model.py`
  - `models/*` (generated artifacts, not committed)
  - `services/api/app/main.py`
  - `app.py`
  - `scripts/feast_materialize_incremental.sh`
  - `.github/workflows/materialize.yml`
  - `monitoring/drift_report.py`
  - `.github/workflows/drift.yml`
  - `load_tests/locustfile.py`
  - `scripts/benchmark_predict.py`
  - `scripts/kafka_seed_events.py`
  - `docs/ops_materialization.md`
  - `docs/performance_testing.md`
  - `docs/HF_DEPLOYMENT.md`
  - `deploy/SPACE_README.md`
  - `.env.example`
  - `requirements.txt`
  - `tests/test_api_contracts.py`
  - `tests/test_predict_route_smoke.py`
  - `tests/test_model_artifact_schema.py`
  - `tests/test_train_pipeline_import.py`
- **Decisions referenced/added**:
  - D005 – Windowed feature engineering and leakage-aware design.
  - D006 – Training pipeline, metrics, and threshold selection.

---

## Step 3 – Windowed feature engineering, Feast feature services, and training-ready catalog

- **Date**: 2026-01-26
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
  - Implemented `pipelines/feature_engineering.py` to build windowed, production-style feature tables for five entities (customer, merchant, device, account, geo cell) with 50+ engineered features, sample-mode controls, and JSON schema snapshots.
  - Added new Feast `FileSource`s for `*_features_v1.parquet` tables and corresponding `FeatureView`s (`*_features_fv_v1`) that expose velocity, balance, and cross-entity consistency features.
  - Introduced an on-demand `RequestSource` and `OnDemandFeatureView` (`transaction_request_features`) for request-time transforms (log-amount, time-of-day sin/cos, weekend/night flags, type codes).
  - Defined risk-scoring `FeatureService`s (`risk_scoring_v1`, `risk_scoring_v2`) bundling multi-entity features, realtime push-based features, and on-demand transforms.
  - Added a feature catalog export script that introspects the Feast repo and writes `docs/feature_catalog.md`.
  - Added lightweight tests ensuring feature tables (if present) expose at least 50 engineered feature columns and that the Feast repo modules (including on-demand views) import correctly.
- **Files touched (high level)**:
  - `pipelines/feature_engineering.py`
  - `feature_repo/data_sources.py`
  - `feature_repo/feature_views.py`
  - `feature_repo/on_demand_feature_views.py`
  - `feature_repo/feature_services.py`
  - `scripts/export_feature_catalog.py`
  - `docs/feature_catalog.md`
  - `tests/test_feature_engineering_schema.py`
  - `tests/test_feature_repo_imports.py`
  - `README.md`
- **Decisions referenced/added**:
  - D004 – Entity and timestamp mapping for Feast.
  - D005 – Window definitions and label-leakage-safe feature engineering.

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