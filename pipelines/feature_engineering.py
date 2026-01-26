import argparse
import json
import logging
import os
from datetime import timedelta
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("feast_fraud.pipelines.feature_engineering")


def _load_transactions(
    parquet_path: str,
    sample_rows: Optional[int],
    seed: int,
    skip_if_missing_input: bool,
) -> Optional[pd.DataFrame]:
    if not os.path.exists(parquet_path):
        msg = (
            f"Processed transactions parquet not found at {parquet_path}. "
            "Run pipelines/data_ingest.py first."
        )
        if skip_if_missing_input:
            logger.warning(
                "transactions_parquet_missing_skip",
                extra={"parquet_path": parquet_path},
            )
            return None
        logger.error("transactions_parquet_missing", extra={"parquet_path": parquet_path})
        raise FileNotFoundError(msg)

    logger.info(
        "Loading processed transactions",
        extra={"path": parquet_path, "sample_rows": sample_rows, "seed": seed},
    )
    df = pd.read_parquet(parquet_path)

    if sample_rows is not None and sample_rows > 0 and len(df) > sample_rows:
        df = df.sample(n=sample_rows, random_state=seed)
        logger.info(
            "Sampled transactions",
            extra={"sample_rows": sample_rows, "rows_after_sample": len(df)},
        )

    if "event_timestamp" not in df.columns:
        raise ValueError("Expected 'event_timestamp' column in processed data.")

    df["event_timestamp"] = pd.to_datetime(df["event_timestamp"], utc=True, errors="coerce")

    # Ensure required columns exist
    required_cols = [
        "customer_id",
        "merchant_id",
        "device_id",
        "account_id",
        "geo_cell_id",
        "amount",
        "type",
        "oldbalanceOrg",
        "newbalanceOrig",
        "oldbalanceDest",
        "newbalanceDest",
        "isFraud",
        "isFlaggedFraud",
    ]
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns in processed data: {missing}")

    return df


def _add_global_helper_columns(df: pd.DataFrame) -> pd.DataFrame:
    logger.info("Adding helper columns for feature engineering", extra={"rows": len(df)})

    df = df.copy()

    # Normalised transaction type
    df["tx_type_upper"] = df["type"].astype(str).str.upper()

    # Time-based helpers
    ts = pd.to_datetime(df["event_timestamp"], utc=True, errors="coerce")
    df["event_hour"] = ts.dt.hour.astype("int16")
    df["event_weekday"] = ts.dt.weekday.astype("int16")  # Monday=0
    df["is_weekend_tx"] = df["event_weekday"].isin([5, 6]).astype("int8")
    df["is_night_tx"] = ((df["event_hour"] < 6) | (df["event_hour"] >= 22)).astype("int8")

    # Balance deltas
    df["org_balance_delta"] = df["newbalanceOrig"] - df["oldbalanceOrg"]
    df["dest_balance_delta"] = df["newbalanceDest"] - df["oldbalanceDest"]
    df["balance_delta"] = df["org_balance_delta"]
    df["balance_delta_abs"] = df["balance_delta"].abs()

    # Insufficient funds proxy
    df["insufficient_funds_flag"] = (df["oldbalanceOrg"] < df["amount"]).astype("int8")

    # High-risk transaction types and one-hot encodings
    df["is_high_risk_type"] = df["tx_type_upper"].isin(["CASH_OUT", "TRANSFER"]).astype(
        "int8"
    )
    df["is_payment"] = (df["tx_type_upper"] == "PAYMENT").astype("int8")
    df["is_transfer"] = (df["tx_type_upper"] == "TRANSFER").astype("int8")
    df["is_cash_out"] = (df["tx_type_upper"] == "CASH_OUT").astype("int8")
    df["is_cash_in"] = (df["tx_type_upper"] == "CASH_IN").astype("int8")
    df["is_debit"] = (df["tx_type_upper"] == "DEBIT").astype("int8")

    # Customer-to-merchant repeat indicator
    df_sorted = df.sort_values(
        ["customer_id", "merchant_id", "event_timestamp"],
        kind="mergesort",
    )
    df_sorted["cust_merchant_tx_index"] = (
        df_sorted.groupby(["customer_id", "merchant_id"]).cumcount()
    )
    df_sorted["is_repeat_merchant"] = (
        df_sorted["cust_merchant_tx_index"] > 0
    ).astype("int8")

    # Propagate the repeat flag back to the original frame order
    df = df.merge(
        df_sorted[["customer_id", "merchant_id", "event_timestamp", "is_repeat_merchant"]],
        on=["customer_id", "merchant_id", "event_timestamp"],
        how="left",
        suffixes=("", "_repeat_tmp"),
    )
    df["is_repeat_merchant"] = df["is_repeat_merchant"].fillna(0).astype("int8")

    return df


