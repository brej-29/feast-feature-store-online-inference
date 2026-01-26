# Operational Guide – Feast Materialization

This document explains how to (re)build engineered feature tables and materialize
them into the Feast online store.

## 1. Prerequisites

- `pip install -r requirements.txt`
- A Postgres instance reachable from where you run `feast`:
  - Connection parameters supplied via environment variables or `.env`:
    - `POSTGRES_HOST`
    - `POSTGRES_PORT`
    - `POSTGRES_DB`
    - `POSTGRES_USER`
    - `POSTGRES_PASSWORD`
- Cleaned transactions parquet:
  - `data/processed/transactions_clean.parquet` (from `pipelines/data_ingest.py`)

## 2. Build windowed feature tables

Run the feature engineering pipeline to build per-entity, windowed feature tables
under `data/processed/feature_tables/`:

```bash
python pipelines/feature_engineering.py \
  --transactions_path data/processed/transactions_clean.parquet \
  --out_dir data/processed \
  --sample_rows 200000 \
  --max_entities 5000
```

Notes:

- `--sample_rows` (optional): maximum number of transaction rows to use for feature
  engineering. Use a negative value or omit the flag to use all rows.
- `--max_entities` (optional): cap on the number of unique entities per entity type
  (customer, merchant, device, account, geo cell), useful for local experiments.
- The pipeline writes:
  - `data/processed/feature_tables/customer_features_v1.parquet`
  - `data/processed/feature_tables/merchant_features_v1.parquet`
  - `data/processed/feature_tables/device_features_v1.parquet`
  - `data/processed/feature_tables/account_features_v1.parquet`
  - `data/processed/feature_tables/geocell_features_v1.parquet`
  - Plus a `_schema.json` file alongside each parquet for quick inspection.

## 3. Apply Feast definitions

Once the feature tables exist, apply the Feast repo so that the registry knows
about entities, FeatureViews, and FeatureServices:

```bash
# Uses FEAST_REPO_PATH=feature_repo by default
bash scripts/feast_apply.sh
```

This will:

- Load definitions from `feature_repo/`
- Connect to the configured Postgres instance
- Create / migrate online store tables as needed

If Postgres is not reachable or not configured, `feast apply` will fail. In CI
we typically guard this with environment checks (see below).

## 4. Materialize snapshot FeatureViews

To backfill the online store up to the current time for all snapshot
FeatureViews (excluding realtime push-based views), run:

```bash
bash scripts/feast_materialize_incremental.sh
```

What this script does:

- Verifies that `data/processed/feature_tables/*_features_v1.parquet` exist.
  - If not, it logs a message and exits **successfully** (exit code 0) so that
    automation does not fail on missing local data.
- Computes `END_TS_UTC` as the current UTC timestamp.
- Runs:

  ```bash
  feast -c feature_repo materialize-incremental \
    -v device_profile_v1 \
    -v merchant_profile_v1 \
    -v customer_profile_v1 \
    -v account_profile_v1 \
    -v geocell_profile_v1 \
    -v customer_features_fv_v1 \
    -v merchant_features_fv_v1 \
    -v device_features_fv_v1 \
    -v account_features_fv_v1 \
    -v geocell_features_fv_v1 \
    "${END_TS_UTC}"
  ```

- Leaves out `customer_realtime_v1`, which is populated exclusively via
  `FeatureStore.push` from the streaming pipeline and API `/api/push` endpoint.

## 5. GitHub Actions workflow

The repo includes a GitHub Actions workflow at
[`.github/workflows/materialize.yml`](../.github/workflows/materialize.yml) that:

1. Checks out the repository.
2. Sets up Python 3.11 and installs runtime dependencies.
3. Runs `pipelines/feature_engineering.py` in **sample mode**, skipping cleanly if
   `transactions_clean.parquet` is missing (common in CI).
4. Runs `feast apply` and `feast_materialize_incremental.sh` **only if**
   `POSTGRES_HOST` (and related secrets) are configured.

This means:

- On a fresh CI environment with no data and no Postgres secrets, the workflow
  exits successfully with clear log messages.
- Once you provide Postgres credentials as GitHub secrets, the same workflow can
  drive real materialization into your managed Postgres instance.

## 6. Local vs. remote workflows

- **Local development**:
  - Use Docker Compose (`docker-compose.yml`) to start Postgres + Redpanda +
    the app stack.
  - Run:
    - `pipelines/data_ingest.py`
    - `pipelines/feature_engineering.py`
    - `scripts/feast_apply.sh`
    - `scripts/feast_materialize_incremental.sh`
- **Remote / managed Postgres** (e.g., Neon, Supabase):
  - Configure Postgres connection settings in `.env` or environment variables.
  - Optionally wire secrets into GitHub Actions for scheduled materialization.
  - Use the same scripts; only the connection string changes.