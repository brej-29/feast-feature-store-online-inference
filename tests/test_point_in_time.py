"""Leakage regression tests for the point-in-time feature builder.

These tests encode the core correctness contract of the project: a feature
row at time t must contain no information from transactions at or after t,
and fraud-label-derived features must additionally ignore transactions whose
labels had not matured (label delay) by t.
"""

from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from pipelines.build_entity_tables import build_point_in_time_features

T0 = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)


def _txn_frame(rows):
    """rows: list of (hours_after_t0, customer, merchant, amount, is_fraud, is_flagged)."""
    return pd.DataFrame(
        {
            "event_timestamp": [T0 + timedelta(hours=h) for h, *_ in rows],
            "customer_id": [r[1] for r in rows],
            "merchant_id": [r[2] for r in rows],
            "amount": [float(r[3]) for r in rows],
            "isFraud": [int(r[4]) for r in rows],
            "isFlaggedFraud": [int(r[5]) for r in rows],
            "type": ["TRANSFER"] * len(rows),
        }
    )


def _row(features: pd.DataFrame, hours_after_t0: int) -> pd.Series:
    ts = T0 + timedelta(hours=hours_after_t0)
    match = features[features["event_timestamp"] == ts]
    assert len(match) == 1, f"expected exactly one feature row at t0+{hours_after_t0}h"
    return match.iloc[0]


class TestStrictlyPriorAggregates:
    def test_first_transaction_has_zero_history(self):
        df = _txn_frame([(0, "C1", "M1", 100, 0, 0)])
        out = build_point_in_time_features(df, "customer_id", "merchant_id")
        row = _row(out, 0)
        assert row["txn_count_prior"] == 0
        assert row["amount_sum_prior"] == 0.0
        assert row["amount_max_prior"] == 0.0
        assert row["unique_counterparty_count_prior"] == 0

    def test_feature_row_excludes_own_transaction(self):
        """The row at time t must NOT include the transaction(s) at t."""
        df = _txn_frame(
            [
                (0, "C1", "M1", 100, 0, 0),
                (1, "C1", "M2", 200, 0, 0),
                (2, "C1", "M3", 400, 0, 0),
            ]
        )
        out = build_point_in_time_features(df, "customer_id", "merchant_id")

        row_t1 = _row(out, 1)
        assert row_t1["txn_count_prior"] == 1
        assert row_t1["amount_sum_prior"] == pytest.approx(100.0)
        assert row_t1["amount_max_prior"] == pytest.approx(100.0)
        assert row_t1["unique_counterparty_count_prior"] == 1

        row_t2 = _row(out, 2)
        assert row_t2["txn_count_prior"] == 2
        assert row_t2["amount_sum_prior"] == pytest.approx(300.0)
        assert row_t2["amount_mean_prior"] == pytest.approx(150.0)
        assert row_t2["amount_max_prior"] == pytest.approx(200.0)
        assert row_t2["unique_counterparty_count_prior"] == 2

    def test_same_timestamp_transactions_share_one_prior_row(self):
        """Two txns in the same hour must both see only strictly-earlier data."""
        df = _txn_frame(
            [
                (0, "C1", "M1", 100, 0, 0),
                (1, "C1", "M2", 200, 0, 0),
                (1, "C1", "M3", 300, 0, 0),
            ]
        )
        out = build_point_in_time_features(df, "customer_id", "merchant_id")
        assert len(out) == 2  # one row per (entity, timestamp)
        row_t1 = _row(out, 1)
        # Neither of the two t1 transactions may leak into the t1 feature row.
        assert row_t1["txn_count_prior"] == 1
        assert row_t1["amount_sum_prior"] == pytest.approx(100.0)

    def test_repeat_counterparty_not_double_counted(self):
        df = _txn_frame(
            [
                (0, "C1", "M1", 100, 0, 0),
                (1, "C1", "M1", 200, 0, 0),
                (2, "C1", "M2", 300, 0, 0),
            ]
        )
        out = build_point_in_time_features(df, "customer_id", "merchant_id")
        assert _row(out, 2)["unique_counterparty_count_prior"] == 1


class TestLabelDelay:
    def test_fraud_label_not_known_before_maturation(self):
        """A fraud txn at t0 must not appear in fraud features until t0+delay."""
        delay = pd.Timedelta(hours=72)
        df = _txn_frame(
            [
                (0, "C1", "M1", 100, 1, 0),  # fraud, label matures at t0+72h
                (10, "C1", "M2", 200, 0, 0),  # before maturation
                (100, "C1", "M3", 400, 0, 0),  # after maturation
            ]
        )
        out = build_point_in_time_features(
            df, "customer_id", "merchant_id", label_delay=delay
        )

        row_t10 = _row(out, 10)
        assert row_t10["fraud_txn_count_prior"] == 0, "label leaked before maturation"
        assert row_t10["fraud_rate_prior"] == pytest.approx(0.0)
        assert row_t10["matured_txn_count_prior"] == 0
        # Non-label behavioral features still see the earlier txn immediately.
        assert row_t10["txn_count_prior"] == 1

        row_t100 = _row(out, 100)
        # By t0+100h, txns at t0 and t0+10h have matured (100-72=28 >= 10).
        assert row_t100["matured_txn_count_prior"] == 2
        assert row_t100["fraud_txn_count_prior"] == 1
        assert row_t100["fraud_rate_prior"] == pytest.approx(0.5)

    def test_flagged_rate_has_no_delay(self):
        """isFlaggedFraud is a system rule output, available immediately."""
        df = _txn_frame(
            [
                (0, "C1", "M1", 100, 0, 1),
                (1, "C1", "M2", 200, 0, 0),
            ]
        )
        out = build_point_in_time_features(df, "customer_id", "merchant_id")
        assert _row(out, 1)["flagged_rate_prior"] == pytest.approx(1.0)


class TestLastTxnFeatures:
    def test_last_txn_is_previous_not_current(self):
        df = _txn_frame(
            [
                (0, "C1", "M1", 100, 0, 1),
                (5, "C1", "M2", 200, 0, 0),
            ]
        )
        out = build_point_in_time_features(
            df, "customer_id", "merchant_id", include_last_txn=True
        )
        row_t0 = _row(out, 0)
        assert row_t0["last_txn_amount"] == pytest.approx(0.0)
        assert row_t0["last_txn_hour"] == -1  # no prior transaction

        row_t5 = _row(out, 5)
        assert row_t5["last_txn_amount"] == pytest.approx(100.0)
        assert row_t5["last_txn_hour"] == 0
        assert row_t5["last_txn_is_flagged"] == 1
        assert row_t5["last_txn_type_code"] == 2  # TRANSFER


class TestEntityIsolation:
    def test_entities_do_not_share_history(self):
        df = _txn_frame(
            [
                (0, "C1", "M1", 1000, 1, 0),
                (1, "C2", "M1", 50, 0, 0),
            ]
        )
        out = build_point_in_time_features(df, "customer_id", "merchant_id")
        row_c2 = out[out["customer_id"] == "C2"].iloc[0]
        assert row_c2["txn_count_prior"] == 0
        assert row_c2["amount_sum_prior"] == pytest.approx(0.0)
