#!/usr/bin/env bash
set -euo pipefail

# Materialize only snapshot FeatureViews backed by offline FileSources.
# Push-based realtime views (e.g., customer_realtime_v1) are *not* materialized
# from offline store, because their columns are populated via FeatureStore.push.
SNAPSHOT_VIEWS=(
  "device_profile_v1"
  "merchant_profile_v1"
  "customer_profile_v1"
  "account_profile_v1"
  "geocell_profile_v1"
  "customer_features_fv_v1"
  "merchant_features_fv_v1"
  "device_features_fv_v1"
  "account_features_fv_v1"
  "geocell_features_fv_v1"
)

FEATURE_TABLE_DIR="${FEATURE_TABLE_DIR:-data/processed/feature_tables}"

# If feature tables are missing (e.g., in CI or on a fresh checkout), skip
# materialization gracefully so automation can still succeed.
if [ ! -d "${FEATURE_TABLE_DIR}" ] || ! ls "${FEATURE_TABLE_DIR}"/*_features_v1.parquet >/dev/null 2>&1; then
  echo "Feature tables not found under '${FEATURE_TABLE_DIR}'."
  echo "Skipping 'feast materialize-incremental'."
  exit 0
fi

END_TS_UTC=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

echo "Running 'feast materialize-incremental' up to ${END_TS_UTC} for feature_repo/ ..."
echo "Materializing snapshot feature views: ${SNAPSHOT_VIEWS[*]}"

CMD=(feast -c feature_repo materialize-incremental)
for view in "${SNAPSHOT_VIEWS[@]}"; do
  CMD+=(-v "$view")
done
CMD+=("${END_TS_UTC}")

"${CMD[@]}"