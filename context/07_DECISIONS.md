# 07 — Decisions Register

This file records key architectural and product decisions in a lightweight ADR-style format.

Each decision should have:

- An ID (e.g., `D001`)
- Date
- Status (`proposed`, `accepted`, `deprecated`)
- Context / problem
- Options considered
- Chosen option
- Consequences and follow-ups

---

## Template

```markdown
## D0XX – <short title>
- **Date**: YYYY-MM-DD
- **Status**: proposed | accepted | deprecated
- **Context**:
  - <problem / background>
- **Options considered**:
  - Option A – <description, pros/cons>
  - Option B – <description, pros/cons>
- **Decision**:
  - <chosen option and rationale>
- **Consequences / Follow-ups**:
  - <short bullet list>
```

---

## D001 – Single-container HF deployment with internal Nginx and Prometheus

- **Date**: 2026-01-24
- **Status**: accepted
- **Context**:
  - Hugging Face Spaces (Docker) supports a single container and sets a single `$PORT`.
  - We need to serve:
    - Gradio UI
    - FastAPI API
    - Prometheus UI (optional but useful)
  - The system must remain free-tier friendly and simple to operate.
- **Options considered**:
  - **Option A** – Run a single Python process (e.g., FastAPI) and mount Gradio as a sub-app.
    - Pros:
      - Simpler process model (one server).
      - Fewer moving parts.
    - Cons:
      - Harder to integrate Prometheus UI.
      - Less separation of concerns between UI and API.
  - **Option B** – Use `docker-compose` in HF Spaces to run multiple containers (API, UI, Prometheus, Nginx).
    - Pros:
      - Clear separation between components.
    - Cons:
      - Not allowed on HF Spaces (no nested Docker/docker-compose).
  - **Option C** – Single container with multiple processes (FastAPI, Gradio, Prometheus) behind Nginx.
    - Pros:
      - Compatible with HF Spaces single-container model.
      - Clear routing:
        - `/` → Gradio
        - `/api/*` → FastAPI
        - `/prom/*` → Prometheus
      - Keeps internal ports stable.
    - Cons:
      - Slightly more complex startup/termination logic.
- **Decision**:
  - Adopt **Option C**: a single container that runs FastAPI, Gradio, and Prometheus, with Nginx as the reverse proxy listening on `$PORT`.
- **Consequences / Follow-ups**:
  - `deploy/run.sh` must act as the process supervisor for the container.
  - `deploy/nginx/nginx.conf` must remain compatible with HF `$PORT`.
  - Future changes to routing or monitoring must update both Nginx and Prometheus configs.

---

## D002 – Local-only docker-compose for Postgres + Redpanda + stack

- **Date**: 2026-01-24
- **Status**: accepted
- **Context**:
  - Developers need a convenient way to run:
    - Postgres
    - Kafka-compatible broker (Redpanda)
    - The application stack container
  - HF Spaces must not run docker-compose.
- **Options considered**:
  - **Option A** – Use docker-compose locally and in HF Spaces.
    - Cons:
      - Not compatible with HF Spaces constraints.
  - **Option B** – Avoid docker-compose completely.
    - Cons:
      - Local development becomes cumbersome (manual container orchestration).
  - **Option C** – Use docker-compose **only for local development**, and a single Dockerfile/entrypoint for HF Spaces.
    - Pros:
      - Maximizes local developer productivity.
      - Fully compatible with HF Spaces.
- **Decision**:
  - Adopt **Option C**: `docker-compose.yml` is **strictly for local dev**, while HF deployment uses only the root `Dockerfile` + `deploy/run.sh`.
- **Consequences / Follow-ups**:
  - Documentation must clearly separate local dev vs. HF deployment.
  - Any future service that needs to run in HF Spaces must be added to the single-container setup, not to a separate HF-only compose file.

---

## D003 – Sampling strategy for Kaggle ingestion

- **Date**: 2026-01-24
- **Status**: accepted
- **Context**:
  - The Kaggle dataset can be large, and we want the ingest pipeline to be usable on
    free-tier and typical laptop hardware.
  - We also want deterministic, reproducible samples for experimentation.
- **Options considered**:
  - **Option A** – Always load the full CSV into memory.
    - Pros:
      - Simple implementation.
    - Cons:
      - Risk of out-of-memory errors on small machines.
      - Slow for iterative experiments.
  - **Option B** – Require manual pre-sampling outside the repo.
    - Pros:
      - No complexity in our pipeline.
    - Cons:
      - Harder to reproduce experiments.
      - Puts more burden on users.
  - **Option C** – Implement chunk-based sampling with a configurable row cap and seed.
    - Pros:
      - Works on large CSVs.
      - Reproducible and configurable.
      - Free-tier/laptop friendly.
    - Cons:
      - Slightly more complex ingest code.
- **Decision**:
  - Adopt **Option C**: `pipelines/data_ingest.py` implements chunk-based sampling with
    `--sample_rows` (default 200k) and `--seed` (default 42). Passing a negative
    `--sample_rows` disables sampling and loads the full dataset.
- **Consequences / Follow-ups**:
  - Notebooks and docs must assume that `transactions_clean.parquet` may be a sample, not
    the full dataset.
  - Future performance-sensitive analyses should document whether they rely on full data
    or sampled data.

---

## D004 – Entity and timestamp mapping for Feast

