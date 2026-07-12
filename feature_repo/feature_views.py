from datetime import timedelta
from typing import List

from data_sources import (
    account_features_source,
    customer_features_source,
    device_features_source,
    geocell_features_source,
    merchant_features_source,
)
from entities import account, customer, device, geocell, merchant
from feast import FeatureView, Field, PushSource
from feast.types import Float32, Int64

# v2 feature views are point-in-time correct: each source row holds
# aggregates over that entity's STRICTLY PRIOR transactions, and fraud-label
# aggregates additionally respect a label maturation delay (see
# pipelines/build_entity_tables.py). v1 views were removed because they
# leaked the target (fraud_rate over the full dataset, including the row
# being scored).

# TTL must cover gaps between an entity's consecutive transactions across the
# ~31-day simulated window; entities inactive longer than this read as null
# (treated as "no known history") which is the safe default for fraud.
PROFILE_TTL = timedelta(days=90)


def _profile_schema() -> List[Field]:
    return [
        Field(name="txn_count_prior", dtype=Int64),
        Field(name="amount_sum_prior", dtype=Float32),
        Field(name="amount_mean_prior", dtype=Float32),
        Field(name="amount_max_prior", dtype=Float32),
        Field(name="unique_counterparty_count_prior", dtype=Int64),
        Field(name="flagged_rate_prior", dtype=Float32),
        Field(name="entity_age_hours", dtype=Float32),
        Field(name="matured_txn_count_prior", dtype=Int64),
        Field(name="fraud_txn_count_prior", dtype=Int64),
        Field(name="fraud_rate_prior", dtype=Float32),
    ]


customer_profile_v2 = FeatureView(
    name="customer_profile_v2",
    entities=[customer],
    ttl=PROFILE_TTL,
    schema=_profile_schema(),
    source=customer_features_source,
    online=True,
)

merchant_profile_v2 = FeatureView(
    name="merchant_profile_v2",
    entities=[merchant],
    ttl=PROFILE_TTL,
    schema=_profile_schema(),
    source=merchant_features_source,
    online=True,
)

device_profile_v2 = FeatureView(
    name="device_profile_v2",
    entities=[device],
    ttl=PROFILE_TTL,
    schema=_profile_schema(),
    source=device_features_source,
    online=True,
)

account_profile_v2 = FeatureView(
    name="account_profile_v2",
    entities=[account],
    ttl=PROFILE_TTL,
    schema=_profile_schema(),
    source=account_features_source,
    online=True,
)

geocell_profile_v2 = FeatureView(
    name="geocell_profile_v2",
    entities=[geocell],
    ttl=PROFILE_TTL,
    schema=_profile_schema(),
    source=geocell_features_source,
    online=True,
)

# Realtime last-transaction features. The batch source (customer feature
# table) provides the point-in-time historical values used at TRAINING time;
# the Kafka consumer pushes fresh values through this PushSource at SERVING
# time. Same feature names, same encoding (pipelines/encoders.py) -- that is
# the training/serving consistency contract.
customer_realtime_push = PushSource(
    name="customer_realtime_push",
    batch_source=customer_features_source,
)

customer_realtime_v1 = FeatureView(
    name="customer_realtime_v1",
    entities=[customer],
    ttl=timedelta(hours=24),
    schema=[
        Field(name="last_txn_amount", dtype=Float32),
        Field(name="last_txn_type_code", dtype=Int64),
        Field(name="last_txn_hour", dtype=Int64),
        Field(name="last_txn_is_flagged", dtype=Int64),
    ],
    source=customer_realtime_push,
    online=True,
)
