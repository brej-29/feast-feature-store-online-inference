#!/usr/bin/env bash
# Train against the FULL-dataset feature tables built by Spark, and log the
# result to MLflow next to the sample-based run.
#
# The variable under test is *feature richness*, not training-set size: the
# training row count is held equal to the sample run, but the entity profiles
# behind those rows are computed over all 6.3M transactions instead of a 300k
# subsample. Deeper histories should mean better features.
#
# Reversible: it re-points the Feast FileSources via FEATURE_TABLE_DIR, applies,
# trains, then re-applies the default paths so the demo/registry end up exactly
# as they started. --no_save keeps the served production artifact untouched.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"

SPARK_DIR="${SPARK_DIR:-data/processed/spark}"
FULL_TXNS="${FULL_TXNS:-data/processed/full/transactions_clean.parquet}"
MAX_ROWS="${MAX_ROWS:-300000}"   # match the sample run's training size

restore() {
  echo "==> Restoring default feature table paths"
  unset FEATURE_TABLE_DIR
  bash scripts/feast_apply.sh >/dev/null 2>&1 || true
}
trap restore EXIT

# Spark writes <name>.parquet.d/ (a directory of parts). Feast's FileSource
# wants the path it was given, so expose the directories under the names the
# definitions expect.
STAGE="$(mktemp -d)"
for f in "${SPARK_DIR}"/*.parquet.d; do
  [ -e "$f" ] || { echo "No Spark output in ${SPARK_DIR}; run scripts/spark_run.sh build first." >&2; exit 1; }
  base="$(basename "$f" .d)"
  ln -s "$(cd "$f" && pwd)" "${STAGE}/${base}" 2>/dev/null || cp -r "$f" "${STAGE}/${base}"
done
echo "==> Staged full-dataset tables at ${STAGE}"

export FEATURE_TABLE_DIR="${STAGE}"
echo "==> Applying Feast definitions against the full-dataset tables"
bash scripts/feast_apply.sh

echo "==> Training (rows=${MAX_ROWS}, features from the full 6.3M-row build)"
python -m pipelines.train_model \
  --transactions_path "${FULL_TXNS}" \
  --max_rows "${MAX_ROWS}" \
  --no_save

echo "==> Done. Compare runs with: python scripts/export_experiments.py"