def _limit_entities(
    df: pd.DataFrame,
    entity_col: str,
    max_entities: Optional[int],
) -> pd.DataFrame:
    if max_entities is None or max_entities <= 0:
        return df

    unique_ids = df[entity_col].dropna().unique()
    if len(unique_ids) <= max_entities:
        return df

    keep_ids = set(unique_ids[:max_entities])
    logger.info(
        "Limiting entities",
        extra={
            "entity_col": entity_col,
            "max_entities": max_entities,
            "unique_before": len(unique_ids),
            "unique_after": len(keep_ids),
        },
    )
    return df[df[entity_col].isin(keep_ids)].copy()


def _rolling_count(
    group: pd.core.groupby.generic.DataFrameGroupBy,
    col: str,
    window: str,
) -> pd.Series:
    return group[col].rolling(window).count().reset_index(level=0, drop=True)


def _rolling_sum(
    group: pd.core.groupby.generic.DataFrameGroupBy,
    col: str,
    window: str,
) -> pd.Series:
    return group[col].rolling(window).sum().reset_index(level=0, drop=True)


def _rolling_mean(
    group: pd.core.groupby.generic.DataFrameGroupBy,
    col: str,
    window: str,
) -> pd.Series:
    return group[col].rolling(window).mean().reset_index(level=0, drop=True)


def _rolling_max(
    group: pd.core.groupby.generic.DataFrameGroupBy,
    col: str,
    window: str,
) -> pd.Series:
    return group[col].rolling(window).max().reset_index(level=0, drop=True)


def _rolling_nunique(
    group: pd.core.groupby.generic.DataFrameGroupBy,
    col: str,
    window: str,
) -> pd.Series:
    return group[col].rolling(window).apply(lambda s: s.nunique(), raw=False).reset_index(
        level=0,
        drop=True,
    )


