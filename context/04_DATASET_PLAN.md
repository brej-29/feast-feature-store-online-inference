# 04 — Dataset Plan: Online Payments Fraud Detection

This project uses the **“Online Payments Fraud Detection Dataset”** from Kaggle as the primary source for offline experimentation and feature-store design.

---

## 1. Dataset reference

- **Name**: Online Payments Fraud Detection Dataset
- **Platform**: Kaggle
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

The exact schema should be verified in the EDA notebook and documented here as we progress.

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

## 3. Entity mapping proposal

Proposed mapping from raw columns to domain entities (to be refined later):

- **Customer / account entities**:
  - `customer_id` → `nameOrig`
  - `account_id` → `nameOrig`
- **Counterparty entities**:
  - `counterparty_id` → `nameDest`
- **Device / composite entities** (placeholder hashes):
  - `device_id` → `hash(nameOrig + nameDest)`
- **Geo / cell entities**:
  - `geo_cell_id` → `hash(nameDest)` (placeholder; real geo features may require external data)

Notes:

- We use hashes for entities where we do not have explicit IDs in the dataset.
- The hashing mechanism should be stable and deterministic across offline and online paths.

This mapping will inform Feast `Entity` definitions and how we key feature tables.

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

These will be articulated and refined in the EDA notebook:
`notebooks/00_eda_feature_store_story.ipynb`.

---

## 5. Data access and governance

Step 0 focuses on **documentation and scaffolding**, not actual data ingestion.

Implementation notes:

- Data will be downloaded manually or via the Kaggle API using:
  - `scripts/kaggle_download.md` as a guide.
- **Do not commit raw data** to this repository.
- Keep any local data files under a dedicated `data/` directory (ignored by `.gitignore`).

In later steps, we may:

- Persist cleaned/feature-ready datasets as parquet files.
- Introduce a small, anonymized sample for quick tests, still respecting license terms.

---

## 6. Integration with Feast (future)

Later, we will:

1. Define Feast **entities** based on the mapping above.
2. Create **FeatureViews** that:
   - Pull from batch sources (Kaggle-derived tables/files).
   - Optionally consume from streaming sources (Kafka/Redpanda).
3. Materialize features to the Postgres online store used by the FastAPI service.

The feature definitions should be tightly aligned with the narrative in the EDA notebook and the metrics in `context/05_METRICS_AND_EVAL.md`.