"""PySpark port of the point-in-time entity feature builder.

WHY THIS EXISTS
---------------
The pandas implementation (pipelines/build_entity_tables.py) is the reference
and is what the committed demo tables are built from. It samples the PaySim
dataset (default 300k rows) because a single machine's memory is the binding
constraint: point-in-time expansion emits one row per (entity, timestamp), so
the full 6.3M-row dataset produces multi-GB feature tables per entity.

This Spark version runs the identical computation over the *full* dataset.
It is verified equivalent to the pandas reference by tests/test_spark_parity.py.

OFFLINE ONLY -- never import this from the serving path. pyspark needs a JVM
and lives in requirements-spark.txt, deliberately outside the serving image
(the deployed container runs on a 512MB free-tier box; Spark would not fit and
has no business in a request path).

The Spark rewrite is also *clearer* than the pandas one: "aggregates over
strictly prior transactions" is a native window frame here
(ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) rather than a
cumsum-then-shift dance, and the 72h label-maturation delay is a RANGE frame
on the timestamp rather than a merge_asof.

Run (containerised, no local JDK needed):
    bash scripts/spark_run.sh build --transactions_path <parquet> --out_dir <dir>
    bash scripts/spark_run.sh test          # the pandas-parity check

Run (with a local JDK + `pip install -r requirements-spark.txt`):
    python -m pipelines.build_entity_tables_spark \\
        --transactions_path data/processed/transactions_clean.parquet \\
        --out_dir data/processed/spark
"""

import argparse
import logging
import os
import time
from typing import List, Optional

from pyspark.sql import DataFrame, SparkSession, Window, functions as F

from pipelines.build_entity_tables import (
    DEFAULT_LABEL_DELAY_HOURS,
    ENTITY_JOBS,
    EntityJob,
)
from pipelines.encoders import TYPE_CODE_MAPPING

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("feast_fraud.pipelines.build_entity_tables_spark")

