#!/usr/bin/env bash
set -euo pipefail

echo "Kaggle Online Payments Fraud Detection Dataset download helper"
echo
echo "This script assumes you have:"
echo "  - A Kaggle account"
echo "  - The Kaggle CLI installed (pip install kaggle)"
echo "  - A valid kaggle.json API token configured"
echo

cat &lt;&lt;'EOF'
KAGGLE API SETUP (one-time):

1) Go to: https://www.kaggle.com/&lt;your-username&gt;/account
2) Under API, click "Create New API Token".
   This downloads a file named kaggle.json.
3) Place kaggle.json in one of the following locations:

   - Linux/macOS:  ~/.kaggle/kaggle.json
   - Windows:      C:\Users&lt;User&gt\.kaggle\kaggle.json

   OR put kaggle.json in this project root and run:
       export KAGGLE_CONFIG_DIR=$(pwd)

4) Restrict permissions on kaggle.json (recommended):
       chmod 600 ~/.kaggle/kaggle.json
   or:
       chmod 600 ./kaggle.json

NOTE: kaggle.json is secret and must never be committed to Git.
      .gitignore is configured to ignore kaggle.json and data/ directories.

DATASET DOWNLOAD (rupakroy/online-payments-fraud-detection-dataset):

The project expects the Kaggle dataset:
  rupakroy/online-payments-fraud-detection-dataset

To download and unzip into data/raw/:

    mkdir -p data/raw
    kaggle datasets download \
        -d rupakroy/online-payments-fraud-detection-dataset \
        -p data/raw \
        --unzip

After download, you should see one or more CSV files under data/raw/.

This script is intentionally non-destructive: it only prints instructions.
Run the commands above manually so you stay in control of where credentials live.
EOF