# Hugging Face Space – Deployment Notes

This file is intended to be shown in the Hugging Face Space UI (if supported),
summarizing how the Space is configured.

## What runs inside this Space?

The Docker image built from this repository runs:

- **FastAPI API + UI** (services/api/app/main.py, serving the bespoke frontend
  from `frontend/` via StaticFiles) on port `8000`
- **Prometheus** on port `9090`
- **Nginx** as a reverse proxy listening on `$PORT` (provided by HF)

Nginx routes:

- `/` → FastAPI (UI)
- `/api/` → FastAPI backend
- `/prom/` → Prometheus UI

## Key environment variables

Typical configuration for a Space:

- `PORT` – provided by HF, used by Nginx
- `API_BASE_URL` – base URL used by the frontend UI to call the API
  - On HF Spaces, this can often remain at its default
  - For local development you may set it to `http://127.0.0.1:8000`
- Optional Postgres configuration (if you connect to a managed DB):
  - `POSTGRES_HOST`
  - `POSTGRES_PORT`
  - `POSTGRES_DB`
  - `POSTGRES_USER`
  - `POSTGRES_PASSWORD`

## URLs (from the user's perspective)

- UI: `https://<space-host>/`
- Prediction API: `https://<space-host>/api/predict`
- Prometheus UI: `https://<space-host>/prom/`