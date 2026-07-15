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

# Apply Feast definitions and materialize the online store on boot. A fresh
# container has no local registry (feature_repo/data/registry.db is not
# committed), so this must run every start; both are idempotent. Skipped
# gracefully if no Postgres is configured (e.g. first boot before Neon is
# wired up) so the container still comes up in degraded serving mode.
if [ -n "${POSTGRES_HOST:-}" ]; then
  log "POSTGRES_HOST set; applying Feast definitions..."
  if bash /app/scripts/feast_apply.sh; then
    log "Feast apply succeeded; materializing online store..."
    bash /app/scripts/feast_materialize.sh || log "WARNING: materialize failed; online store may be stale or empty."
  else
    log "WARNING: feast apply failed; /api/predict will run in degraded mode."
  fi
else
  log "POSTGRES_HOST not set; skipping Feast apply/materialize (degraded serving mode)."
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

# Start Gradio (frontend)
log "Starting Gradio on 0.0.0.0:7861..."
python app.py --port 7861 &
GRADIO_PID=$!

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
  if ps -p "${GRADIO_PID}" >/dev/null 2>&1; then
    kill "${GRADIO_PID}" || true
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