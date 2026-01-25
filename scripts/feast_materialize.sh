#!/usr/bin/env bash
set -euo pipefail

END_TS_UTC=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

# Only materialize snapshot feature views from offline sources.
# customer_realtime_v1 is fed via Kafka → Feast PushSource and does not have
# offline columns last_txn_* in the parquet files, so attempting to
# backfill it from offline store causes KeyError.
SNAPSHOT_VIEWS="device_profile_v1,merchant_profile_v1,customer_profile_v1,account_profile_v1,geocell_profile_v1"

echo "Running 'feast materialize-incremental' up to ${END_TS_UTC} for feature_repo/ ..."
echo "Materializing snapshot feature views: ${SNAPSHOT_VIEWS}"
feast -c feature_repo materialize-incremental -v "${SNAPSHOT_VIEWS}" "${END_TS_UTC}"