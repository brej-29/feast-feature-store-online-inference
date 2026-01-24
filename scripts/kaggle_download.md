# Kaggle Dataset Download Instructions

This document describes how to download the **Online Payments Fraud Detection Dataset** from Kaggle for local use.

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

1. Go to https://www.kaggle.com/&lt;your-username&gt;/account
2. Under **API**, click **Create New API Token**.
3. This downloads a file named `kaggle.json`.

Place the file in:

- **Linux/macOS**: `~/.kaggle/kaggle.json`
- **Windows**: `C:\Users&lt;User&gt;\.kaggle\kaggle.json`

Or place it in the project root and export:

```bash
export KAGGLE_CONFIG_DIR=$(pwd)
```

> `.gitignore` is configured to ignore `kaggle.json`.  
> Never commit `kaggle.json` or any secrets to version control.

---

## 3. Downloading the dataset

The exact Kaggle dataset slug may vary; at the time of writing, one common dataset is:

- Name: **Online Payments Fraud Detection Dataset**

Once you know the dataset slug (for example `mishra5001/online-payments-fraud-detection-dataset`),
you can download it as follows:

```bash
# Example: adjust the dataset slug as needed
kaggle datasets download -d mishra5001/online-payments-fraud-detection-dataset -p data/raw --unzip
```

This will download and unzip the dataset under `data/raw/`.

Directory layout suggestion:

```text
data/
  raw/
    onlinefraud.csv           # or actual dataset filename(s)
  interim/
  processed/
```

---

## 4. Usage in notebooks and pipelines

- Point your EDA notebook (`notebooks/00_eda_feature_store_story.ipynb`) to read from `data/raw/`.
- Keep any data cleaning and feature engineering logic in code or notebooks, not as manual spreadsheet edits.
- If you generate derived datasets (e.g., train/validation/test), store them under `data/processed/`.

---

## 5. Licensing and terms

Always check the dataset’s Kaggle page for:

- License terms
- Attribution requirements
- Any usage restrictions

Ensure your use of the dataset complies with those terms, especially if you later expose demos publicly via HF Spaces.