#!/usr/bin/env bash
# Backfill a window of feature values: recompute the offline tables, then push
# that window into the online store.
#
#   bash scripts/backfill.sh 2026-07-01 2026-07-08
#   bash scripts/backfill.sh 2026-07-01 2026-07-08 --skip-rebuild
#
# The materialize half is Feast's own `materialize START END` -- this wrapper
# exists for the operational sequence around it (recompute first, so the
# window you push reflects current pipeline logic rather than whatever the
# parquet happened to hold) and for the connection wiring.
#
# Note on point-in-time correctness: the rebuild always recomputes over the
# FULL transaction history, not just the window. Prior-aggregate features at
# time t depend on everything before t, so recomputing a window in isolation
# would silently produce wrong values.
set -euo pipefail

if [ $# -lt 2 ]; then
  echo "usage: $0 START END [--skip-rebuild]   (dates as YYYY-MM-DD or ISO-8601)" >&2
  exit 2
fi

START="$1"; END="$2"; shift 2
SKIP_REBUILD=false
[ "${1:-}" = "--skip-rebuild" ] && SKIP_REBUILD=true

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"

# Resolve POSTGRES_URL -> discrete vars (and load .env), as the other Feast
# entrypoints do.
eval "$(python -m pipelines.pg_config --export)"

if [ "${SKIP_REBUILD}" = false ]; then
  echo "==> Recomputing entity feature tables (full history, point-in-time correct)"
  python -m pipelines.build_entity_tables
else
  echo "==> Skipping rebuild; using existing feature tables"
fi

echo "==> Materializing ${START} -> ${END} into the online store"
feast -c feature_repo materialize "${START}" "${END}"

echo "==> Backfill complete"
