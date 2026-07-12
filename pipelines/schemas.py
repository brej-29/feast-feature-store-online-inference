"""Pandera schemas that gate pipeline outputs.

Validated once, at the boundary where each pipeline stage writes its output,
so a schema violation fails loudly and immediately instead of silently
corrupting a downstream Feast apply/materialize or training run.
"""

from typing import Any

import pandas as pd
import pandera as pa
from pandera.typing import Series

TXN_TYPES = {"PAYMENT", "TRANSFER", "CASH_OUT", "CASH_IN", "DEBIT"}


class CleanedTransactionSchema(pa.DataFrameModel):
    """Schema for data/processed/transactions_clean.parquet."""

    step: Series[int] = pa.Field(ge=0)
    type: Series[str] = pa.Field(isin=TXN_TYPES)
    amount: Series[float] = pa.Field(ge=0)
    nameOrig: Series[str]
    oldbalanceOrg: Series[float] = pa.Field(ge=0)
    newbalanceOrig: Series[float] = pa.Field(ge=0)
    nameDest: Series[str]
    oldbalanceDest: Series[float] = pa.Field(ge=0)
    newbalanceDest: Series[float] = pa.Field(ge=0)
    isFraud: Series[int] = pa.Field(isin=[0, 1])
    isFlaggedFraud: Series[int] = pa.Field(isin=[0, 1])
    # Left untyped and checked below: pandera's Series[pa.DateTime] rejects
    # tz-aware datetime64 dtype, which event_timestamp always is (UTC).
    event_timestamp: Series[Any]
    customer_id: Series[str] = pa.Field(nullable=False)
    merchant_id: Series[str] = pa.Field(nullable=False)
    account_id: Series[str] = pa.Field(nullable=False)
    geo_cell_id: Series[str] = pa.Field(nullable=False)
    device_id: Series[str] = pa.Field(nullable=False)

    class Config:
        coerce = False
        strict = False  # allow extra columns (e.g. isFraud variants from raw CSV)

    @pa.check("event_timestamp")
    def event_timestamp_is_tz_aware(cls, series: pd.Series) -> bool:
        return pd.api.types.is_datetime64_any_dtype(series) and series.dt.tz is not None
