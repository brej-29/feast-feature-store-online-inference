"""End-to-end Feast integration test: apply -> push -> online read.

Runs against an ephemeral Postgres (Testcontainers) so it's hermetic and does
not depend on the local docker-compose stack, the Kaggle dataset, or the
developer's local feature_repo/data/registry.db. Uses a throwaway entity,
batch source, and feature view mirroring customer_realtime_v1's shape
(PushSource over a FileSource) rather than the production objects, so this
test needs no real data files -- only the realtime push/online-read path is
under test here. The batch/materialize path against real data is covered by
the leakage regression tests in test_point_in_time.py and by manual
verification (see context/06_STEP_LOG.md).

Marked `integration`; excluded from the default unit test run (see
pyproject.toml `-m "not integration"` in CI) because it requires Docker.
"""

from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

pytest.importorskip("testcontainers")
from testcontainers.postgres import PostgresContainer  # noqa: E402

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def postgres_container():
    with PostgresContainer(
        "postgres:16-alpine",
        username="feature_user",
        password="feature_pass",
        dbname="feature_store",
    ) as pg:
        yield pg


def _make_store(postgres_container, tmp_path):
    from feast import FeatureStore
    from feast.repo_config import RepoConfig

    # as_uri() gives a file:// scheme Feast's registry path parser can read
    # on Windows too (a bare "C:\..." path is misparsed as scheme "c").
    config = RepoConfig(
        project="fraud_feature_store_it",
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
    return FeatureStore(config=config)


def test_apply_push_and_online_read_round_trip(postgres_container, tmp_path):
    from feast import Entity, FeatureView, Field, FileSource, PushSource
    from feast.types import Float32, Int64

    # A throwaway batch source file satisfies apply()'s schema validation
    # without touching real production data. One dummy row (rather than an
    # empty frame) so pyarrow can concretely infer non-null column types.
    batch_path = tmp_path / "customer_realtime_batch.parquet"
    pd.DataFrame(
        {
            "customer_id": pd.Series(["_dummy"], dtype="str"),
            "event_timestamp": pd.Series(
                [datetime.now(timezone.utc)], dtype="datetime64[ns, UTC]"
            ),
            "last_txn_amount": pd.Series([0.0], dtype="float32"),
            "last_txn_type_code": pd.Series([0], dtype="int64"),
            "last_txn_hour": pd.Series([0], dtype="int64"),
            "last_txn_is_flagged": pd.Series([0], dtype="int64"),
        }
    ).to_parquet(batch_path, index=False)

    customer = Entity(name="customer", join_keys=["customer_id"])
    batch_source = FileSource(
        name="it_customer_realtime_batch",
        path=str(batch_path),
        timestamp_field="event_timestamp",
    )
    push_source = PushSource(name="it_customer_realtime_push", batch_source=batch_source)
    realtime_view = FeatureView(
        name="it_customer_realtime",
        entities=[customer],
        ttl=timedelta(hours=24),
        schema=[
            Field(name="last_txn_amount", dtype=Float32),
            Field(name="last_txn_type_code", dtype=Int64),
            Field(name="last_txn_hour", dtype=Int64),
            Field(name="last_txn_is_flagged", dtype=Int64),
        ],
        source=push_source,
        online=True,
    )

    store = _make_store(postgres_container, tmp_path)
    store.apply([customer, realtime_view])

    push_ts = datetime.now(timezone.utc)
    df = pd.DataFrame(
        [
            {
                "event_timestamp": push_ts,
                "customer_id": "IT_TEST_CUSTOMER",
                "last_txn_amount": 4242.0,
                "last_txn_type_code": 2,
                "last_txn_hour": push_ts.hour,
                "last_txn_is_flagged": 1,
            }
        ]
    )
    store.push("it_customer_realtime_push", df)

    result = store.get_online_features(
        features=[
            "it_customer_realtime:last_txn_amount",
            "it_customer_realtime:last_txn_type_code",
            "it_customer_realtime:last_txn_is_flagged",
        ],
        entity_rows=[{"customer_id": "IT_TEST_CUSTOMER"}],
    ).to_dict()

    assert result["last_txn_amount"] == [4242.0]
    assert result["last_txn_type_code"] == [2]
    assert result["last_txn_is_flagged"] == [1]

    # An entity that was never pushed must come back as null, not an error
    # and not a stale value from another entity.
    missing = store.get_online_features(
        features=["it_customer_realtime:last_txn_amount"],
        entity_rows=[{"customer_id": "NEVER_SEEN"}],
    ).to_dict()
    assert missing["last_txn_amount"] == [None]
