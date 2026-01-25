from datetime import timedelta

from feast import FeatureView, Field, PushSource
from feast.types import Float32, Int64

from data_sources import (
    account_features_source,
    customer_features_source,
    device_features_source,
    geocell_features_source,
    merchant_features_source,
)
from entities import account, customer, device, geocell, merchant


customer_profile_v1 = FeatureView(
    name="customer_profile_v1",
    entities=[customer],
    ttl=timedelta(days=7),
    schema=[
        Field(name="txn_count_total", dtype=Int64),
        Field(name="amount_sum_total", dtype=Float32),
        Field(name="amount_mean", dtype=Float32),
        Field(name="amount_max", dtype=Float32),
        Field(name="fraud_rate", dtype=Float32),
        Field(name="flagged_rate", dtype=Float32),
        Field(name="unique_counterparty_count", dtype=Int64),
    ],
    source=customer_features_source,
    online=True,
)

merchant_profile_v1 = FeatureView(
    name="merchant_profile_v1",
    entities=[merchant],
    ttl=timedelta(days=7),
    schema=[
        Field(name="txn_count_total", dtype=Int64),
        Field(name="amount_sum_total", dtype=Float32),
        Field(name="amount_mean", dtype=Float32),
        Field(name="amount_max", dtype=Float32),
        Field(name="fraud_rate", dtype=Float32),
        Field(name="flagged_rate", dtype=Float32),
        Field(name="unique_counterparty_count", dtype=Int64),
    ],
    source=merchant_features_source,
    online=True,
)

device_profile_v1 = FeatureView(
    name="device_profile_v1",
    entities=[device],
    ttl=timedelta(days=7),
    schema=[
        Field(name="txn_count_total", dtype=Int64),
        Field(name="amount_sum_total", dtype=Float32),
        Field(name="amount_mean", dtype=Float32),
        Field(name="amount_max", dtype=Float32),
        Field(name="fraud_rate", dtype=Float32),
        Field(name="flagged_rate", dtype=Float32),
        Field(name="unique_counterparty_count", dtype=Int64),
    ],
    source=device_features_source,
    online=True,
)

account_profile_v1 = FeatureView(
    name="account_profile_v1",
    entities=[account],
    ttl=timedelta(days=7),
    schema=[
        Field(name="txn_count_total", dtype=Int64),
        Field(name="amount_sum_total", dtype=Float32),
        Field(name="amount_mean", dtype=Float32),
        Field(name="amount_max", dtype=Float32),
        Field(name="fraud_rate", dtype=Float32),
        Field(name="flagged_rate", dtype=Float32),
        Field(name="unique_counterparty_count", dtype=Int64),
    ],
    source=account_features_source,
    online=True,
)

geocell_profile_v1 = FeatureView(
    name="geocell_profile_v1",
    entities=[geocell],
    ttl=timedelta(days=7),
    schema=[
        Field(name="txn_count_total", dtype=Int64),
        Field(name="amount_sum_total", dtype=Float32),
        Field(name="amount_mean", dtype=Float32),
        Field(name="amount_max", dtype=Float32),
        Field(name="fraud_rate", dtype=Float32),
        Field(name="flagged_rate", dtype=Float32),
        Field(name="unique_counterparty_count", dtype=Int64),
    ],
    source=geocell_features_source,
    online=True,
)

customer_realtime_push = PushSource(
    name="customer_realtime_push",
    batch_source=customer_features_source,
    stream_source=None,
)

customer_realtime_v1 = FeatureView(
    name="customer_realtime_v1",
    entities=[customer],
    ttl=timedelta(hours=1),
    schema=[
        Field(name="last_txn_amount", dtype=Float32),
        Field(name="last_txn_type_code", dtype=Int64),
        Field(name="last_txn_hour", dtype=Int64),
        Field(name="last_txn_is_flagged", dtype=Int64),
    ],
    source=customer_realtime_push,
    online=True,
)