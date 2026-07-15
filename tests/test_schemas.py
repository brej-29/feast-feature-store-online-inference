"""Tests for the pandera schema gate on cleaned transactions."""

from datetime import datetime, timezone

import pandas as pd
import pytest
from pandera.errors import SchemaErrors

from pipelines.schemas import CleanedTransactionSchema


def _valid_row(**overrides) -> dict:
    row = {
        "step": 1,
        "type": "PAYMENT",
        "amount": 100.0,
        "nameOrig": "C1",
        "oldbalanceOrg": 500.0,
        "newbalanceOrig": 400.0,
        "nameDest": "M1",
        "oldbalanceDest": 0.0,
        "newbalanceDest": 100.0,
        "isFraud": 0,
        "isFlaggedFraud": 0,
        "event_timestamp": datetime(2026, 1, 1, tzinfo=timezone.utc),
        "customer_id": "C1",
        "merchant_id": "M1",
        "account_id": "C1",
        "geo_cell_id": "g1",
        "device_id": "d1",
    }
    row.update(overrides)
    return row


def _frame(*rows) -> pd.DataFrame:
    df = pd.DataFrame(list(rows))
    df["event_timestamp"] = pd.to_datetime(df["event_timestamp"], utc=True)
    return df


def test_valid_frame_passes():
    df = _frame(_valid_row(), _valid_row(nameOrig="C2"))
    CleanedTransactionSchema.validate(df, lazy=True)


def test_negative_amount_rejected():
    df = _frame(_valid_row(amount=-1.0))
    with pytest.raises(SchemaErrors):
        CleanedTransactionSchema.validate(df, lazy=True)


def test_unknown_transaction_type_rejected():
    df = _frame(_valid_row(type="WIRE"))
    with pytest.raises(SchemaErrors):
        CleanedTransactionSchema.validate(df, lazy=True)


def test_isfraud_out_of_range_rejected():
    df = _frame(_valid_row(isFraud=2))
    with pytest.raises(SchemaErrors):
        CleanedTransactionSchema.validate(df, lazy=True)


def test_tz_naive_timestamp_rejected():
    df = pd.DataFrame([_valid_row()])
    df["event_timestamp"] = pd.to_datetime(df["event_timestamp"]).dt.tz_localize(None)
    with pytest.raises(SchemaErrors):
        CleanedTransactionSchema.validate(df, lazy=True)
