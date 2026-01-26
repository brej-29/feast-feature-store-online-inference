from typing import Dict

import numpy as np
import pandas as pd
from feast import OnDemandFeatureView, RequestSource, Field
from feast.types import Float32, Int64, String, UnixTimestamp

# Request-time source capturing raw transaction fields passed in at prediction
# / historical retrieval time. This is used by the OnDemandFeatureView below
# to derive deterministic, request-time features.
transaction_request = RequestSource(
    name="transaction_request",
    schema=[
        Field(name="amount", dtype=Float32),
        Field(name="type", dtype=String),
        Field(name="event_timestamp", dtype=UnixTimestamp),
        Field(name="isFlaggedFraud", dtype=Int64),
    ],
)


def _transaction_request_udf(input_df: pd.DataFrame) -> pd.DataFrame:
    """
    Request-time feature transformations for a single transaction.

    This function is used by the OnDemandFeatureView and is kept separate so
    that it can be unit-tested directly.
    """
    df = input_df.copy()
    out = pd.DataFrame(index=df.index)

    # Amount log transform
    amount = pd.to_numeric(df.get("amount", 0.0), errors="coerce").fillna(0.0)
    out["amount_log1p"] = np.log1p(amount.astype("float32"))

    # Event timestamp → hour-of-day, weekend/night flags
    ts = pd.to_datetime(df.get("event_timestamp"), utc=True, errors="coerce")
    ts = ts.fillna(pd.Timestamp("1970-01-01T00:00:00Z"))
    hours = ts.dt.hour.astype("int16")
    weekdays = ts.dt.weekday.astype("int16")  # Monday=0

    out["hour_sin"] = np.sin(2.0 * np.pi * hours / 24.0).astype("float32")
    out["hour_cos"] = np.cos(2.0 * np.pi * hours / 24.0).astype("float32")
    out["is_weekend"] = (weekdays.isin([5, 6])).astype("int64")
    out["is_night"] = ((hours < 6) | (hours >= 22)).astype("int64")

    # Transaction type code
    type_upper = df.get("type", "").astype(str).str.upper()
    type_mapping: Dict[str, int] = {
        "PAYMENT": 1,
        "TRANSFER": 2,
        "CASH_OUT": 3,
        "CASH_IN": 4,
        "DEBIT": 5,
    }
    out["type_code"] = type_upper.map(type_mapping).fillna(0).astype("int64")

    return out


transaction_request_features = OnDemandFeatureView(
    name="transaction_request_features",
    sources=[transaction_request],
    schema=[
        Field(name="amount_log1p", dtype=Float32),
        Field(name="hour_sin", dtype=Float32),
        Field(name="hour_cos", dtype=Float32),
        Field(name="is_weekend", dtype=Int64),
        Field(name="is_night", dtype=Int64),
        Field(name="type_code", dtype=Int64),
    ],
    udf=_transaction_request_udf,
)