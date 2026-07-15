#!/usr/bin/env bash
set -euo pipefail

# Resolve Postgres settings (parses POSTGRES_URL when set; ensures
# POSTGRES_SSLMODE is populated for feature_store.yaml) so the Feast CLI,
# which reads the YAML directly, sees the same connection as the app.
eval "$(python -m pipelines.pg_config --export)"

echo "Running 'feast apply' for feature_repo/ ..."
feast -c feature_repo apply
