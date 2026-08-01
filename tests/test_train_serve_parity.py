"""Proves training and serving actually see the same feature values.

The project claims "one feature definition for training and serving, so
serving can't silently drift from training". That claim is normally just
*asserted* in READMEs. This test demonstrates it:

    offline  get_historical_features(entity, t)   ->  values used at TRAINING
    online   get_online_features(entity)          ->  values used at SERVING

Both go through the same `fraud_detection_v2` FeatureService, and after a
materialize covering `t` the two must agree field-for-field. If anyone edits a
feature view, changes a dtype, or breaks the materialize path so the online
store falls behind, this fails loudly instead of quietly degrading production
predictions.

Fully hermetic: builds a tiny transaction set, runs the real pandas feature
builder over it, applies the real v2 feature views against an ephemeral
Postgres, materializes, then compares. Marked `integration` (needs Docker).
"""

import importlib
import os
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

pytest.importorskip("testcontainers")
from testcontainers.postgres import PostgresContainer  # noqa: E402

pytestmark = pytest.mark.integration

# Anchor near "now" so the feature views' TTL doesn't expire the rows before
# the online read happens.
NOW = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
ENTITY_KEYS = ["customer_id", "merchant_id", "device_id", "account_id", "geo_cell_id"]


@pytest.fixture(scope="module")
def postgres_container():
    with PostgresContainer(
        "postgres:16-alpine",
        username="feature_user",
        password="feature_pass",
        dbname="feature_store",
    ) as pg:
        yield pg


def _transactions() -> pd.DataFrame:
    """A handful of transactions across two customers, with enough history
    that the 'prior' aggregates are non-trivial (all-zero features would make
    the comparison vacuous)."""
    # C1's newest transaction is deliberately only 2h old: customer_realtime_v1
    # carries a 24h TTL, and an online read is always "as of now". A stale
    # entity would make that view return nothing, which collapses the whole
    # multi-view join to zero rows -- exactly the failure this fixture must
    # avoid to test parity rather than TTL expiry.
    rows = [
        # (hours_ago, customer, merchant, amount, isFraud, isFlaggedFraud, type)
        (240, "C1", "M1", 100.0, 1, 0, "TRANSFER"),
        (200, "C1", "M2", 250.0, 0, 1, "PAYMENT"),
        (150, "C1", "M1", 900.0, 0, 0, "CASH_OUT"),
        (100, "C1", "M3", 75.0, 0, 0, "PAYMENT"),
        (2, "C1", "M2", 1200.0, 0, 0, "TRANSFER"),
        (220, "C2", "M1", 60.0, 0, 0, "CASH_IN"),
        (80, "C2", "M4", 340.0, 0, 0, "TRANSFER"),
    ]
    df = pd.DataFrame(
        {
            "event_timestamp": [NOW - timedelta(hours=r[0]) for r in rows],
            "customer_id": [r[1] for r in rows],
            "merchant_id": [r[2] for r in rows],
            "amount": [r[3] for r in rows],
            "isFraud": [r[4] for r in rows],
            "isFlaggedFraud": [r[5] for r in rows],
            "type": [r[6] for r in rows],
        }
    )
    # Mirror pipelines/data_ingest.py's derived entity keys.
    from pipelines.encoders import deterministic_hash

    df["account_id"] = df["customer_id"]
    df["geo_cell_id"] = df["merchant_id"].map(deterministic_hash)
    df["device_id"] = [
        deterministic_hash(f"{c}|{m}") for c, m in zip(df["customer_id"], df["merchant_id"])
    ]
    return df


def _build_store(postgres_container, tmp_path, feature_dir):
    """Apply the REAL v2 feature views/service against an ephemeral Postgres,
    with the file sources pointed at freshly built tiny tables."""
    os.environ["FEATURE_TABLE_DIR"] = str(feature_dir)

    # Import order matters and isort must not "tidy" it: importing the
    # feature_repo package is what puts its directory on sys.path, which is
    # what makes the bare `import data_sources` (etc.) below resolvable.
    import feature_repo  # noqa: F401,I001

    data_sources = importlib.import_module("data_sources")
    entities = importlib.import_module("entities")
    feature_views = importlib.import_module("feature_views")
    feature_services = importlib.import_module("feature_services")

    # data_sources reads FEATURE_TABLE_DIR at import time, so reload the chain
    # in case another test already imported it.
    for mod in (data_sources, feature_views, feature_services):
        importlib.reload(mod)

    from feast import FeatureStore
    from feast.repo_config import RepoConfig

    store = FeatureStore(
        config=RepoConfig(
            project="fraud_parity_test",
            registry=(tmp_path / "registry.db").as_uri(),
            provider="local",
            online_store={
                "type": "postgres",
                "host": postgres_container.get_container_host_ip(),
                "port": int(postgres_container.get_exposed_port(5432)),
                "database": "feature_store",
                "db_schema": "public",
                "user": "feature_user",
                "password": "feature_pass",
                "sslmode": "disable",
            },
            entity_key_serialization_version=3,
        )
    )
    store.apply(
        [
            entities.customer,
            entities.merchant,
            entities.device,
            entities.account,
            entities.geocell,
            feature_views.customer_profile_v2,
            feature_views.merchant_profile_v2,
            feature_views.device_profile_v2,
            feature_views.account_profile_v2,
            feature_views.geocell_profile_v2,
            feature_views.customer_realtime_v1,
            feature_services.fraud_detection_v2,
        ]
    )
    return store


