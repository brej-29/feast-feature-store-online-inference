from feast import FileSource


# Snapshot entity feature tables from Step 1 (simple aggregates).
# These remain available for baseline FeatureViews and backwards compatibility.
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


# Windowed, production-style feature tables from Step 3.
# These live under data/processed/feature_tables/*_features_v1.parquet and
# include 50+ engineered features across entities.
customer_features_v1_source = FileSource(
    name="customer_features_v1_source",
    path="../data/processed/feature_tables/customer_features_v1.parquet",
    timestamp_field="event_timestamp",
    created_timestamp_column="created_timestamp",
)

merchant_features_v1_source = FileSource(
    name="merchant_features_v1_source",
    path="../data/processed/feature_tables/merchant_features_v1.parquet",
    timestamp_field="event_timestamp",
    created_timestamp_column="created_timestamp",
)

device_features_v1_source = FileSource(
    name="device_features_v1_source",
    path="../data/processed/feature_tables/device_features_v1.parquet",
    timestamp_field="event_timestamp",
    created_timestamp_column="created_timestamp",
)

account_features_v1_source = FileSource(
    name="account_features_v1_source",
    path="../data/processed/feature_tables/account_features_v1.parquet",
    timestamp_field="event_timestamp",
    created_timestamp_column="created_timestamp",
)

geocell_features_v1_source = FileSource(
    name="geocell_features_v1_source",
    path="../data/processed/feature_tables/geocell_features_v1.parquet",
    timestamp_field="event_timestamp",
    created_timestamp_column="created_timestamp",
)