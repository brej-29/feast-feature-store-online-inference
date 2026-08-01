"""Build point-in-time correct entity feature tables from cleaned transactions.

Leakage-safety design
---------------------
The previous version of this pipeline aggregated over the FULL dataset
(including each row's own label) and emitted one row per entity. Serving a
`fraud_rate` computed that way leaks the target into the features.

This version emits one row per (entity, event_timestamp) where every feature
is computed from **strictly earlier** transactions only:

- Behavioral aggregates (counts, sums, means, maxima, counterparty
  cardinality) use all transactions with `event_timestamp < t`.
- Label-derived aggregates (`fraud_*`) additionally respect a **label delay**:
  fraud labels are only "known" `label_delay_hours` after the transaction
  happens (chargebacks/investigations are not instant). A feature row at time
  `t` therefore only counts fraud among transactions matured by `t -
  label_delay_hours`.

Feast's point-in-time join (`get_historical_features`) then picks, for each
training example at time `t`, the latest feature row with timestamp <= `t` --
which by construction contains no information from `t` or later.
"""

import argparse
import logging
import os
import time
from dataclasses import dataclass
from typing import List, Optional

import numpy as np
import pandas as pd

from pipelines.encoders import map_type_to_code

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("feast_fraud.pipelines.build_entity_tables")

DEFAULT_LABEL_DELAY_HOURS = 72


@dataclass(frozen=True)
class EntityJob:
    entity_col: str
    counterpart_col: str
    out_name: str
    include_last_txn: bool = False


ENTITY_JOBS: List[EntityJob] = [
    EntityJob("customer_id", "merchant_id", "customer_features.parquet", include_last_txn=True),
    EntityJob("merchant_id", "customer_id", "merchant_features.parquet"),
    EntityJob("device_id", "merchant_id", "device_features.parquet"),
    EntityJob("account_id", "merchant_id", "account_features.parquet"),
    EntityJob("geo_cell_id", "customer_id", "geocell_features.parquet"),
]


