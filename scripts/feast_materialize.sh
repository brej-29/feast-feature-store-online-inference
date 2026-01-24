#!/usr/bin/env bash
set -euo pipefail

END_TS_UTC=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

echo "Running 'feast materialize-incremental' up to ${END_TS_UTC} for feature_repo/ ..."
feast -c feature_repo materialize-incremental "${END_TS_UTC}"