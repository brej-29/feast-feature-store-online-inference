# Kaggle Dataset Download Instructions

This document describes how to download the **Online Payments Fraud Detection Dataset** from Kaggle for local use.

Target dataset (Step 1/2):

- Kaggle slug: **`rupakroy/online-payments-fraud-detection-dataset`**

> Note: Do **not** commit any downloaded data files or your Kaggle API token to this repository.

---

## 1. Prerequisites

1. A Kaggle account: https://www.kaggle.com/
2. Kaggle API credentials (`kaggle.json`).
3. `kaggle` CLI installed locally (optional but recommended).

Install the Kaggle CLI (if you use Python):

```bash
pip install kaggle
```

---

## 2. Configure your Kaggle API token

1. Go to https://www.kaggle.com/<your-username>/account
2. Under **API**, click **Create New API Token**.
3. This downloads a file named `kaggle.json`.

Place the file in:

- **Linux/macOS**: `~/.kaggle/kaggle.json`
- **Windows**: `C:\Users\<User>\.kaggle\kaggle.json`

Or place it in the project root and export:

```bash
export KAGGLE_CONFIG_DIR=$(pwd)
```

Set restrictive permissions (recommended):

```bash
chmod 600 ~/.kaggle/kaggle.json
# or, if using the project root:
chmod 600 ./kaggle.json
```

> `.gitignore` is configured to ignore `kaggle.json` and `data/` directories.  
> Never commit `kaggle.json` or any secrets to version control.

---

## 3. Downloading the dataset (rupakroy)

Create a raw-data directory and download the dataset:

```bash
mkdir -p data/raw

kaggle datasets download \
  -d rupakroy/online-payments-fraud-detection-dataset \
  -p data/raw \
  --unzip
```

After running this, you should see one or more CSV files in `data/raw/`.  
The ingest pipeline in `pipelines/data_ingest.py` will take `--raw_path` pointing at one of these CSV files.

Suggested directory layout:

```text
data/
  raw/
    online-payments-fraud-detection-dataset.csv    # or actual filename from Kaggle
  processed/
    transactions_clean.parquet
    customer_features.parquet
    merchant_features.parquet
    device_features.parquet
    account_features.parquet
    geocell_features.parquet
```

---

## 4. Usage in notebooks and pipelines

- The ingest pipeline (`pipelines/data_ingest.py`) reads from `data/raw/` and writes to `data/processed/`.
- The entity table builder (`pipelines/build_entity_tables.py`) also writes to `data/processed/`.
- EDA notebooks:
  - `notebooks/01_kaggle_eda_and_baseline.ipynb` will read from `data/processed/transactions_clean.parquet`.
- Keep cleaning and feature engineering logic in code or notebooks, not as manual spreadsheet edits.

---

## 5. Licensing and terms

Always check the dataset’s Kaggle page for:

- License terms
- Attribution requirements
- Any usage restrictions

Ensure your use of the dataset complies with those terms, especially if you later expose demos publicly via HF Spaces.