def _build_customer_features(
    df: pd.DataFrame,
    max_entities: Optional[int],
) -> pd.DataFrame:
    logger.info("Building customer features", extra={"rows": len(df)})

    cols = [
        "customer_id",
        "merchant_id",
        "event_timestamp",
        "amount",
        "is_night_tx",
        "is_payment",
        "is_transfer",
        "is_cash_out",
        "is_cash_in",
        "is_debit",
        "is_high_risk_type",
        "is_repeat_merchant",
    ]
    df_c = df[cols].copy()
    df_c = _limit_entities(df_c, "customer_id", max_entities)

    df_c = df_c.sort_values(["customer_id", "event_timestamp"])
    df_c = df_c.set_index("event_timestamp")

    group = df_c.groupby("customer_id", group_keys=False)

    # Velocity and amount windows
    for label, window in [("1h", "1h"), ("6h", "6h"), ("24h", "24h"), ("7d", "7d")]:
        df_c[f"cust_tx_count_{label}"] = _rolling_count(group, "amount", window)
        df_c[f"cust_tx_amount_sum_{label}"] = _rolling_sum(group, "amount", window)

    for label, window in [("24h", "24h"), ("7d", "7d")]:
        df_c[f"cust_tx_amount_mean_{label}"] = _rolling_mean(group, "amount", window)
        df_c[f"cust_tx_amount_max_{label}"] = _rolling_max(group, "amount", window)

    # Unique merchants
    for label, window in [("24h", "24h"), ("7d", "7d")]:
        df_c[f"cust_unique_merchants_{label}"] = _rolling_nunique(
            group,
            "merchant_id",
            window,
        )

    # Night transaction ratio
    df_c["cust_night_tx_ratio_7d"] = _rolling_mean(group, "is_night_tx", "7d")

    # Type distribution ratios
    type_cols: List[Tuple[str, str]] = [
        ("is_payment", "payment"),
        ("is_transfer", "transfer"),
        ("is_cash_out", "cash_out"),
        ("is_cash_in", "cash_in"),
        ("is_debit", "debit"),
    ]
    for col, suffix in type_cols:
        df_c[f"cust_type_{suffix}_ratio_7d"] = _rolling_mean(group, col, "7d")

    # Cross-entity consistency
    df_c["cust_to_merchant_repeat_ratio_7d"] = _rolling_mean(
        group,
        "is_repeat_merchant",
        "7d",
    )
    df_c["cust_high_risk_type_ratio_7d"] = _rolling_mean(
        group,
        "is_high_risk_type",
        "7d",
    )

    df_c = df_c.reset_index()  # event_timestamp back as column
    df_c["created_timestamp"] = df_c["event_timestamp"]

    logger.info(
        "Customer features built",
        extra={"rows": len(df_c), "columns": list(df_c.columns)},
    )
    return df_c


def _build_merchant_features(
    df: pd.DataFrame,
    max_entities: Optional[int],
) -> pd.DataFrame:
    logger.info("Building merchant features", extra={"rows": len(df)})
    cols = [
        "merchant_id",
        "customer_id",
        "event_timestamp",
        "amount",
        "isFraud",
    ]
    df_m = df[cols].copy()
    df_m = _limit_entities(df_m, "merchant_id", max_entities)

    df_m = df_m.sort_values(["merchant_id", "event_timestamp"])
    df_m = df_m.set_index("event_timestamp")

    group = df_m.groupby("merchant_id", group_keys=False)

    df_m["mch_tx_count_24h"] = _rolling_count(group, "amount", "24h")
    df_m["mch_tx_count_7d"] = _rolling_count(group, "amount", "7d")
    df_m["mch_amount_mean_7d"] = _rolling_mean(group, "amount", "7d")
    df_m["mch_unique_customers_7d"] = _rolling_nunique(group, "customer_id", "7d")
    df_m["mch_fraud_rate_7d"] = _rolling_mean(group, "isFraud", "7d")

    df_m = df_m.reset_index()
    df_m["created_timestamp"] = df_m["event_timestamp"]

    logger.info(
        "Merchant features built",
        extra={"rows": len(df_m), "columns": list(df_m.columns)},
    )
    return df_m


def _build_device_features(
    df: pd.DataFrame,
    max_entities: Optional[int],
) -> pd.DataFrame:
    logger.info("Building device features", extra={"rows": len(df)})
    cols = [
        "device_id",
        "customer_id",
        "event_timestamp",
        "amount",
    ]
    df_d = df[cols].copy()
    df_d = _limit_entities(df_d, "device_id", max_entities)

    df_d = df_d.sort_values(["device_id", "event_timestamp"])
    df_d = df_d.set_index("event_timestamp")

    group = df_d.groupby("device_id", group_keys=False)

    df_d["dev_tx_count_10m"] = _rolling_count(group, "amount", "10min")
    df_d["dev_tx_count_1h"] = _rolling_count(group, "amount", "1h")
    df_d["dev_tx_count_24h"] = _rolling_count(group, "amount", "24h")
    df_d["dev_unique_customers_24h"] = _rolling_nunique(group, "customer_id", "24h")
    df_d["dev_unique_customers_7d"] = _rolling_nunique(group, "customer_id", "7d")
    df_d["dev_amount_max_24h"] = _rolling_max(group, "amount", "24h")

    df_d = df_d.reset_index()
    df_d["created_timestamp"] = df_d["event_timestamp"]

    logger.info(
        "Device features built",
        extra={"rows": len(df_d), "columns": list(df_d.columns)},
    )
    return df_d


