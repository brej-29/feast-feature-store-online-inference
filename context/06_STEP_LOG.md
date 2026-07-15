# 06 — Step Log

This file tracks major steps in the evolution of the project. Each entry should describe:

- What was done
- When it was done
- Who/what did it
- Which context files were used
- Any key decisions (with links to `context/07_DECISIONS.md`)

Use reverse chronological order (newest at the top).

---

## Step 6 – Phase 3 (start): deployment prep, pivot from HF Spaces to Render

- **Date**: 2026-07-12
- **Agent**: Claude Code (with human review)
- **Context used**:
  - context/07_DECISIONS.md (D011)
- **Summary**:
  - `deploy/run.sh` now runs `feast apply` + materialize on every container
    boot (it never ran automatically before); a fresh container has no
    committed registry, so this is required for any hosted deployment to
    serve real predictions rather than degraded/default-only ones.
  - Committed the 5 point-in-time entity feature parquet tables (~19MB) so
    a freshly built container has offline data to materialize from.
  - Attempted to create a Hugging Face Space (Docker SDK) and discovered
    HF now requires a PRO subscription for Docker/Gradio Spaces on free
    accounts (confirmed via API 402 response). Pivoted to Render.com's free
    web service plan instead -- see D011 for the full reasoning and
    trade-offs (cold starts on the free plan).
  - Added `render.yaml` (Blueprint) and `docs/RENDER_DEPLOYMENT.md`;
    `docs/HF_DEPLOYMENT.md` kept with a correction note for anyone with/
    getting HF PRO.
- **Files touched (high level)**:
  - `deploy/run.sh`
  - `data/processed/*_features.parquet` (5 files, newly committed)
  - `render.yaml` (new), `docs/RENDER_DEPLOYMENT.md` (new)
  - `docs/HF_DEPLOYMENT.md`
- **Decisions referenced/added**:
  - D011 – Deploy to Render.com instead of Hugging Face Spaces.

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

## Step 5 – Phase 2: production hardening (CI, validation, observability, auth, calibration)

- **Date**: 2026-07-12
- **Agent**: Claude Code (with human review)
- **Context used**:
  - context/07_DECISIONS.md (D010)
