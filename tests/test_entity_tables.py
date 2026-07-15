from pathlib import Path

import pandas as pd
import pytest

ENTITY_FILES = [
    ("customer_id", Path("data/processed/customer_features.parquet")),
    ("merchant_id", Path("data/processed/merchant_features.parquet")),
    ("device_id", Path("data/processed/device_features.parquet")),
    ("account_id", Path("data/processed/account_features.parquet")),
    ("geo_cell_id", Path("data/processed/geocell_features.parquet")),
]

V2_FEATURE_COLUMNS = [
    "txn_count_prior",
    "amount_sum_prior",
    "amount_mean_prior",
    "amount_max_prior",
    "unique_counterparty_count_prior",
    "flagged_rate_prior",
    "entity_age_hours",
    "matured_txn_count_prior",
    "fraud_txn_count_prior",
    "fraud_rate_prior",
]


@pytest.mark.skipif(
    not any(path.exists() for _, path in ENTITY_FILES),
    reason="Entity parquet files not found; run pipelines/build_entity_tables.py first.",
)
def test_entity_tables_have_required_columns():
    for entity_col, path in ENTITY_FILES:
        if not path.exists():
            continue

        df = pd.read_parquet(path)
        assert entity_col in df.columns, f"{entity_col} missing in {path}"
        assert "event_timestamp" in df.columns, f"event_timestamp missing in {path}"

        for feature_col in V2_FEATURE_COLUMNS:
            assert feature_col in df.columns, f"{feature_col} missing in {path}"

        # Point-in-time tables have one row per (entity, timestamp), and the
        # first row of every entity must show zero prior history.
        assert not df.duplicated([entity_col, "event_timestamp"]).any()
        first_rows = (
            df.sort_values("event_timestamp", kind="stable").groupby(entity_col).head(1)
        )
        assert (
            first_rows["txn_count_prior"] == 0
        ).all(), f"non-zero history on first rows in {path}"


@pytest.mark.skipif(
    not Path("data/processed/customer_features.parquet").exists(),
    reason="Customer features parquet not found.",
)
def test_customer_table_has_last_txn_columns():
    df = pd.read_parquet("data/processed/customer_features.parquet")
    for col in ["last_txn_amount", "last_txn_type_code", "last_txn_hour", "last_txn_is_flagged"]:
        assert col in df.columns