def _build_account_features(
    df: pd.DataFrame,
    max_entities: Optional[int],
) -> pd.DataFrame:
    logger.info("Building account features", extra={"rows": len(df)})
    cols = [
        "account_id",
        "event_timestamp",
        "amount",
        "org_balance_delta",
        "dest_balance_delta",
        "balance_delta",
        "balance_delta_abs",
        "insufficient_funds_flag",
    ]
    df_a = df[cols].copy()
    df_a = _limit_entities(df_a, "account_id", max_entities)

    df_a = df_a.sort_values(["account_id", "event_timestamp"])
    df_a = df_a.set_index("event_timestamp")

    group = df_a.groupby("account_id", group_keys=False)

    # Per-transaction deltas are already columns
    df_a["acct_org_balance_delta"] = df_a["org_balance_delta"]
    df_a["acct_dest_balance_delta"] = df_a["dest_balance_delta"]

    # Aggregated balance dynamics
    df_a["acct_balance_delta_mean_24h"] = _rolling_mean(group, "balance_delta", "24h")
    df_a["acct_balance_delta_mean_7d"] = _rolling_mean(group, "balance_delta", "7d")
    df_a["acct_balance_delta_abs_mean_7d"] = _rolling_mean(
        group,
        "balance_delta_abs",
        "7d",
    )
    df_a["acct_insufficient_funds_rate_24h"] = _rolling_mean(
        group,
        "insufficient_funds_flag",
        "24h",
    )
    df_a["acct_insufficient_funds_rate_7d"] = _rolling_mean(
        group,
        "insufficient_funds_flag",
        "7d",
    )

    # Additional velocity-style account features
    df_a["acct_tx_count_24h"] = _rolling_count(group, "amount", "24h")
    df_a["acct_tx_count_7d"] = _rolling_count(group, "amount", "7d")
    df_a["acct_tx_amount_sum_24h"] = _rolling_sum(group, "amount", "24h")
    df_a["acct_tx_amount_sum_7d"] = _rolling_sum(group, "amount", "7d")

    df_a = df_a.reset_index()
    df_a["created_timestamp"] = df_a["event_timestamp"]

    logger.info(
        "Account features built",
        extra={"rows": len(df_a), "columns": list(df_a.columns)},
    )
    return df_a


def _build_geocell_features(
    df: pd.DataFrame,
    max_entities: Optional[int],
) -> pd.DataFrame:
    logger.info("Building geo-cell features", extra={"rows": len(df)})
    cols = [
        "geo_cell_id",
        "customer_id",
        "event_timestamp",
        "amount",
    ]
    df_g = df[cols].copy()
    df_g = _limit_entities(df_g, "geo_cell_id", max_entities)

    df_g = df_g.sort_values(["geo_cell_id", "event_timestamp"])
    df_g = df_g.set_index("event_timestamp")

    group = df_g.groupby("geo_cell_id", group_keys=False)

    df_g["geo_tx_count_24h"] = _rolling_count(group, "amount", "24h")
    df_g["geo_tx_count_7d"] = _rolling_count(group, "amount", "7d")
    df_g["geo_unique_customers_7d"] = _rolling_nunique(group, "customer_id", "7d")
    df_g["geo_amount_mean_7d"] = _rolling_mean(group, "amount", "7d")

    df_g = df_g.reset_index()
    df_g["created_timestamp"] = df_g["event_timestamp"]

    logger.info(
        "Geo-cell features built",
        extra={"rows": len(df_g), "columns": list(df_g.columns)},
    )
    return df_g


