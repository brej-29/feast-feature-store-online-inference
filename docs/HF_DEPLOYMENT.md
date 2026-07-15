# Hugging Face Spaces Deployment Guide

> **2026-07 update**: Hugging Face now requires a **PRO subscription
> ($9/month)** to run Docker or Gradio Spaces on free accounts -- only
> static Spaces are free. This guide is kept for anyone with (or planning
> to get) PRO. For a genuinely free deployment, see
> [`docs/RENDER_DEPLOYMENT.md`](RENDER_DEPLOYMENT.md) instead (see D011).

This repository is designed to run as a **single Docker container** on
Hugging Face Spaces, exposing:

- Bespoke static UI (served by FastAPI)
- FastAPI API
- Prometheus UI
- Nginx as the public entrypoint

## 1. Space type

Create a new Space:

- **Type**: Docker
- **Hardware**: free-tier CPU instance is sufficient for this project

## 2. Repository and Dockerfile

Point the Space at this GitHub repository. The root `Dockerfile`:

- Installs Python dependencies, Nginx, and Prometheus
- Copies the repo into `/app`
- Uses `deploy/run.sh` as the container entrypoint

You should not need to modify the Dockerfile for a basic deployment.

## 3. Environment variables

At minimum, configure:

- `PORT` – provided automatically by HF Spaces; Nginx listens on this port.
- `API_BASE_URL` – base URL used by the frontend UI to call the API:
  - For HF Spaces, the default (`http://127.0.0.1:8000`) works because the
    UI is served by the same FastAPI process inside the container.
  - For more explicit routing through Nginx you could set:
    - `API_BASE_URL=http://127.0.0.1:${PORT}`

Optional (for real Feast online store / Postgres connection):

- `POSTGRES_HOST`
- `POSTGRES_PORT`
- `POSTGRES_DB`
- `POSTGRES_USER`
- `POSTGRES_PASSWORD`

Optional Kafka / streaming configuration (local-only, not typically used in HF):

- `KAFKA_BROKERS`
- `KAFKA_TOPIC`
- `KAFKA_GROUP_ID`

## 4. URLs in the Space

Once the Space is running:

- UI: `https://<space-host>/`
- Prediction API: `https://<space-host>/api/predict`
- Feast health: `https://<space-host>/api/feast/health`
- Prometheus UI: `https://<space-host>/prom/`

## 5. Feast and model configuration

For full end-to-end behavior (beyond the stub model), you need:

1. A Postgres instance reachable from the Space, with credentials set as env vars.
2. A trained model and FeatureStore registry applied from a local or CI environment.

Typical workflow:

1. On a local machine or CI runner:
   - Run `pipelines/data_ingest.py` to produce `transactions_clean.parquet`.
   - Run `pipelines/build_entity_tables.py` to build the point-in-time correct
     entity feature tables.
   - Run `scripts/feast_apply.sh` to apply the Feast repo (pointed at your Postgres).
   - Run `scripts/feast_materialize.sh` to backfill the online store.
   - Run `pipelines/train_model.py` to produce `models/fraud_model_v2.joblib`.
2. Commit or upload `models/` artifacts (and optionally the registry) to a
   storage location accessible by the Space, or bake them into the image.

Out of the box, this repo focuses on:
- Wiring the container and Nginx correctly for HF Spaces.
- Providing a working frontend → FastAPI → Feast scaffold that can be extended
  as you add real data, models, and infrastructure.