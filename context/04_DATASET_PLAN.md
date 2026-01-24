# 04 — Dataset Plan: Online Payments Fraud Detection

This project uses the **“Online Payments Fraud Detection Dataset”** from Kaggle as the primary source for offline experimentation and feature-store design.

---

## 1. Dataset reference

- **Name**: Online Payments Fraud Detection Dataset
- **Platform**: Kaggle
- **Slug**: `rupakroy/online-payments-fraud-detection-dataset`
- **Typical columns**:

  - `step`
  - `type`
  - `amount`
  - `nameOrig`
  - `oldbalanceOrg`
  - `newbalanceOrig`
  - `nameDest`
  - `oldbalanceDest`
  - `newbalanceDest`
  - `isFraud`
  - `isFlaggedFraud`

The exact schema is captured at ingest time in:

- `data/processed/transactions_full_schema.json`
- `data/processed/data_profile.json`

and should be kept consistent with this document as the pipeline evolves.

---

## 2. High-level usage plan

We will use this dataset for:

1. **Exploratory Data Analysis (EDA)**:
   - Target imbalance inspection (`isFraud` distribution).
   - Transaction types and volume over `step`.
   - Amount distributions and outliers.
   - Simple cohort analysis (e.g., by account type or counterparty patterns).

2. **Leakage checks**:
   - Ensure no columns contain post-event information that would be unavailable at scoring time.
   - Specifically scrutinize balances and any derived fields.

3. **Feature engineering**:
   - Design features that can reasonably be computed online / near real time.
   - Map engineered features into Feast `FeatureView`s.

4. **Training & evaluation**:
   - Generate training/validation/test splits in a **time-aware** fashion (respecting `step`).
   - Compute metrics suitable for imbalanced classification (see `context/05_METRICS_AND_EVAL.md`).

---

## 3. Entity mapping (Step 1+2 baseline)

Based on Step 1/2 pipelines, we adopt the following mapping from raw columns to domain entities:

- **Customer / account entities**:
  - `customer_id` → `nameOrig`
  - `account_id` → `nameOrig`
- **Merchant / counterparty entities**:
  - `merchant_id` → `nameDest`
- **Device / composite entities** (hashed IDs):
  - `device_id` → deterministic hash of `nameOrig + "|" + nameDest`
- **Geo / cell entities** (hashed IDs):
  - `geo_cell_id` → deterministic hash of `nameDest`

Notes:

- The hashing mechanism is implemented in `pipelines/data_ingest.py` and must remain
  deterministic and stable across offline and online paths.
- These IDs are used consistently in:
  - `data/processed/transactions_clean.parquet`
  - `data/processed/*_features.parquet`
  - `feature_repo/entities.py`

This mapping drives Feast `Entity` definitions and how we key feature tables.

---

## 4. Feature categories (initial thinking)

We anticipate at least these feature categories:

1. **Static/meta features**:
   - Account age (if derivable)
   - Typical transaction type distribution for an account

2. **Velocity / frequency features**:
   - Number of transactions in the last N steps (`1h`, `24h`, etc.).
   - Total and average amount per time window per entity.

3. **Balance and ratio features**:
   - `amount / (oldbalanceOrg + 1)`
   - Delta balances: `oldbalanceOrg - newbalanceOrig`, etc.
   - Ratios between sender and receiver balances.

4. **Counterparty interaction features**:
   - Recency and frequency of transfers between `nameOrig` and `nameDest`.
   - “First time sender → receiver?” flags.

5. **Flagged vs. true fraud**:
   - Understand the relationship between `isFraud` and `isFlaggedFraud`.
   - Create features capturing “flagged but not fraud” behavior.

In Step 1 entity tables (`pipelines/build_entity_tables.py`), we start with simple
snapshot aggregates per entity:

- `txn_count_total`
- `amount_sum_total`
- `amount_mean`
- `amount_max`
- `fraud_rate` (mean of `isFraud`)
- `flagged_rate` (mean of `isFlaggedFraud`)
- `unique_counterparty_count`

These are later exposed via Feast `FeatureView`s.

---

## 5. Data access and governance

Implementation notes:

- Data is downloaded manually or via the Kaggle API using:
  - `scripts/kaggle_download.sh`
  - `scripts/kaggle_download.md`
- **Do not commit raw data** to this repository.
- Keep any local data files under the `data/` directory (ignored by `.gitignore`).
- The ingest pipeline (`pipelines/data_ingest.py`) is responsible for:
  - Enforcing schema and dtypes.
  - Dropping impossible rows (negative balances/amounts).
  - Writing:
    - `transactions_clean.parquet`
    - `transactions_full_schema.json`
    - `data_profile.json`

We may later introduce small, anonymized samples for quick tests, still respecting license terms.

---

## 6. Integration with Feast

In Step 2, we connect this dataset to Feast by:

1. Defining Feast **entities** (`feature_repo/entities.py`) based on the IDs above.
2. Creating **FileSources** that point at the processed parquet tables
   (`feature_repo/data_sources.py`).
3. Creating **FeatureViews** that expose the snapshot aggregates per entity
   (`feature_repo/feature_views.py`).
4. Materializing features to the Postgres online store used by the FastAPI service.

The feature definitions are intended to remain aligned with:

- The narrative in the EDA notebook:
  - `notebooks/01_kaggle_eda_and_baseline.ipynb`
- The metrics and evaluation strategy in:
  - `context/05_METRICS_AND_EVAL.md`.