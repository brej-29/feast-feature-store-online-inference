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

## D005 – Point-in-time entity features with label maturation delay

- **Date**: 2026-07-12
- **Status**: accepted
- **Context**:
  - The v1 entity tables aggregated over the FULL dataset — including each
    row's own fraud label — and served `fraud_rate` as a feature. That is
    target leakage: the model would be scored on information unavailable at
    prediction time, inflating offline metrics and collapsing in production.
- **Options considered**:
  - **Option A** – Static temporal split: compute aggregates on an early
    "history" window only, train on a later window.
    - Pros: simple. Cons: features go stale; doesn't exercise Feast's
      point-in-time join; weaker portfolio story.
  - **Option B** – Per-(entity, timestamp) expanding aggregates over strictly
    prior transactions, with a maturation delay on label-derived features.
    - Pros: correct by construction; `get_historical_features` picks the
      right row for any training timestamp; mirrors how real fraud systems
      handle delayed chargeback labels. Cons: larger feature tables, more
      complex builder.
- **Decision**:
  - Option B, implemented in `pipelines/build_entity_tables.py`. Behavioral
    aggregates use transactions with `ts < t`; fraud-label aggregates only
    count transactions matured by `t - 72h` (configurable
    `--label_delay_hours`). Verified by `tests/test_point_in_time.py`.
- **Consequences / Follow-ups**:
  - Feature tables grow to one row per entity-timestamp (~300k rows/entity
    at the current sample size) — acceptable for parquet + free-tier Postgres.
  - v1 feature views were removed; consumers must use `*_profile_v2`.

---

## D006 – Exclude post-transaction balance fields from model features

- **Date**: 2026-07-12
- **Status**: accepted
- **Context**:
  - `newbalanceOrig`/`newbalanceDest` describe the state AFTER a transaction
    executes. A real-time scorer decides before execution, so these fields
    are unavailable at serving time. They also make PaySim near-trivially
    separable, producing dishonest headline metrics.
- **Decision**:
  - The model uses only request-time fields (`amount`, `type`, hour,
    pre-transaction balances) plus Feast-served historical features.
    Enforced in `pipelines/train_model.py::build_entity_df` and tested.
- **Consequences / Follow-ups**:
  - Headline metrics are lower than typical PaySim notebooks (PR-AUC ~0.49
    vs. inflated ~0.99) — this is intentional and documented in the model
    card as an honesty feature.

---

## D007 – Committed model artifact bundle with feature contract

- **Date**: 2026-07-12
- **Status**: accepted
- **Context**:
  - Serving needs the trained model plus the exact feature names/order,
    defaults, and threshold used at training time. Free-tier deployment has
    no artifact registry.
- **Options considered**:
  - **Option A** – External registry (MLflow, HF Hub model repo). Deferred:
    adds infra for Phase 2+.
  - **Option B** – Commit a small joblib bundle (`models/fraud_model_v2.joblib`,
    ~76KB) carrying model + feature contract + metrics, plus a model card.
- **Decision**:
  - Option B for now. The bundle is the single source of truth the API loads;
    serving cannot silently drift from training because feature names and
    defaults travel with the model.
- **Consequences / Follow-ups**:
  - Revisit with MLflow or HF Hub in a later phase; keep bundle size small.

---

## D008 – Uniform time sampling and recent-anchored timestamps

- **Date**: 2026-07-12
- **Status**: accepted
- **Context**:
  - The previous chunked sampler silently kept only the FIRST ~13 hours of
    the 31-day simulation (200k head rows), breaking temporal splits and
    entity history. Also, 2017-anchored timestamps make online-store TTLs and
    `materialize-incremental` meaningless in a live demo.
- **Decision**:
  - `pipelines/data_ingest.py` now defaults to `--sample_strategy uniform`
    (random sample across the full simulated window, sorted by step) and
    `--base_time recent` (anchor the window to end roughly now). The legacy
    behavior remains available via `--sample_strategy head` /
    `--base_time <ISO>`.
- **Consequences / Follow-ups**:
  - Data must be re-ingested when the demo window drifts too far into the
    past (document a refresh command in deployment docs).

---

## D009 – Superseded a parallel feature-engineering/training implementation on merge

- **Date**: 2026-07-12
- **Status**: accepted
- **Context**:
  - While Phase 1 was in progress on this branch, a separate PR
    (`cosine/feat/step3-9-complete-project`) was merged directly into `main`,
    adding its own windowed feature engineering (`pipelines/feature_engineering.py`),
    Feast views (`*_features_fv_v1`), on-demand view, and training pipeline
    targeting a `risk_scoring_v1` feature service.
  - Reconciling this branch with `main` required a decision on which
    implementation to keep going forward.
- **Findings**:
  - The parallel implementation reintroduces exactly the leakage classes D005/D006
    (this document) were written to fix:
    - `mch_fraud_rate_7d` is an **unshifted** rolling mean of `isFraud` — a
      time-indexed pandas `.rolling(window).mean()` includes the current row,
      so this feature contains the label of the very transaction being scored.
    - `acct_org_balance_delta` / `acct_dest_balance_delta` are computed from
      `newbalanceOrig`/`newbalanceDest`, i.e. **post-transaction** state,
      unavailable to a real-time scorer (same issue as D006 above).
  - Its `*_profile_v1` views (also leaky — full-dataset `fraud_rate`) were left
    in place rather than removed.
- **Decision**:
  - Keep this branch's point-in-time correct pipeline, `*_profile_v2` views, and
    `fraud_detection_v2` training/serving path as canonical. Remove the parallel
    implementation's leakage-prone modules and their direct tests:
    `pipelines/feature_engineering.py`, `feature_repo/on_demand_feature_views.py`,
    `scripts/feast_materialize_incremental.sh`,
    `notebooks/02_training_and_feature_importance.ipynb`, and
    `tests/test_api_contracts.py`, `tests/test_feature_engineering_schema.py`,
    `tests/test_model_artifact_schema.py`, `tests/test_predict_route_smoke.py`
    (each asserts against the removed schema/artifacts).
  - Keep the parallel PR's genuinely additive, non-conflicting assets: CI
    workflows (`materialize.yml`, `drift.yml`, adapted to this branch's
    commands), `monitoring/drift_report.py`, `load_tests/locustfile.py` and
    `scripts/benchmark_predict.py` (adapted to this branch's request schema),
    `scripts/export_feature_catalog.py` (introspection-based, name-agnostic),
    and deployment docs.
  - Docs that documented only the removed pipeline
    (`docs/ops_materialization.md`, `docs/feature_importance.md`,
    `context/09_LOCAL_RUN_AND_TEST.md`) were removed rather than left stale;
    Phase 2/4 should write their replacements against the verified v2 commands.
- **Consequences / Follow-ups**:
  - `main` briefly contained the leaky parallel implementation between the two
    PRs' merges; this decision documents why it was not carried forward.
  - Phase 2 should add a CI job that actually runs `pytest`, since neither
    implementation had one.