- **Date**: 2026-01-24
- **Status**: accepted
- **Context**:
  - We need stable, reproducible entity IDs and event timestamps for Feast entities and
    FeatureViews.
  - The raw Kaggle dataset exposes `step`, `nameOrig`, `nameDest`, and balances, but no
    explicit customer/account/device/geo IDs.
- **Options considered**:
  - **Option A** – Invent new opaque IDs unrelated to the raw fields.
    - Cons:
      - Harder to debug and reason about in notebooks.
  - **Option B** – Use raw string IDs directly where possible and derive hashed IDs only
    when necessary.
    - Pros:
      - Easier to interpret.
      - Stable mapping between raw data and entities.
- **Decision**:
  - Use the following mapping (implemented in `pipelines/data_ingest.py` and
    documented in `context/04_DATASET_PLAN.md`):
    - `customer_id` = `nameOrig`
    - `account_id` = `nameOrig`
    - `merchant_id` = `nameDest`
    - `geo_cell_id` = hash(`nameDest`)
    - `device_id` = hash(`nameOrig + '|' + nameDest`)
  - Construct `event_timestamp` as:
    - `2017-01-01T00:00:00Z + step hours`
- **Consequences / Follow-ups**:
  - Feast `Entity` definitions in `feature_repo/entities.py` must use these IDs.
  - All offline and online paths (including Kafka streaming) must use the same hashing
    scheme and timestamp logic to keep entity keys consistent.
  - Any future changes to hashing or timestamp logic must be treated as breaking
    changes and recorded here.

---

## D005 – Windowed feature engineering and leakage-aware design

- **Date**: 2026-01-26
- **Status**: accepted
- **Context**:
  - We want production-style, time-windowed features (velocity, balance dynamics,
    cross-entity consistency) for multiple entities while avoiding label leakage from
    the future into the past.
  - The Kaggle dataset provides event timestamps (derived from `step`) and fraud
    labels (`isFraud`, `isFlaggedFraud`), and we already have entity IDs per D004.
- **Options considered**:
  - **Option A** – Build only static per-entity aggregates (one row per entity).
    - Pros:
      - Simple to compute and store.
    - Cons:
      - Loses temporal dynamics (recent velocity vs. long-term behaviour).
      - Harder to support time-based model evaluation.
  - **Option B** – Build fully dynamic, per-transaction features using time-based
    rolling windows over sorted event time.
    - Pros:
      - Captures recent and longer-term behaviour (1h/6h/24h/7d windows).
      - Naturally supports time-based train/validation splits.
    - Cons:
      - More complex and compute-intensive.
- **Decision**:
  - Adopt **Option B** with pandas-based time-windowed rolling features per entity:
    - Customers: transaction counts and amount stats over multiple windows, unique
      counterparties, night/weekend ratios, and high-risk type ratios.
    - Merchants, devices, accounts, and geo cells: tailored velocity, balance, and
      cross-entity features.
  - Use only past and current information in the rolling windows (no lookahead),
    to avoid label leakage from future transactions.
  - Introduce an `OnDemandFeatureView` for request-time transforms (log-amount,
    hour-of-day encodings, weekend/night flags, type codes) to keep client payloads
    simple and reuse the same logic for historical and online retrieval.
- **Consequences / Follow-ups**:
  - `pipelines/feature_engineering.py` is now the canonical place for engineered
    feature definitions; changes here must remain time-respecting and be reflected in
    the Feast `FeatureView` schemas.
  - Training and serving should both rely on `risk_scoring_v1` FeatureService, which
    bundles multi-entity features and on-demand transforms.
  - Any future change to window definitions or feature semantics must be recorded
    as a new decision (e.g., D006+) and treated as a versioned change to the
    feature tables and FeatureViews.

---

## D006 – Training pipeline, metrics, and threshold selection

- **Date**: 2026-01-26
- **Status**: accepted
- **Context**:
  - We need a reproducible training pipeline that uses the same Feast feature
    definitions as online serving and provides fraud-focused metrics.
  - The primary evaluation metric should be PR-AUC, with ROC-AUC as secondary
    and clear precision/recall/F1 at an operational threshold.
- **Options considered**:
  - **Option A** – Ad-hoc notebooks only, with manual feature joins.
    - Cons:
      - Easy to drift away from serving-time feature definitions.
      - Harder to reproduce training runs from CI.
  - **Option B** – Scripted pipeline using `FeatureStore.get_historical_features`
    and a simple model, with metadata and metrics logged to disk.
    - Pros:
      - Ensures parity with serving-time FeatureServices.
      - Easy to plug into CI or scheduled jobs.
- **Decision**:
  - Adopt **Option B**:
    - Implement `pipelines/train_model.py` that:
      - Loads `transactions_clean.parquet`.
      - Builds `entity_df` and calls `get_historical_features` on `risk_scoring_v1`.
      - Splits train/validation **by time** (not random).
      - Trains a logistic regression with `class_weight='balanced'`.
      - Chooses a decision threshold targeting ~0.9 precision on the validation set.
      - Computes PR-AUC, ROC-AUC, precision, recall, F1, and confusion matrix.
      - Computes permutation feature importance on the validation split.
      - Writes `models/model.joblib`, `models/model_metadata.json`,
        `models/feature_importance.csv`, and a human-readable model card.
- **Consequences / Follow-ups**:
  - Serving must read `model_metadata.json` to know the feature ordering and
    decision threshold used during training.
  - Future model versions (e.g., tree-based, calibrated models) should follow the
    same artifact schema and decision logging pattern.
  - CI and scheduled jobs can call the training pipeline to refresh models when
    new data appears.