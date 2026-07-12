#!/usr/bin/env bash
set -euo pipefail

END_TS_UTC=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

# Materialize all v2 views, including customer_realtime_v1: its batch source
# (customer_features.parquet) now carries point-in-time last_txn_* columns,
# so backfilling from the offline store is valid. Fresh values keep arriving
# through the Kafka -> PushSource path on top of the backfill.
VIEWS=(
  "device_profile_v2"
  "merchant_profile_v2"
  "customer_profile_v2"
  "account_profile_v2"
  "geocell_profile_v2"
  "customer_realtime_v1"
)

echo "Running 'feast materialize-incremental' up to ${END_TS_UTC} for feature_repo/ ..."
echo "Materializing feature views: ${VIEWS[*]}"

# Build Feast CLI command with one -v flag per feature view so that Feast
# treats them as separate views, not a single comma-joined name.
CMD=(feast -c feature_repo materialize-incremental)
for view in "${VIEWS[@]}"; do
  CMD+=(-v "$view")
done
CMD+=("${END_TS_UTC}")

"${CMD[@]}"
