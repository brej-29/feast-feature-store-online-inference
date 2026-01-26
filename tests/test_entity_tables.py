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

        for feature_col in [
            "txn_count_total",
            "amount_sum_total",
            "amount_mean",
            "amount_max",
            "fraud_rate",
            "flagged_rate",
            "unique_counterparty_count",
        ]:
            assert feature_col in df.columns, f"{feature_col} missing in {path}"