#!/usr/bin/env python
"""Seed a bounded, free-tier-safe subset of features into the online store.

A full `feast materialize` would write millions of entity rows -- far beyond
Neon's free 0.5 GB and enough to OOM a 512 MB Render container on boot. This
instead writes only the latest row for the top-N most-active entities per
view via ``FeatureStore.write_to_online_store`` (direct online write, no
offline scan of the whole table), so the deployed demo can serve real batch
features for a curated set of entities while staying tiny.

Live/streaming features still arrive through the PushSource path at runtime;
this only backfills the batch profile views for a representative sample.
"""

import argparse
import logging
import os
from typing import List

import pandas as pd

from pipelines.pg_config import apply_postgres_url_env

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("feast_fraud.scripts.seed_demo_online")

PROFILE_FEATURES = [
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
REALTIME_FEATURES = [
    "last_txn_amount",
    "last_txn_type_code",
    "last_txn_hour",
    "last_txn_is_flagged",
]

# (feature_view, parquet, entity_key, feature_columns)
SEED_JOBS = [
    ("customer_profile_v2", "customer_features.parquet", "customer_id", PROFILE_FEATURES),
    ("customer_realtime_v1", "customer_features.parquet", "customer_id", REALTIME_FEATURES),
    ("merchant_profile_v2", "merchant_features.parquet", "merchant_id", PROFILE_FEATURES),
    ("device_profile_v2", "device_features.parquet", "device_id", PROFILE_FEATURES),
    ("account_profile_v2", "account_features.parquet", "account_id", PROFILE_FEATURES),
    ("geocell_profile_v2", "geocell_features.parquet", "geo_cell_id", PROFILE_FEATURES),
]


def _latest_top_n(df: pd.DataFrame, entity_key: str, n: int) -> pd.DataFrame:
    """Latest row per entity, restricted to the N most-active entities."""
    latest = (
        df.sort_values("event_timestamp", kind="stable")
        .groupby(entity_key, sort=False)
        .tail(1)
    )
    if "txn_count_prior" in latest.columns and len(latest) > n:
        latest = latest.nlargest(n, "txn_count_prior")
    elif len(latest) > n:
        latest = latest.head(n)
    return latest.reset_index(drop=True)


def run(data_dir: str, repo_path: str, max_entities: int) -> None:
    from feast import FeatureStore

    apply_postgres_url_env()
    store = FeatureStore(repo_path=repo_path)

    for view, parquet, entity_key, feature_cols in SEED_JOBS:
        path = os.path.join(data_dir, parquet)
        if not os.path.exists(path):
            logger.warning("seed_skip_missing_table", extra={"path": path})
            continue

        df = pd.read_parquet(path)
        subset = _latest_top_n(df, entity_key, max_entities)
        cols: List[str] = [entity_key, "event_timestamp", *feature_cols]
        payload = subset[cols].copy()

        store.write_to_online_store(view, payload)
        logger.info(
            "seeded_online_view",
            extra={"view": view, "rows": len(payload)},
        )

    logger.info("seed_demo_online_complete", extra={"max_entities": max_entities})


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data_dir", default="data/processed")
    parser.add_argument("--repo_path", default=os.getenv("FEAST_REPO_PATH", "feature_repo"))
    parser.add_argument(
        "--max_entities",
        type=int,
        default=int(os.getenv("SEED_MAX_ENTITIES", "5000")),
        help="Max entities seeded per view (latest row each). Keeps the online "
        "store within free-tier limits.",
    )
    args = parser.parse_args()
    run(args.data_dir, args.repo_path, args.max_entities)


if __name__ == "__main__":
    main()
