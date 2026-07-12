from feast import FileSource


# Point-in-time correct entity feature tables (see pipelines/build_entity_tables.py).
customer_features_source = FileSource(
    name="customer_features_source",
    # Feast resolves relative paths from the repo root (feature_repo/),
    # but our processed data lives at data/processed/ under the project root.
    path="../data/processed/customer_features.parquet",
    timestamp_field="event_timestamp",
)

merchant_features_source = FileSource(
    name="merchant_features_source",
    path="../data/processed/merchant_features.parquet",
    timestamp_field="event_timestamp",
)

device_features_source = FileSource(
    name="device_features_source",
    path="../data/processed/device_features.parquet",
    timestamp_field="event_timestamp",
)

account_features_source = FileSource(
    name="account_features_source",
    path="../data/processed/account_features.parquet",
    timestamp_field="event_timestamp",
)

geocell_features_source = FileSource(
    name="geocell_features_source",
    path="../data/processed/geocell_features.parquet",
    timestamp_field="event_timestamp",
)
