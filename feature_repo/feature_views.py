from datetime import timedelta

from feast import FeatureView, Field, PushSource
from feast.types import Float32, Int64

from data_sources import (
    account_features_source,
    account_features_v1_source,
    customer_features_source,
    customer_features_v1_source,
    device_features_source,
    device_features_v1_source,
    geocell_features_source,
    geocell_features_v1_source,
    merchant_features_source,
    merchant_features_v1_source,
)
from entities import account, customer, device, geocell, merchant


# ---------------------------------------------------------------------------
# Step 1 snapshot FeatureViews (simple aggregates, kept for backwards
# compatibility and exploratory analysis).
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Real-time PushSource FeatureView for last-transaction features.
# ---------------------------------------------------------------------------

customer_realtime_push = PushSource(
    name="customer_realtime_push",
    batch_source=customer_features_source,
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


# ---------------------------------------------------------------------------
# Step 3: windowed, production-style FeatureViews backed by *_features_v1
# tables. These are the primary inputs to the risk_scoring FeatureServices.
# ---------------------------------------------------------------------------

customer_features_fv_v1 = FeatureView(
    name="customer_features_fv_v1",
    entities=[customer],
    ttl=timedelta(days=7),
    schema=[
        Field(name="cust_tx_count_1h", dtype=Float32),
        Field(name="cust_tx_count_6h", dtype=Float32),
        Field(name="cust_tx_count_24h", dtype=Float32),
        Field(name="cust_tx_count_7d", dtype=Float32),
        Field(name="cust_tx_amount_sum_1h", dtype=Float32),
        Field(name="cust_tx_amount_sum_6h", dtype=Float32),
        Field(name="cust_tx_amount_sum_24h", dtype=Float32),
        Field(name="cust_tx_amount_sum_7d", dtype=Float32),
        Field(name="cust_tx_amount_mean_24h", dtype=Float32),
        Field(name="cust_tx_amount_mean_7d", dtype=Float32),
        Field(name="cust_tx_amount_max_24h", dtype=Float32),
        Field(name="cust_tx_amount_max_7d", dtype=Float32),
        Field(name="cust_unique_merchants_24h", dtype=Float32),
        Field(name="cust_unique_merchants_7d", dtype=Float32),
        Field(name="cust_night_tx_ratio_7d", dtype=Float32),
        Field(name="cust_type_payment_ratio_7d", dtype=Float32),
        Field(name="cust_type_transfer_ratio_7d", dtype=Float32),
        Field(name="cust_type_cash_out_ratio_7d", dtype=Float32),
        Field(name="cust_type_cash_in_ratio_7d", dtype=Float32),
        Field(name="cust_type_debit_ratio_7d", dtype=Float32),
        Field(name="cust_to_merchant_repeat_ratio_7d", dtype=Float32),
        Field(name="cust_high_risk_type_ratio_7d", dtype=Float32),
    ],
    source=customer_features_v1_source,
    online=True,
)

merchant_features_fv_v1 = FeatureView(
    name="merchant_features_fv_v1",
    entities=[merchant],
    ttl=timedelta(days=7),
    schema=[
        Field(name="mch_tx_count_24h", dtype=Float32),
        Field(name="mch_tx_count_7d", dtype=Float32),
        Field(name="mch_amount_mean_7d", dtype=Float32),
        Field(name="mch_unique_customers_7d", dtype=Float32),
        Field(name="mch_fraud_rate_7d", dtype=Float32),
    ],
    source=merchant_features_v1_source,
    online=True,
)

device_features_fv_v1 = FeatureView(
    name="device_features_fv_v1",
    entities=[device],
    ttl=timedelta(days=7),
    schema=[
        Field(name="dev_tx_count_10m", dtype=Float32),
        Field(name="dev_tx_count_1h", dtype=Float32),
        Field(name="dev_tx_count_24h", dtype=Float32),
        Field(name="dev_unique_customers_24h", dtype=Float32),
        Field(name="dev_unique_customers_7d", dtype=Float32),
        Field(name="dev_amount_max_24h", dtype=Float32),
    ],
    source=device_features_v1_source,
    online=True,
)

account_features_fv_v1 = FeatureView(
    name="account_features_fv_v1",
    entities=[account],
    ttl=timedelta(days=7),
    schema=[
        Field(name="acct_org_balance_delta", dtype=Float32),
        Field(name="acct_dest_balance_delta", dtype=Float32),
        Field(name="acct_balance_delta_mean_24h", dtype=Float32),
        Field(name="acct_balance_delta_mean_7d", dtype=Float32),
        Field(name="acct_balance_delta_abs_mean_7d", dtype=Float32),
        Field(name="acct_insufficient_funds_rate_24h", dtype=Float32),
        Field(name="acct_insufficient_funds_rate_7d", dtype=Float32),
        Field(name="acct_tx_count_24h", dtype=Float32),
        Field(name="acct_tx_count_7d", dtype=Float32),
        Field(name="acct_tx_amount_sum_24h", dtype=Float32),
        Field(name="acct_tx_amount_sum_7d", dtype=Float32),
    ],
    source=account_features_v1_source,
    online=True,
)

geocell_features_fv_v1 = FeatureView(
    name="geocell_features_fv_v1",
    entities=[geocell],
    ttl=timedelta(days=7),
    schema=[
        Field(name="geo_tx_count_24h", dtype=Float32),
        Field(name="geo_tx_count_7d", dtype=Float32),
        Field(name="geo_unique_customers_7d", dtype=Float32),
        Field(name="geo_amount_mean_7d", dtype=Float32),
    ],
    source=geocell_features_v1_source,
    online=True,
)