- **Summary**:
  - **CI** (`.github/workflows/test.yml`): ruff (blocking), mypy (non-blocking
    while the codebase adopts typing), pytest unit suite on push/PR; a
    second job runs the Testcontainers integration suite. Fixed the ruff
    findings this surfaced (deprecated `[tool.ruff]` top-level config moved
    to `[tool.ruff.lint]`, one dead variable).
  - **Data validation** (`pipelines/schemas.py`, `pandera`): cleaned
    transactions are validated against a schema (required columns, known
    transaction types, non-negative amounts/balances, isFraud/isFlaggedFraud
    in {0,1}, tz-aware timestamps) before being written; fails loudly with
    the specific failing rows instead of silently writing bad data downstream.
  - **Correlation IDs**: `X-Request-ID` generated/propagated per request via
    a contextvar, injected into every log line (including third-party
    loggers like `feast.infra.registry`) via a handler-level logging filter,
    and included in every error response body (both the unhandled-exception
    path and all `HTTPException`s).
  - **Streaming freshness metrics** (`services/streaming/feast_push.py`):
    `feast_push_success_total`/`feast_push_failure_total` counters,
    `feast_push_last_success_unixtime` gauge, and a
    `feast_push_event_lag_seconds` histogram (age of the newest pushed event
    at push time -- the actual Kafka-to-online-store freshness number). The
    Kafka consumer now runs its own Prometheus HTTP server
    (`CONSUMER_METRICS_PORT`, default 9100); wired into docker-compose and
    `monitoring/prometheus.yml` as a second scrape target.
  - **API key auth**: optional `X-API-Key` header check on `/api/predict`,
    gated by the `API_KEY` env var (unset = disabled, for local dev). Gradio
    UI reads the same var and attaches the header automatically.
  - **Model calibration fix (D010)**: found and fixed a class-imbalance bug
    in the production model -- see D010. PR-AUC 0.54 → 0.93,
    `recall_at_precision_0.90` 0.0 → 0.84, sane operating threshold (0.97
    instead of 0.9999999992). Retrained; `models/` artifacts updated.
  - **Testcontainers integration test**
    (`tests/test_integration_feast_path.py`): spins up an ephemeral Postgres,
    applies a throwaway PushSource-backed feature view, pushes a row, and
    reads it back online -- proves the realtime path against a real
    Postgres, not mocks. Marked `integration`, excluded from the default
    unit-test run.
  - **`make demo`**: one command (idempotent, skips completed stages) that
    brings up local Postgres, ingests data if needed, builds entity tables
    if needed, applies + materializes Feast, trains if needed, and serves
    the API + UI.
  - Re-ingested with a fresh `--base_time recent` window (keeps the online
    serving demo's "now" meaningful) and rebuilt/re-materialized entity
    tables accordingly.
- **Files touched (high level)**:
  - `.github/workflows/test.yml` (new), `pyproject.toml` (ruff/mypy/pytest config)
  - `pipelines/schemas.py` (new), `pipelines/data_ingest.py`
  - `services/api/app/main.py` (correlation IDs, API key auth)
  - `services/streaming/feast_push.py`, `services/streaming/kafka_consumer.py`
  - `monitoring/prometheus.yml`, `docker-compose.yml`
  - `pipelines/train_model.py` (class_weight="balanced")
  - `tests/test_schemas.py`, `tests/test_integration_feast_path.py` (new)
  - `Makefile` (`demo`, `test-integration` targets)
- **Decisions referenced/added**:
  - D010 – class_weight="balanced" on the fraud model.

---

## Step 4 – Reconcile with a parallel PR merged directly to main

- **Date**: 2026-07-12
- **Agent**: Claude Code (with human review)
- **Context used**:
  - context/07_DECISIONS.md (D009)
- **Summary**:
  - While Step 3 (below) was in progress on its own branch, a separate PR
    (`cosine/feat/step3-9-complete-project`) was merged directly to `main`,
    adding a parallel feature-engineering/training/serving implementation
    that reintroduced target leakage (see D009 for specifics).
  - Merged `main` into this branch. Kept this branch's point-in-time correct
    pipeline and `fraud_detection_v2` service as canonical; removed the
    parallel implementation's leaky modules and their direct tests; kept its
    genuinely additive, non-conflicting assets (CI workflows, drift
    monitoring, load testing, feature catalog exporter), adapted to this
    branch's commands and request schema.
  - Removed docs that only documented the removed pipeline rather than
    leaving them stale (`docs/ops_materialization.md`,
    `docs/feature_importance.md`, `context/09_LOCAL_RUN_AND_TEST.md`) —
    Phase 2/4 will write their replacements against the verified v2 commands.
- **Files touched (high level)**:
  - Removed: `pipelines/feature_engineering.py`, `feature_repo/on_demand_feature_views.py`,
    `scripts/feast_materialize_incremental.sh`, `notebooks/02_training_and_feature_importance.ipynb`,
    `tests/test_api_contracts.py`, `tests/test_feature_engineering_schema.py`,
    `tests/test_model_artifact_schema.py`, `tests/test_predict_route_smoke.py`,
    `docs/ops_materialization.md`, `docs/feature_importance.md`, `context/09_LOCAL_RUN_AND_TEST.md`
  - Kept/adapted: `.github/workflows/materialize.yml`, `.github/workflows/drift.yml`,
    `monitoring/drift_report.py`, `load_tests/locustfile.py`, `scripts/benchmark_predict.py`,
    `scripts/export_feature_catalog.py`, `scripts/kafka_seed_events.py`,
    `docs/HF_DEPLOYMENT.md`, `deploy/SPACE_README.md`, `docs/performance_testing.md`
- **Decisions referenced/added**:
  - D009 – Superseded a parallel feature-engineering/training implementation on merge.

---

## Step 3 – Phase 1: leakage-safe features, real model, wired serving

- **Date**: 2026-07-12
- **Agent**: Claude Code (with human review)
- **Context used**:
  - context/00_PROJECT_GOAL.md
  - context/04_DATASET_PLAN.md
  - context/05_METRICS_AND_EVAL.md
  - context/07_DECISIONS.md
- **Summary**:
  - **Fixed target leakage**: entity feature tables are now point-in-time
    correct — one row per (entity, event_timestamp) aggregating only
    strictly-prior transactions; fraud-label features additionally respect a
    72h label maturation delay (D005).
  - **Fixed sampling bias**: ingestion now samples uniformly across the full
    ~31-day simulated window (the old chunked logic silently kept only the
    first 13 hours) and anchors timestamps to end near "now" so online-store
    TTLs and materialization behave like live traffic (D008).
  - **Real training pipeline** (`pipelines/train_model.py`): training data
    assembled via Feast `get_historical_features` against the
    `fraud_detection_v2` feature service; temporal 80/20 split;
    HistGradientBoostingClassifier; artifact bundle + metrics + model card
    committed under `models/` (D007). Post-transaction balance fields are
    excluded from features (D006).
  - **Feast repo v2**: `*_profile_v2` views over the point-in-time sources;
    leaky v1 views removed; `customer_realtime_v1` now has a valid batch
    source carrying historical `last_txn_*` columns, so the PushSource path
    and training read the same feature definitions.
  - **Serving wired end-to-end**: `/api/predict` now derives entity keys,
    fetches online features, scores with the trained model, and returns a
    latency breakdown (feature fetch vs. inference); degrades gracefully to
    request-time features if the online store is down. Added
    `/api/model/info` and Prometheus metrics for score distribution and
    per-stage latency.
  - **Tests**: leakage regression suite for the point-in-time builder,
    training smoke tests, mocked serving-path tests (28 passing).
  - Shared encodings (transaction type codes, entity-id hashing) centralized
    in `pipelines/encoders.py` and reused by ingest, training, streaming, and
    serving.
- **Files touched (high level)**:
  - `pipelines/encoders.py` (new)
  - `pipelines/data_ingest.py`
  - `pipelines/build_entity_tables.py` (rewritten)
  - `pipelines/train_model.py` (new)
  - `feature_repo/feature_views.py`, `feature_repo/feature_services.py`, `feature_repo/__init__.py`
  - `services/api/app/main.py` (rewritten predict path)
  - `services/streaming/kafka_consumer.py`
  - `scripts/feast_materialize.sh`
  - `models/` (new: artifact, metrics, model card)
  - `tests/test_point_in_time.py`, `tests/test_train_model.py`, `tests/test_api_predict.py` (new)
- **Decisions referenced/added**:
  - D005 – Point-in-time entity features with label maturation delay.
  - D006 – Exclude post-transaction balance fields from model features.
  - D007 – Committed model artifact bundle with feature contract.
  - D008 – Uniform time sampling and recent-anchored timestamps.

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