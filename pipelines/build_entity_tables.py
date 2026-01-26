import argparse
import logging
import os
from typing import List, Optional, Tuple

import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("feast_fraud.pipelines.build_entity_tables")


def _load_transactions(parquet_path: str) -> pd.DataFrame:
    if not os.path.exists(parquet_path):
        logger.error(
            "Processed transactions parquet not found. Run data_ingest first.",
            extra={"parquet_path": parquet_path},
        )
        raise FileNotFoundError(
            f"Processed parquet not found at {parquet_path}. "
            "Run pipelines/data_ingest.py before build_entity_tables.py."
        )

    logger.info("Loading processed transactions", extra={"path": parquet_path})
    df = pd.read_parquet(parquet_path)
    if "event_timestamp" not in df.columns:
        raise ValueError("Expected 'event_timestamp' column in processed data.")
    return df


def _build_entity_features(
    df: pd.DataFrame,
    entity_col: str,
    counterpart_col: Optional[str],
) -> pd.DataFrame:
    logger.info(
        "Building entity features",
        extra={"entity_col": entity_col, "counterpart_col": counterpart_col},
    )

    group = df.groupby(entity_col)

    agg_dict = {
        "amount": ["count", "sum", "mean", "max"],
        "isFraud": ["mean"],
        "isFlaggedFraud": ["mean"],
    }

    agg_df = group.agg(agg_dict)
    agg_df.columns = [
        "_".join(col).strip()
        for col in agg_df.columns.to_flat_index()
    ]
    agg_df = agg_df.rename(
        columns={
            "amount_count": "txn_count_total",
            "amount_sum": "amount_sum_total",
            "amount_mean": "amount_mean",
            "amount_max": "amount_max",
            "isFraud_mean": "fraud_rate",
            "isFlaggedFraud_mean": "flagged_rate",
        }
    )

    if counterpart_col is not None:
        uniq_counts = (
            df.groupby(entity_col)[counterpart_col].nunique().rename("unique_counterparty_count")
        )
        agg_df = agg_df.join(uniq_counts, how="left")
    else:
        agg_df["unique_counterparty_count"] = 0

    ts = group["event_timestamp"].max().rename("event_timestamp")
    agg_df = agg_df.join(ts, how="left")

    agg_df = agg_df.reset_index()

    logger.info(
        "Entity features built",
        extra={"entity_col": entity_col, "rows": len(agg_df)},
    )
    return agg_df


def _write_entity_table(df: pd.DataFrame, out_path: str, entity_col: str) -> None:
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    logger.info(
        "Writing entity feature table",
        extra={"path": out_path, "rows": len(df)},
    )
    df.to_parquet(out_path, index=False)

    if "event_timestamp" not in df.columns:
        raise ValueError(
            f"Entity table for {entity_col} must include 'event_timestamp' column."
        )


def run(transactions_path: str, out_dir: str) -> None:
    df = _load_transactions(transactions_path)

    jobs: List[Tuple[str, str, Optional[str]]] = [
        ("customer_id", os.path.join(out_dir, "customer_features.parquet"), "merchant_id"),
        ("merchant_id", os.path.join(out_dir, "merchant_features.parquet"), "customer_id"),
        ("device_id", os.path.join(out_dir, "device_features.parquet"), "merchant_id"),
        ("account_id", os.path.join(out_dir, "account_features.parquet"), "merchant_id"),
        ("geo_cell_id", os.path.join(out_dir, "geocell_features.parquet"), "customer_id"),
    ]

    for entity_col, path, counterpart_col in jobs:
        features_df = _build_entity_features(
            df=df,
            entity_col=entity_col,
            counterpart_col=counterpart_col,
        )
        _write_entity_table(features_df, path, entity_col)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build entity-level aggregate tables from cleaned transactions parquet.",
    )
    parser.add_argument(
        "--transactions_path",
        type=str,
        default="data/processed/transactions_clean.parquet",
        help="Path to cleaned transactions parquet.",
    )
    parser.add_argument(
        "--out_dir",
        type=str,
        default="data/processed",
        help="Output directory for entity parquet tables.",
    )
    return parser.parse_args()


def main() -> None:
    try:
        args = parse_args()
        run(transactions_path=args.transactions_path, out_dir=args.out_dir)
    except Exception:
        logger.exception("build_entity_tables_failed")
        raise


if __name__ == "__main__":
    main()