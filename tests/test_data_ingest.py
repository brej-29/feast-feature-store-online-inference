import os
from pathlib import Path

import pandas as pd
import pytest


PROCESSED_PATH = Path("data/processed/transactions_clean.parquet")


@pytest.mark.skipif(
    not PROCESSED_PATH.exists(),
    reason="Processed parquet not found; run pipelines/data_ingest.py first.",
)
def test_transactions_clean_basic_schema():
    df = pd.read_parquet(PROCESSED_PATH)

    expected_columns = {
        "step",
        "type",
        "amount",
        "nameOrig",
        "oldbalanceOrg",
        "newbalanceOrig",
        "nameDest",
        "oldbalanceDest",
        "newbalanceDest",
        "isFraud",
        "isFlaggedFraud",
        "event_timestamp",
        "customer_id",
        "merchant_id",
        "account_id",
        "geo_cell_id",
        "device_id",
    }

    missing = expected_columns - set(df.columns)
    assert not missing, f"Missing columns in transactions_clean.parquet: {missing}"

    # Basic dtype checks
    assert pd.api.types.is_datetime64_any_dtype(df["event_timestamp"])
    assert pd.api.types.is_numeric_dtype(df["amount"])
    assert pd.api.types.is_integer_dtype(df["isFraud"])
    assert pd.api.types.is_integer_dtype(df["isFlaggedFraud"])


def test_data_directories_ignored():
    # Sanity check that data directories are configured as non-tracked artifacts.
    gitignore_path = Path(".gitignore")
    assert gitignore_path.exists()
    contents = gitignore_path.read_text()
    assert "data/" in contents
    assert "data/raw/" in contents
    assert "data/processed/" in contents