def _load_transactions(parquet_path: str) -> pd.DataFrame:
    if not os.path.exists(parquet_path):
        raise FileNotFoundError(
            f"Processed parquet not found at {parquet_path}. "
            "Run pipelines/data_ingest.py before build_entity_tables.py."
        )
    logger.info("Loading processed transactions", extra={"path": parquet_path})
    df = pd.read_parquet(parquet_path)
    required = {"event_timestamp", "amount", "isFraud", "isFlaggedFraud"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Processed data missing required columns: {sorted(missing)}")
    return df


def build_point_in_time_features(
    df: pd.DataFrame,
    entity_col: str,
    counterpart_col: str,
    label_delay: pd.Timedelta = pd.Timedelta(hours=DEFAULT_LABEL_DELAY_HOURS),
    include_last_txn: bool = False,
) -> pd.DataFrame:
    """Return one feature row per (entity, event_timestamp).

    Each row holds aggregates over the entity's transactions STRICTLY BEFORE
    that timestamp; fraud-label aggregates only count transactions that
    occurred at or before `t - label_delay`.
    """
    cols = [entity_col, counterpart_col, "event_timestamp", "amount", "isFraud", "isFlaggedFraud"]
    if include_last_txn:
        cols.append("type")
    work = df[cols].copy()
    work = work.sort_values("event_timestamp", kind="stable").reset_index(drop=True)

    # First occurrence (in time order) of each (entity, counterparty) pair,
    # so cumulative sums yield distinct-counterparty counts.
    work["_new_cp"] = (~work.duplicated([entity_col, counterpart_col])).astype("int64")

    g = (
        work.groupby([entity_col, "event_timestamp"], sort=False)
        .agg(
            txn_count=("amount", "size"),
            amount_sum=("amount", "sum"),
            amount_max=("amount", "max"),
            fraud_sum=("isFraud", "sum"),
            flagged_sum=("isFlaggedFraud", "sum"),
            new_cp=("_new_cp", "sum"),
        )
        .reset_index()
        .sort_values([entity_col, "event_timestamp"], kind="stable")
        .reset_index(drop=True)
    )

    eg = g.groupby(entity_col, sort=False)
    g["cum_txn"] = eg["txn_count"].cumsum()
    g["cum_amount"] = eg["amount_sum"].cumsum()
    g["cum_amount_max"] = eg["amount_max"].cummax()
    g["cum_fraud"] = eg["fraud_sum"].cumsum()
    g["cum_flagged"] = eg["flagged_sum"].cumsum()
    g["cum_cp"] = eg["new_cp"].cumsum()

    # Shift by one timestamp-group => strictly-prior aggregates.
    eg = g.groupby(entity_col, sort=False)
    prior_txn = eg["cum_txn"].shift(1)
    prior_amount = eg["cum_amount"].shift(1)
    prior_max = eg["cum_amount_max"].shift(1)
    prior_flagged = eg["cum_flagged"].shift(1)
    prior_cp = eg["cum_cp"].shift(1)
    first_seen = eg["event_timestamp"].transform("min")

    out = pd.DataFrame(
        {
            entity_col: g[entity_col],
            "event_timestamp": g["event_timestamp"],
        }
    )
    out["txn_count_prior"] = prior_txn.fillna(0).astype("int64")
    out["amount_sum_prior"] = prior_amount.fillna(0.0).astype("float32")
    out["amount_mean_prior"] = (
        (prior_amount / prior_txn).where(prior_txn > 0, 0.0).astype("float32")
    )
    out["amount_max_prior"] = prior_max.fillna(0.0).astype("float32")
    out["unique_counterparty_count_prior"] = prior_cp.fillna(0).astype("int64")
    out["flagged_rate_prior"] = (
        (prior_flagged / prior_txn).where(prior_txn > 0, 0.0).astype("float32")
    )
    out["entity_age_hours"] = (
        ((g["event_timestamp"] - first_seen).dt.total_seconds() / 3600.0).astype("float32")
    )

    # Label-delay-aware fraud aggregates: as of time t, only transactions at
    # or before (t - label_delay) have a known fraud label.
    right = g[[entity_col, "event_timestamp", "cum_txn", "cum_fraud"]].rename(
        columns={
            "event_timestamp": "_known_ts",
            "cum_txn": "_matured_txn",
            "cum_fraud": "_matured_fraud",
        }
    )
    left = g[[entity_col, "event_timestamp"]].copy()
    left["_asof_ts"] = left["event_timestamp"] - label_delay
    # merge_asof demands identical dtypes on the merge keys. Parquet
    # round-trips give microsecond-resolution timestamps (we coerce on write
    # for Spark compatibility) while Timedelta arithmetic promotes to
    # nanoseconds, so realign before merging.
    if right["_known_ts"].dtype != left["_asof_ts"].dtype:
        right["_known_ts"] = right["_known_ts"].astype(left["_asof_ts"].dtype)
    left["_row"] = np.arange(len(left))
    merged = pd.merge_asof(
        left.sort_values("_asof_ts", kind="stable"),
        right.sort_values("_known_ts", kind="stable"),
        left_on="_asof_ts",
        right_on="_known_ts",
        by=entity_col,
        direction="backward",
        allow_exact_matches=True,
    ).sort_values("_row")
    matured_txn = merged["_matured_txn"].fillna(0).to_numpy(dtype="float64")
    matured_fraud = merged["_matured_fraud"].fillna(0).to_numpy(dtype="float64")
    out["matured_txn_count_prior"] = matured_txn.astype("int64")
    out["fraud_txn_count_prior"] = matured_fraud.astype("int64")
    out["fraud_rate_prior"] = np.where(
        matured_txn > 0, matured_fraud / np.maximum(matured_txn, 1), 0.0
    ).astype("float32")

    if include_last_txn:
        # Previous-transaction features. These are the batch (historical)
        # counterpart of the realtime PushSource view: training reads them
        # point-in-time from this table, serving gets fresh values pushed
        # from the Kafka consumer.
        work["_type_code"] = work["type"].map(map_type_to_code).astype("int64")
        work["_txn_hour"] = work["event_timestamp"].dt.hour.astype("int64")
        last = (
            work.groupby([entity_col, "event_timestamp"], sort=False)
            .agg(
                _last_amount=("amount", "last"),
                _last_type_code=("_type_code", "last"),
                _last_hour=("_txn_hour", "last"),
                _last_flagged=("isFlaggedFraud", "last"),
            )
            .reset_index()
            .sort_values([entity_col, "event_timestamp"], kind="stable")
            .reset_index(drop=True)
        )
        lg = last.groupby(entity_col, sort=False)
        last_out = pd.DataFrame(
            {
                entity_col: last[entity_col],
                "event_timestamp": last["event_timestamp"],
                "last_txn_amount": lg["_last_amount"].shift(1).fillna(0.0).astype("float32"),
                "last_txn_type_code": lg["_last_type_code"].shift(1).fillna(0).astype("int64"),
                # -1 encodes "no prior transaction" (0 is a real hour).
                "last_txn_hour": lg["_last_hour"].shift(1).fillna(-1).astype("int64"),
                "last_txn_is_flagged": lg["_last_flagged"].shift(1).fillna(0).astype("int64"),
            }
        )
        out = out.merge(
            last_out, on=[entity_col, "event_timestamp"], how="left", validate="one_to_one"
        )

    return out.reset_index(drop=True)


def run(
    transactions_path: str,
    out_dir: str,
    label_delay_hours: int = DEFAULT_LABEL_DELAY_HOURS,
    jobs: Optional[List[EntityJob]] = None,
) -> None:
    df = _load_transactions(transactions_path)
    label_delay = pd.Timedelta(hours=label_delay_hours)
    os.makedirs(out_dir, exist_ok=True)

    for job in jobs or ENTITY_JOBS:
        start = time.perf_counter()
        features = build_point_in_time_features(
            df,
            entity_col=job.entity_col,
            counterpart_col=job.counterpart_col,
            label_delay=label_delay,
            include_last_txn=job.include_last_txn,
        )
        out_path = os.path.join(out_dir, job.out_name)
        # Microsecond timestamps keep these readable by Spark (see the same
        # note in pipelines/data_ingest.py).
        features.to_parquet(
            out_path, index=False, coerce_timestamps="us", allow_truncated_timestamps=True
        )
        logger.info(
            "Entity feature table written",
            extra={
                "entity_col": job.entity_col,
                "path": out_path,
                "rows": len(features),
                "elapsed_s": round(time.perf_counter() - start, 2),
            },
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build point-in-time correct entity feature tables (one row per "
            "entity per event timestamp, aggregates over strictly-prior "
            "transactions only)."
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
        help="Output directory for entity parquet tables.",
    )
    parser.add_argument(
        "--label_delay_hours",
        type=int,
        default=DEFAULT_LABEL_DELAY_HOURS,
        help=(
            "How long after a transaction its fraud label becomes known. "
            "Fraud-derived features only count transactions matured by t - delay."
        ),
    )
    return parser.parse_args()


def main() -> None:
    try:
        args = parse_args()
        run(
            transactions_path=args.transactions_path,
            out_dir=args.out_dir,
            label_delay_hours=args.label_delay_hours,
        )
    except Exception:
        logger.exception("build_entity_tables_failed")
        raise


if __name__ == "__main__":
    main()
