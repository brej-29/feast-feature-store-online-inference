import argparse
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
from pandera.errors import SchemaErrors

from pipelines.encoders import deterministic_hash
from pipelines.schemas import CleanedTransactionSchema

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("feast_fraud.pipelines.data_ingest")


REQUIRED_COLUMNS: List[str] = [
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
]


def _validate_columns(df: pd.DataFrame) -> None:
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")


def _resolve_base_time(base_time: str, max_step: int) -> datetime:
    """Resolve the simulation base time.

    "recent" anchors the simulated window so it ends roughly one hour before
    now. This keeps online-store TTLs and `feast materialize-incremental`
    meaningful when serving the historical dataset as if it were live traffic.
    Any other value must be an ISO-8601 timestamp (assumed UTC if naive).
    """
    if base_time == "recent":
        now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
        return now - timedelta(hours=max_step + 1)
    parsed = datetime.fromisoformat(base_time)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _clean_and_augment(df: pd.DataFrame, base_time: str = "recent") -> pd.DataFrame:
    logger.info("Starting cleaning and augmentation", extra={"rows": len(df)})

    # Validate columns early
    _validate_columns(df)

    # Strip whitespace from string columns of interest
    for col in ["type", "nameOrig", "nameDest"]:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip()

    # Cast numeric columns
    # NOTE: column names follow the Kaggle schema:
    # - oldbalanceOrg
    # - newbalanceOrig
    # - oldbalanceDest
    # - newbalanceDest
    numeric_cols = [
        "step",
        "amount",
        "oldbalanceOrg",
        "newbalanceOrig",
        "oldbalanceDest",
        "newbalanceDest",
    ]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # Targets as int 0/1
    for col in ["isFraud", "isFlaggedFraud"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype("int64")

    # Drop impossible rows (negative amounts or balances)
    # Note: Kaggle column is newbalanceOrig (not newbalanceOrg).
    mask_impossible = (
        (df["amount"] < 0)
        | (df["oldbalanceOrg"] < 0)
        | (df["newbalanceOrig"] < 0)
        | (df["oldbalanceDest"] < 0)
        | (df["newbalanceDest"] < 0)
    )
    num_impossible = int(mask_impossible.sum())
    if num_impossible:
        logger.warning(
            "Dropping impossible rows with negative values",
            extra={"dropped_rows": num_impossible},
        )
        df = df.loc[~mask_impossible].copy()

    # Event timestamp from step
    df["step"] = df["step"].astype("int64")
    resolved_base = _resolve_base_time(base_time, max_step=int(df["step"].max()))
    logger.info("Using base time for event timestamps", extra={"base_time": resolved_base.isoformat()})
    df["event_timestamp"] = resolved_base + pd.to_timedelta(df["step"], unit="h")

    # Derived IDs
    df["customer_id"] = df["nameOrig"].astype(str)
    df["merchant_id"] = df["nameDest"].astype(str)
    df["account_id"] = df["nameOrig"].astype(str)
    df["geo_cell_id"] = df["nameDest"].astype(str).apply(deterministic_hash)
    df["device_id"] = (
        df["nameOrig"].astype(str) + "|" + df["nameDest"].astype(str)
    ).apply(deterministic_hash)

    logger.info(
        "Completed cleaning and augmentation",
        extra={"rows": len(df)},
    )
    return df


def _load_sample(
    raw_path: str,
    sample_rows: Optional[int],
    seed: int,
    sample_strategy: str = "uniform",
) -> pd.DataFrame:
    logger.info(
        "Loading raw CSV",
        extra={
            "raw_path": raw_path,
            "sample_rows": sample_rows,
            "seed": seed,
            "sample_strategy": sample_strategy,
        },
    )

    if sample_rows is None:
        df = pd.read_csv(raw_path)
        logger.info("Loaded full dataset", extra={"rows": len(df)})
        return df

    if sample_strategy == "uniform":
        # Random sample across the FULL simulated time range. The previous
        # "head" strategy silently kept only the first hours of the
        # simulation, which breaks temporal train/test splits and
        # point-in-time feature semantics.
        df = pd.read_csv(raw_path)
        total = len(df)
        if total > sample_rows:
            df = df.sample(n=sample_rows, random_state=seed)
        df = df.sort_values("step", kind="stable").reset_index(drop=True)
        logger.info(
            "Uniform sample constructed",
            extra={"total_rows_scanned": total, "sample_rows": len(df)},
        )
        return df

    chunksize = 100_000
    sample: Optional[pd.DataFrame] = None
    total_rows = 0

    for chunk in pd.read_csv(raw_path, chunksize=chunksize):
        chunk_len = len(chunk)
        total_rows += chunk_len
        if sample is None:
            if chunk_len >= sample_rows:
                sample = chunk.sample(n=sample_rows, random_state=seed)
                break
            sample = chunk.copy()
        else:
            needed = max(sample_rows - len(sample), 0)
            if needed <= 0:
                break
            if chunk_len <= needed:
                sample = pd.concat([sample, chunk], ignore_index=True)
            else:
                frac = needed / float(chunk_len)
                take = int(np.ceil(frac * chunk_len))
                sampled_chunk = chunk.sample(n=take, random_state=seed)
                sample = pd.concat([sample, sampled_chunk], ignore_index=True)

    if sample is None:
        raise RuntimeError("No data read from CSV; is the file empty?")

    if len(sample) > sample_rows:
        sample = sample.sample(n=sample_rows, random_state=seed)

    logger.info(
        "Constructed sample from CSV",
        extra={"total_rows_scanned": total_rows, "sample_rows": len(sample)},
    )
    return sample


def _write_schema(df: pd.DataFrame, out_path: str) -> None:
    logger.info("Writing schema snapshot", extra={"path": out_path})
    schema: Dict[str, Any] = {
        col: str(dtype) for col, dtype in df.dtypes.items()
    }
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(schema, f, indent=2)


def _write_profile(df: pd.DataFrame, out_path: str) -> None:
    logger.info("Writing data profile", extra={"path": out_path})
    profile: Dict[str, Any] = {
        "row_count": int(len(df)),
        "columns": {},
    }

    for col in df.columns:
        series = df[col]
        col_profile: Dict[str, Any] = {
            "dtype": str(series.dtype),
            "null_count": int(series.isna().sum()),
        }
        if pd.api.types.is_numeric_dtype(series):
            col_profile.update(
                {
                    "min": float(series.min()) if not series.isna().all() else None,
                    "max": float(series.max()) if not series.isna().all() else None,
                }
            )
        elif pd.api.types.is_datetime64_any_dtype(series):
            col_profile.update(
                {
                    "min": series.min().isoformat() if not series.isna().all() else None,
                    "max": series.max().isoformat() if not series.isna().all() else None,
                }
            )
        profile["columns"][col] = col_profile

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(profile, f, indent=2)


def run(
    raw_path: str,
    out_dir: str,
    sample_rows: Optional[int],
    seed: int,
    sample_strategy: str = "uniform",
    base_time: str = "recent",
) -> None:
    if not os.path.exists(raw_path):
        logger.error(
            "Raw CSV not found; please download the Kaggle dataset first.",
            extra={"raw_path": raw_path},
        )
        raise FileNotFoundError(
            f"Raw CSV not found at {raw_path}. "
            "See scripts/kaggle_download.sh and scripts/kaggle_download.md."
        )

    os.makedirs(out_dir, exist_ok=True)

    df_raw = _load_sample(
        raw_path=raw_path,
        sample_rows=sample_rows,
        seed=seed,
        sample_strategy=sample_strategy,
    )
    df_clean = _clean_and_augment(df_raw, base_time=base_time)

    try:
        CleanedTransactionSchema.validate(df_clean, lazy=True)
    except SchemaErrors as exc:
        logger.error(
            "cleaned_transactions_schema_validation_failed",
            extra={"failure_count": len(exc.failure_cases)},
        )
        raise ValueError(
            f"Cleaned transactions failed schema validation:\n{exc.failure_cases}"
        ) from exc
    logger.info("Cleaned transactions passed schema validation", extra={"rows": len(df_clean)})

    parquet_path = os.path.join(out_dir, "transactions_clean.parquet")
    schema_path = os.path.join(out_dir, "transactions_full_schema.json")
    profile_path = os.path.join(out_dir, "data_profile.json")

    logger.info("Writing cleaned parquet", extra={"path": parquet_path})
    # coerce_timestamps="us": pandas/pyarrow default to nanosecond timestamps,
    # which Spark 3.5 refuses to read ("Illegal Parquet type: INT64
    # (TIMESTAMP(NANOS,true))"). Microseconds are the interop-safe precision
    # and far finer than this hourly-resolution data needs.
    df_clean.to_parquet(
        parquet_path, index=False, coerce_timestamps="us", allow_truncated_timestamps=True
    )

    _write_schema(df_clean, schema_path)
    _write_profile(df_clean, profile_path)

    logger.info(
        "Data ingest completed",
        extra={
            "parquet_path": parquet_path,
            "rows": len(df_clean),
        },
    )


def parse_args(args: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ingest Kaggle fraud dataset CSV into cleaned parquet + metadata.",
    )
    parser.add_argument(
        "--raw_path",
        type=str,
        required=True,
        help="Path to raw Kaggle CSV (e.g., data/raw/online-payments-fraud-detection-dataset.csv).",
    )
    parser.add_argument(
        "--out_dir",
        type=str,
        default="data/processed",
        help="Output directory for processed artifacts.",
    )
    parser.add_argument(
        "--sample_rows",
        type=int,
        default=200_000,
        help="Number of rows to sample from the raw CSV (use -1 for full data).",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed used for sampling.",
    )
    parser.add_argument(
        "--sample_strategy",
        type=str,
        choices=["uniform", "head"],
        default="uniform",
        help=(
            "'uniform' samples randomly across the full time range (recommended); "
            "'head' keeps the legacy chunked behavior that favors early rows."
        ),
    )
    parser.add_argument(
        "--base_time",
        type=str,
        default="recent",
        help=(
            "Base timestamp for step 0. 'recent' anchors the simulation to end "
            "about now (recommended for online serving demos); otherwise pass "
            "an ISO-8601 timestamp such as 2017-01-01T00:00:00Z."
        ),
    )
    return parser.parse_args(args=args)


def main(cli_args: Optional[List[str]] = None) -> None:
    try:
        args = parse_args(cli_args)

        sample_rows: Optional[int]
        if args.sample_rows is not None and args.sample_rows < 0:
            sample_rows = None
        else:
            sample_rows = args.sample_rows

        run(
            raw_path=args.raw_path,
            out_dir=args.out_dir,
            sample_rows=sample_rows,
            seed=args.seed,
            sample_strategy=args.sample_strategy,
            base_time=args.base_time,
        )
    except Exception:
        logger.exception("data_ingest_failed")
        raise


if __name__ == "__main__":
    main()