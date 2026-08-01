import os

from feast import FileSource

# Where the entity feature tables live, relative to the Feast repo dir.
# Overridable so the same definitions can be pointed at an alternative build
# (e.g. the full-dataset Spark output in data/processed/spark) without editing
# code. Default is the committed demo tables.
FEATURE_TABLE_DIR = os.getenv("FEATURE_TABLE_DIR", "../data/processed")

# Point-in-time correct entity feature tables (see pipelines/build_entity_tables.py).
customer_features_source = FileSource(
    name="customer_features_source",
    # Feast resolves relative paths from the repo root (feature_repo/),
    # but our processed data lives at data/processed/ under the project root.
    path=f"{FEATURE_TABLE_DIR}/customer_features.parquet",
    timestamp_field="event_timestamp",
)

merchant_features_source = FileSource(
    name="merchant_features_source",
    path=f"{FEATURE_TABLE_DIR}/merchant_features.parquet",
    timestamp_field="event_timestamp",
)

device_features_source = FileSource(
    name="device_features_source",
    path=f"{FEATURE_TABLE_DIR}/device_features.parquet",
    timestamp_field="event_timestamp",
)

account_features_source = FileSource(
    name="account_features_source",
    path=f"{FEATURE_TABLE_DIR}/account_features.parquet",
    timestamp_field="event_timestamp",
)

geocell_features_source = FileSource(
    name="geocell_features_source",
    path=f"{FEATURE_TABLE_DIR}/geocell_features.parquet",
    timestamp_field="event_timestamp",
)