def test_offline_and_online_features_agree(postgres_container, tmp_path, monkeypatch):
    """The core claim: what training saw == what serving sees."""
    from pipelines.build_entity_tables import run as build_tables

    txns = _transactions()
    txn_path = tmp_path / "transactions.parquet"
    txns.to_parquet(txn_path, index=False, coerce_timestamps="us", allow_truncated_timestamps=True)

    feature_dir = tmp_path / "features"
    feature_dir.mkdir()
    build_tables(transactions_path=str(txn_path), out_dir=str(feature_dir))

    monkeypatch.setenv("FEATURE_TABLE_DIR", str(feature_dir))
    store = _build_store(postgres_container, tmp_path, feature_dir)

    # Materialize everything up to now -> the online store should now hold the
    # latest feature row per entity, which is exactly what an offline lookup
    # "as of now" returns.
    store.materialize(start_date=NOW - timedelta(days=30), end_date=NOW + timedelta(minutes=1))

    service = store.get_feature_service("fraud_detection_v2")
    # C1's most recent transaction: has real history behind it and is inside
    # every view's TTL, so both paths return populated features.
    row = txns[txns["customer_id"] == "C1"].sort_values("event_timestamp").iloc[-1]
    entity_row = {k: row[k] for k in ENTITY_KEYS}

    online = store.get_online_features(
        features=service, entity_rows=[entity_row], full_feature_names=True
    ).to_dict()

    # Match the feature tables' timestamp resolution. Feast's file-based
    # point-in-time join silently returns ZERO rows on a ns-vs-us mismatch
    # rather than raising -- see the length guard in
    # pipelines/train_model.retrieve_training_frame, which turns that silent
    # failure into a loud one.
    # Ask offline for the same moment the online store's latest values
    # represent: this entity's most recent feature row.
    entity_df = pd.DataFrame([{**entity_row, "event_timestamp": row["event_timestamp"]}])
    entity_df["event_timestamp"] = entity_df["event_timestamp"].astype("datetime64[us, UTC]")
    offline = store.get_historical_features(
        entity_df=entity_df, features=service, full_feature_names=True
    ).to_df()

    compared = 0
    mismatches = []
    for name, values in online.items():
        if name in ENTITY_KEYS or name not in offline.columns:
            continue
        online_val, offline_val = values[0], offline[name].iloc[0]
        if pd.isna(offline_val) and online_val is None:
            continue
        compared += 1
        if online_val is None or pd.isna(offline_val):
            mismatches.append((name, online_val, offline_val))
        elif abs(float(online_val) - float(offline_val)) > 1e-4:
            mismatches.append((name, online_val, offline_val))

    assert not mismatches, (
        "Training/serving skew detected -- offline and online disagree on "
        f"{len(mismatches)} feature(s): {mismatches}"
    )
    # Guard against a vacuous pass if the service ever stops returning features.
    assert compared >= 10, f"expected to compare the full feature vector, only saw {compared}"


def test_features_are_not_all_defaults(postgres_container, tmp_path, monkeypatch):
    """Parity is meaningless if both sides return zeros -- prove the entity
    actually has real history behind it."""
    from pipelines.build_entity_tables import run as build_tables

    txns = _transactions()
    txn_path = tmp_path / "transactions.parquet"
    txns.to_parquet(txn_path, index=False, coerce_timestamps="us", allow_truncated_timestamps=True)
    feature_dir = tmp_path / "features2"
    feature_dir.mkdir()
    build_tables(transactions_path=str(txn_path), out_dir=str(feature_dir))

    monkeypatch.setenv("FEATURE_TABLE_DIR", str(feature_dir))
    store = _build_store(postgres_container, tmp_path, feature_dir)
    store.materialize(start_date=NOW - timedelta(days=30), end_date=NOW + timedelta(minutes=1))

    row = txns[txns["customer_id"] == "C1"].iloc[-1]
    online = store.get_online_features(
        features=["customer_profile_v2:txn_count_prior", "customer_profile_v2:amount_sum_prior"],
        entity_rows=[{"customer_id": row["customer_id"]}],
    ).to_dict()

    # C1's last transaction has four earlier ones behind it.
    assert online["txn_count_prior"][0] == 4
    assert online["amount_sum_prior"][0] > 0
