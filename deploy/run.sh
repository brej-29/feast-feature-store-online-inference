#!/usr/bin/env bash
set -eu

log() {
  echo "[$(date --iso-8601=seconds)] $*"
}

export PORT="${PORT:-7860}"
export API_BASE_URL="${API_BASE_URL:-http://127.0.0.1:8000}"
export FEAST_REPO_PATH="${FEAST_REPO_PATH:-feature_repo}"

log "Using PORT=${PORT}"
log "Using API_BASE_URL=${API_BASE_URL}"

# Resolve Postgres settings from POSTGRES_URL (Neon/managed) into the discrete
# POSTGRES_* vars the rest of the boot logic and feature_store.yaml expect.
eval "$(python -m pipelines.pg_config --export)"

# Apply Feast definitions and seed the online store on boot. A fresh container
# has no local registry (feature_repo/data/registry.db is not committed), so
# apply must run every start (idempotent). Skipped gracefully if no Postgres
# is configured (e.g. first boot before Neon is wired up) so the container
# still comes up in degraded serving mode.
#
# By default we seed only a bounded subset (scripts/seed_demo_online.py) rather
# than a full `feast materialize`: a full materialize writes millions of rows,
# overflowing Neon's free 0.5 GB and risking an OOM on a 512 MB Render box.
# Set MATERIALIZE_ON_BOOT=true to run the full materialize instead (needs a
# larger DB/instance).
if [ -n "${POSTGRES_HOST:-}" ]; then
  log "Postgres configured (host=${POSTGRES_HOST}); applying Feast definitions..."
  if bash /app/scripts/feast_apply.sh; then
    if [ "${MATERIALIZE_ON_BOOT:-false}" = "true" ]; then
      log "MATERIALIZE_ON_BOOT=true; running full materialize..."
      bash /app/scripts/feast_materialize.sh || log "WARNING: materialize failed; online store may be stale or empty."
    else
      log "Seeding bounded demo subset into online store (SEED_MAX_ENTITIES=${SEED_MAX_ENTITIES:-5000})..."
      python -m scripts.seed_demo_online || log "WARNING: online seed failed; profile features may fall back to defaults."
    fi
  else
    log "WARNING: feast apply failed; /api/predict will run in degraded mode."
  fi
else
  log "No Postgres configured; skipping Feast apply/seed (degraded serving mode)."
fi

# Prepare Nginx config (template uses $PORT)
if [ -f /app/deploy/nginx/nginx.conf ]; then
  log "Rendering Nginx configuration with PORT=${PORT}"
  envsubst '$PORT' < /app/deploy/nginx/nginx.conf > /etc/nginx/nginx.conf
else
  log "ERROR: /app/deploy/nginx/nginx.conf not found"
  exit 1
fi

# Start FastAPI (backend)
log "Starting FastAPI on 0.0.0.0:8000..."
uvicorn services.api.app.main:app --host 0.0.0.0 --port 8000 &
FASTAPI_PID=$!

# Start Prometheus (if available in PATH)
if command -v prometheus >/dev/null 2>&1; then
  log "Starting Prometheus on 0.0.0.0:9090..."
  prometheus \
    --config.file=/app/monitoring/prometheus.yml \
    --web.listen-address="0.0.0.0:9090" &
  PROMETHEUS_PID=$!
else
  log "Prometheus binary not found on PATH; skipping Prometheus server startup."
  PROMETHEUS_PID=
fi

# Ensure child processes are cleaned up on exit
terminate() {
  log "Received termination signal, stopping child processes..."
  if ps -p "${FASTAPI_PID}" >/dev/null 2>&1; then
    kill "${FASTAPI_PID}" || true
  fi
  if [ -n "${PROMETHEUS_PID}" ] && ps -p "${PROMETHEUS_PID}" >/dev/null 2>&1; then
    kill "${PROMETHEUS_PID}" || true
  fi
  if ps -p "${NGINX_PID:-0}" >/dev/null 2>&1; then
    kill "${NGINX_PID}" || true
  fi
  exit 0
}

trap terminate TERM INT

# Start Nginx in the foreground
log "Starting Nginx (listening on PORT=${PORT})..."
nginx -g "daemon off;" &
NGINX_PID=$!

# Wait for Nginx to exit (propagate exit code)
wait "${NGINX_PID}"