"""Proves the Spark feature builder matches the pandas reference exactly.

The pandas implementation is the reference (it produces the committed demo
tables); the Spark one exists to run the same computation over the full
dataset. A rewrite is only worth anything if it is *provably* equivalent, so
this asserts the two agree row-for-row on a fixture crafted to hit the fiddly
cases: ties within a timestamp, repeat counterparties, the 72h label-maturation
boundary, and entities with no prior history.

Marked `spark` (and `integration`) -- needs a JVM, so it's excluded from the
default unit run. See scripts/spark_build_entity_tables.sh for a containerised
runner that needs no local JDK.
"""

from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

pytest.importorskip("pyspark")

from pipelines.build_entity_tables import build_point_in_time_features  # noqa: E402
from pipelines.build_entity_tables_spark import (  # noqa: E402
    build_point_in_time_features_spark,
)

pytestmark = [pytest.mark.integration, pytest.mark.spark]

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
DELAY_HOURS = 72


@pytest.fixture(scope="module")
def spark():
    from pyspark.sql import SparkSession

    session = (
        SparkSession.builder.appName("parity-test")
        .master("local[2]")
        .config("spark.sql.shuffle.partitions", "2")
        .config("spark.sql.session.timeZone", "UTC")
        .getOrCreate()
    )
    yield session
    session.stop()


def _fixture_frame() -> pd.DataFrame:
    # (hours_after_T0, customer, merchant, amount, isFraud, isFlaggedFraud, type)
    rows = [
        (0, "C1", "M1", 100.0, 1, 0, "TRANSFER"),   # fraud at t0; matures at t0+72h
        (0, "C1", "M2", 50.0, 0, 1, "PAYMENT"),     # same timestamp -> tie handling
        (1, "C1", "M1", 200.0, 0, 0, "CASH_OUT"),   # repeat counterparty
        (10, "C1", "M3", 400.0, 0, 0, "TRANSFER"),  # before fraud label matures
        (72, "C1", "M4", 25.0, 0, 0, "CASH_IN"),    # exactly on the maturation edge
        (100, "C1", "M5", 900.0, 0, 0, "TRANSFER"), # after maturation
        (5, "C2", "M1", 75.0, 0, 0, "PAYMENT"),     # separate entity, no history
        (6, "C2", "M1", 80.0, 0, 0, "DEBIT"),       # unknown-ish type code path
    ]
    return pd.DataFrame(
        {
            "event_timestamp": [T0 + timedelta(hours=r[0]) for r in rows],
            "customer_id": [r[1] for r in rows],
            "merchant_id": [r[2] for r in rows],
            "amount": [r[3] for r in rows],
            "isFraud": [r[4] for r in rows],
            "isFlaggedFraud": [r[5] for r in rows],
            "type": [r[6] for r in rows],
        }
    )


@pytest.mark.parametrize("include_last_txn", [False, True])
def test_spark_matches_pandas_reference(spark, include_last_txn):
    pdf = _fixture_frame()

    expected = build_point_in_time_features(
        pdf,
        entity_col="customer_id",
        counterpart_col="merchant_id",
        label_delay=pd.Timedelta(hours=DELAY_HOURS),
        include_last_txn=include_last_txn,
    )

    sdf = spark.createDataFrame(pdf)
    from pyspark.sql import functions as F

    sdf = sdf.withColumn("_row_id", F.monotonically_increasing_id())
    actual = build_point_in_time_features_spark(
        sdf,
        entity_col="customer_id",
        counterpart_col="merchant_id",
        label_delay_hours=DELAY_HOURS,
        include_last_txn=include_last_txn,
    ).toPandas()

    key = ["customer_id", "event_timestamp"]
    expected = expected.sort_values(key).reset_index(drop=True)
    actual = actual.sort_values(key).reset_index(drop=True)[expected.columns]

    # Normalise dtypes/timezones: the values are what's under test, not the
    # exact int width or tz representation Spark chose on the way back.
    for col in expected.columns:
        if col in key:
            continue
        expected[col] = expected[col].astype("float64")
        actual[col] = actual[col].astype("float64")
    expected["event_timestamp"] = pd.to_datetime(expected["event_timestamp"], utc=True)
    actual["event_timestamp"] = pd.to_datetime(actual["event_timestamp"], utc=True)

    pd.testing.assert_frame_equal(expected, actual, check_exact=False, rtol=1e-5)
