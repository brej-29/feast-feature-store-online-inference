import os

import pandas as pd
import pytest

FEATURE_TABLE_DIR = "data/processed/feature_tables"

ENTITY_TABLES = [
    ("customer_features_v1.parquet", "customer_id"),
    ("merchant_features_v1.parquet", "merchant_id"),
    ("device_features_v1.parquet", "device_id"),
    ("account_features_v1.parquet", "account_id"),
    ("geocell_features_v1.parquet", "geo_cell_id"),
]


@pytest.mark.skipif(
    not os.path.exists(FEATURE_TABLE_DIR),
    reason="Feature tables directory missing; run pipelines/feature_engineering.py first.",
)
def test_feature_tables_have_at_least_50_features():
    feature_cols = set()

    for filename, _ in ENTITY_TABLES:
        path = os.path.join(FEATURE_TABLE_DIR, filename)
        if not os.path.exists(path):
            # Allow partial availability; this is a smoke check.
            continue

        df = pd.read_parquet(path)

        non_feature_cols = {
            "customer_id",
            "merchant_id",
            "device_id",
            "account_id",
            "geo_cell_id",
            "event_timestamp",
            "created_timestamp",
        }
        for col in df.columns:
            if col not in non_feature_cols:
                feature_cols.add(col)

    if not feature_cols:
        pytest.skip(
            "No feature tables found under data/processed/feature_tables; "
            "run pipelines/feature_engineering.py to generate them.",
        )

    assert (
        len(feature_cols) >= 50
    ), f"Expected at least 50 engineered feature columns, found {len(feature_cols)}"