def _write_parquet_and_schema(df: pd.DataFrame, out_path: str) -> None:
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    logger.info(
        "Writing feature table",
        extra={"path": out_path, "rows": len(df), "columns": list(df.columns)},
    )
    df.to_parquet(out_path, index=False)

    schema_path = os.path.splitext(out_path)[0] + "_schema.json"
    schema: Dict[str, str] = {col: str(dtype) for col, dtype in df.dtypes.items()}
    with open(schema_path, "w", encoding="utf-8") as f:
        json.dump(schema, f, indent=2)
    logger.info("Wrote schema snapshot", extra={"schema_path": schema_path})


def run(
    transactions_path: str,
    out_dir: str,
    sample_rows: Optional[int],
    max_entities: Optional[int],
    seed: int,
    skip_if_missing_input: bool,
) -> None:
    df = _load_transactions(
        parquet_path=transactions_path,
        sample_rows=sample_rows,
        seed=seed,
        skip_if_missing_input=skip_if_missing_input,
    )
    if df is None:
        # Graceful no-op when input is missing (used in CI workflows)
        logger.warning(
            "feature_engineering_skipped_missing_input",
            extra={"transactions_path": transactions_path},
        )
        return

    df = _add_global_helper_columns(df)

    # Build per-entity feature tables
    customer_features = _build_customer_features(df, max_entities=max_entities)
    merchant_features = _build_merchant_features(df, max_entities=max_entities)
    device_features = _build_device_features(df, max_entities=max_entities)
    account_features = _build_account_features(df, max_entities=max_entities)
    geocell_features = _build_geocell_features(df, max_entities=max_entities)

    # Write parquet + schema snapshots
    out_base = os.path.join(out_dir, "feature_tables")
    outputs = [
        (customer_features, os.path.join(out_base, "customer_features_v1.parquet")),
        (merchant_features, os.path.join(out_base, "merchant_features_v1.parquet")),
        (device_features, os.path.join(out_base, "device_features_v1.parquet")),
        (account_features, os.path.join(out_base, "account_features_v1.parquet")),
        (geocell_features, os.path.join(out_base, "geocell_features_v1.parquet")),
    ]

    for table_df, path in outputs:
        _write_parquet_and_schema(table_df, path)

    logger.info(
        "Feature engineering completed",
        extra={
            "out_dir": out_dir,
            "tables": [os.path.basename(p) for _, p in outputs],
        },
    )


def parse_args(args: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build windowed feature tables per entity from cleaned transactions parquet."
        ),
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
        help="Output directory for feature tables (feature_tables/*_features_v1.parquet).",
    )
    parser.add_argument(
        "--sample_rows",
        type=int,
        default=None,
        help=(
            "Optional maximum number of transaction rows to sample for feature engineering. "
            "If omitted or non-positive, use all rows."
        ),
    )
    parser.add_argument(
        "--max_entities",
        type=int,
        default=None,
        help=(
            "Optional cap on the number of unique entities per entity type "
            "(customer, merchant, device, account, geo_cell)."
        ),
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed used for sampling.",
    )
    parser.add_argument(
        "--skip_if_missing_input",
        action="store_true",
        help=(
            "If set, skip feature engineering gracefully when the transactions parquet "
            "is missing instead of raising FileNotFoundError. Useful in CI."
        ),
    )
    return parser.parse_args(args=args)


def main(cli_args: Optional[List[str]] = None) -> None:
    try:
        args = parse_args(cli_args)
        sample_rows: Optional[int]
        if args.sample_rows is not None and args.sample_rows <= 0:
            sample_rows = None
        else:
            sample_rows = args.sample_rows

        run(
            transactions_path=args.transactions_path,
            out_dir=args.out_dir,
            sample_rows=sample_rows,
            max_entities=args.max_entities,
            seed=args.seed,
            skip_if_missing_input=args.skip_if_missing_input,
        )
    except Exception:  # noqa: BLE001
        logger.exception("feature_engineering_failed")
        raise


if __name__ == "__main__":
    main()