# Column order mirrors the pandas reference so outputs diff cleanly.
PROFILE_COLUMNS = [
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
LAST_TXN_COLUMNS = [
    "last_txn_amount",
    "last_txn_type_code",
    "last_txn_hour",
    "last_txn_is_flagged",
]


def build_point_in_time_features_spark(
    df: DataFrame,
    entity_col: str,
    counterpart_col: str,
    label_delay_hours: int = DEFAULT_LABEL_DELAY_HOURS,
    include_last_txn: bool = False,
) -> DataFrame:
    """One feature row per (entity, event_timestamp), strictly-prior aggregates.

    Semantics are identical to
    pipelines.build_entity_tables.build_point_in_time_features -- see
    tests/test_spark_parity.py, which asserts the two agree row-for-row.

    `_row_id` reproduces the pandas reference's stable-sort tie-breaking:
    within one timestamp, original input order decides "first counterparty
    seen" and "last transaction".
    """
    cols = [entity_col, counterpart_col, "event_timestamp", "amount", "isFraud", "isFlaggedFraud"]
    if include_last_txn:
        cols.append("type")
    work = df.select(*cols, F.col("_row_id"))

    # First occurrence of each (entity, counterparty) pair in time order, so a
    # running sum yields the distinct-counterparty count.
    pair_w = Window.partitionBy(entity_col, counterpart_col).orderBy("event_timestamp", "_row_id")
    work = work.withColumn("_new_cp", (F.row_number().over(pair_w) == 1).cast("long"))

    if include_last_txn:
        type_map = F.create_map(*[x for kv in TYPE_CODE_MAPPING.items() for x in (F.lit(kv[0]), F.lit(kv[1]))])
        work = work.withColumn(
            "_type_code", F.coalesce(type_map[F.upper(F.trim(F.col("type")))], F.lit(0)).cast("long")
        ).withColumn("_txn_hour", F.hour("event_timestamp").cast("long"))

    # Collapse to one row per (entity, timestamp).
    aggs = [
        F.count(F.lit(1)).alias("txn_count"),
        F.sum("amount").alias("amount_sum"),
        F.max("amount").alias("amount_max"),
        F.sum("isFraud").alias("fraud_sum"),
        F.sum("isFlaggedFraud").alias("flagged_sum"),
        F.sum("_new_cp").alias("new_cp"),
    ]
    if include_last_txn:
        # "last within the timestamp group" = highest _row_id, matching the
        # pandas .agg(..., "last") on a stably time-sorted frame.
        last_of_group = F.max(F.struct("_row_id", "amount", "_type_code", "_txn_hour", "isFlaggedFraud"))
        aggs.append(last_of_group.alias("_last"))

    g = work.groupBy(entity_col, "event_timestamp").agg(*aggs)

    ts = F.col("event_timestamp").cast("long")  # epoch seconds, for RANGE frames
    entity_w = Window.partitionBy(entity_col).orderBy("event_timestamp")
    # "Strictly prior" is a native frame here -- no cumsum + shift needed.
    prior_w = entity_w.rowsBetween(Window.unboundedPreceding, -1)
    # As-of (t - label_delay): fraud labels are only known after maturation.
    matured_w = (
        Window.partitionBy(entity_col)
        .orderBy(ts)
        .rangeBetween(Window.unboundedPreceding, -label_delay_hours * 3600)
    )

    prior_txn = F.sum("txn_count").over(prior_w)
    prior_amount = F.sum("amount_sum").over(prior_w)
    prior_max = F.max("amount_max").over(prior_w)
    prior_flagged = F.sum("flagged_sum").over(prior_w)
    prior_cp = F.sum("new_cp").over(prior_w)
    matured_txn = F.coalesce(F.sum("txn_count").over(matured_w), F.lit(0))
    matured_fraud = F.coalesce(F.sum("fraud_sum").over(matured_w), F.lit(0))

    out = (
        g.withColumn("txn_count_prior", F.coalesce(prior_txn, F.lit(0)).cast("long"))
        .withColumn("_prior_txn", F.coalesce(prior_txn, F.lit(0)))
        .withColumn("amount_sum_prior", F.coalesce(prior_amount, F.lit(0.0)).cast("float"))
        .withColumn(
            "amount_mean_prior",
            F.when(F.col("_prior_txn") > 0, F.coalesce(prior_amount, F.lit(0.0)) / F.col("_prior_txn"))
            .otherwise(F.lit(0.0))
            .cast("float"),
        )
        .withColumn("amount_max_prior", F.coalesce(prior_max, F.lit(0.0)).cast("float"))
        .withColumn("unique_counterparty_count_prior", F.coalesce(prior_cp, F.lit(0)).cast("long"))
        .withColumn(
            "flagged_rate_prior",
            F.when(F.col("_prior_txn") > 0, F.coalesce(prior_flagged, F.lit(0.0)) / F.col("_prior_txn"))
            .otherwise(F.lit(0.0))
            .cast("float"),
        )
        .withColumn(
            "entity_age_hours",
            ((ts - F.min(ts).over(entity_w.rowsBetween(Window.unboundedPreceding, Window.unboundedFollowing)))
             / 3600.0).cast("float"),
        )
        .withColumn("matured_txn_count_prior", matured_txn.cast("long"))
        .withColumn("fraud_txn_count_prior", matured_fraud.cast("long"))
        .withColumn(
            "fraud_rate_prior",
            F.when(matured_txn > 0, matured_fraud / matured_txn).otherwise(F.lit(0.0)).cast("float"),
        )
    )

    if include_last_txn:
        # Previous timestamp-group's last transaction (-1 hour encodes "none",
        # since 0 is a real hour).
        prev = F.lag("_last").over(entity_w)
        out = (
            out.withColumn("_prev", prev)
            .withColumn("last_txn_amount", F.coalesce(F.col("_prev.amount"), F.lit(0.0)).cast("float"))
            .withColumn("last_txn_type_code", F.coalesce(F.col("_prev._type_code"), F.lit(0)).cast("long"))
            .withColumn("last_txn_hour", F.coalesce(F.col("_prev._txn_hour"), F.lit(-1)).cast("long"))
            .withColumn("last_txn_is_flagged", F.coalesce(F.col("_prev.isFlaggedFraud"), F.lit(0)).cast("long"))
        )

    select_cols = [entity_col, "event_timestamp"] + PROFILE_COLUMNS
    if include_last_txn:
        select_cols += LAST_TXN_COLUMNS
    return out.select(*select_cols)


def run(
    transactions_path: str,
    out_dir: str,
    label_delay_hours: int = DEFAULT_LABEL_DELAY_HOURS,
    jobs: Optional[List[EntityJob]] = None,
    shuffle_partitions: int = 64,
) -> None:
    spark = (
        SparkSession.builder.appName("feast-fraud-entity-tables")
        .config("spark.sql.shuffle.partitions", shuffle_partitions)
        .config("spark.sql.session.timeZone", "UTC")
        .getOrCreate()
    )
    try:
        df = spark.read.parquet(transactions_path).withColumn(
            "_row_id", F.monotonically_increasing_id()
        )
        df.cache()
        total = df.count()
        logger.info("Loaded transactions", extra={"path": transactions_path, "rows": total})
        os.makedirs(out_dir, exist_ok=True)

        for job in jobs or ENTITY_JOBS:
            start = time.perf_counter()
            features = build_point_in_time_features_spark(
                df,
                entity_col=job.entity_col,
                counterpart_col=job.counterpart_col,
                label_delay_hours=label_delay_hours,
                include_last_txn=job.include_last_txn,
            )
            # One file per table keeps the output drop-in compatible with the
            # pandas artifacts that Feast's FileSource reads.
            out_path = os.path.join(out_dir, job.out_name)
            features.coalesce(1).write.mode("overwrite").parquet(out_path + ".d")
            logger.info(
                "Entity feature table written",
                extra={
                    "entity_col": job.entity_col,
                    "path": out_path,
                    "elapsed_s": round(time.perf_counter() - start, 2),
                },
            )
    finally:
        spark.stop()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--transactions_path", default="data/processed/transactions_clean.parquet")
    parser.add_argument("--out_dir", default="data/processed/spark")
    parser.add_argument("--label_delay_hours", type=int, default=DEFAULT_LABEL_DELAY_HOURS)
    parser.add_argument("--shuffle_partitions", type=int, default=64)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run(
        transactions_path=args.transactions_path,
        out_dir=args.out_dir,
        label_delay_hours=args.label_delay_hours,
        shuffle_partitions=args.shuffle_partitions,
    )


if __name__ == "__main__":
    main()
