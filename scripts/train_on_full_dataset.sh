#!/usr/bin/env bash
# Train against the FULL-dataset feature tables built by Spark and log the
# result to MLflow beside the sample-based run.
#
# The variable under test is *feature richness*, not training-set size: the
# training row count is held equal to the sample run, but the entity profiles
# behind those rows are computed over all 6.3M transactions instead of a 300k
# subsample. Deeper histories should mean better features.
#
# Runs in a throwaway Feast repo (temp registry + sqlite online store) so it:
#   - never touches the live Neon online store or the committed registry,
#   - needs no database at all -- get_historical_features is purely offline.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"

SPARK_DIR="${SPARK_DIR:-data/processed/spark}"
FULL_TXNS="${FULL_TXNS:-data/processed/full/transactions_clean.parquet}"
MAX_ROWS="${MAX_ROWS:-300000}"   # match the sample run's training size

[ -d "${SPARK_DIR}" ] || { echo "No Spark output at ${SPARK_DIR}; run scripts/spark_run.sh build first." >&2; exit 1; }

TMP_REPO="$(mktemp -d)"
STAGE="$(mktemp -d)"
cleanup() { rm -rf "${TMP_REPO}" "${STAGE}"; }
trap cleanup EXIT

# Spark writes <name>.parquet.d/ (a directory of part files); expose those
# directories under the names the feature definitions expect. Feast reads a
# directory of parquet parts fine.
for f in "${SPARK_DIR}"/*.parquet.d; do
  cp -r "$f" "${STAGE}/$(basename "$f" .d)"
done

# Throwaway repo: same feature definitions, local-only stores.
cp feature_repo/*.py "${TMP_REPO}/"
cat > "${TMP_REPO}/feature_store.yaml" <<'YAML'
project: fraud_full_experiment
registry: registry.db
provider: local
online_store:
    type: sqlite
    path: online.db
entity_key_serialization_version: 3
YAML

export FEATURE_TABLE_DIR="${STAGE}"
echo "==> Applying feature definitions in throwaway repo (${TMP_REPO})"
feast -c "${TMP_REPO}" apply

echo "==> Training (rows=${MAX_ROWS}, features from the full 6.3M-row Spark build)"
python -m pipelines.train_model \
  --transactions_path "${FULL_TXNS}" \
  --repo_path "${TMP_REPO}" \
  --max_rows "${MAX_ROWS}" \
  --no_save

echo "==> Done. Compare runs with: python scripts/export_experiments.py"
