#!/usr/bin/env bash
# Run the Spark feature pipeline (or its parity test) in a container, so no
# local JDK/winutils setup is needed. Spark is offline-only tooling here; it
# is deliberately absent from the serving image.
#
#   bash scripts/spark_run.sh build          # build entity tables
#   bash scripts/spark_run.sh test           # run the pandas-parity test
#   bash scripts/spark_run.sh build --transactions_path data/processed/foo.parquet
set -euo pipefail

IMAGE="${SPARK_IMAGE:-apache/spark:3.5.3-scala2.12-java17-python3-ubuntu}"
CMD="${1:-build}"
shift || true

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Spark's image runs as a non-root user that cannot write pip's default target,
# so install into a user dir mounted from the repo (cached between runs).
PIP_TARGET="/app/.spark-deps"
# The image ships pyspark under $SPARK_HOME/python (plus the py4j zip) rather
# than site-packages, so an overridden PYTHONPATH must re-add it or
# `import pyspark` silently fails and the parity test skips instead of running.
SPARK_PY='${SPARK_HOME:-/opt/spark}/python:$(ls ${SPARK_HOME:-/opt/spark}/python/lib/py4j-*.zip | head -1)'

case "$CMD" in
  build)
    INNER="pip install --quiet --target=${PIP_TARGET} pandas pyarrow 2>/dev/null || true; \
           PYTHONPATH=/app:${PIP_TARGET}:${SPARK_PY} python3 -m pipelines.build_entity_tables_spark $*"
    ;;
  test)
    INNER="pip install --quiet --target=${PIP_TARGET} pandas pyarrow pytest 2>/dev/null || true; \
           PYTHONPATH=/app:${PIP_TARGET}:${SPARK_PY} ${PIP_TARGET}/bin/pytest tests/test_spark_parity.py -q -m spark -p no:cacheprovider $*"
    ;;
  *)
    echo "usage: $0 {build|test} [args...]" >&2; exit 2 ;;
esac

echo "==> Running '${CMD}' in ${IMAGE}"
# Git Bash on Windows rewrites container-side absolute paths (/app ->
# C:/Program Files/Git/app); MSYS_NO_PATHCONV keeps them intact. No-op elsewhere.
export MSYS_NO_PATHCONV=1
exec docker run --rm \
  -v "${REPO_ROOT}:/app" -w /app \
  -e HOME=/tmp \
  --user root \
  "${IMAGE}" \
  bash -lc "${INNER}"
