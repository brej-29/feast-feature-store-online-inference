# Render.com Deployment Guide

Genuinely free hosting for the single-container stack (Nginx + FastAPI
(serving the UI and API) + Prometheus, same image as `Dockerfile` describes) -- no credit
card required for Render's free web service plan. See D011 for why this
replaced the original Hugging Face Spaces plan.

## 1. One-time setup

1. Push this repository to GitHub (already done).
2. Go to <https://dashboard.render.com/blueprints> and sign in (GitHub OAuth
   is easiest -- this step has to happen in your browser).
3. Click **New Blueprint Instance**, connect this repo. Render reads
   `render.yaml` at the repo root and provisions a `web` service named
   `feast-fraud-detection` on the **free** plan automatically.
4. Render will prompt you to fill in the env vars marked `sync: false` in
   `render.yaml`:
   - `POSTGRES_HOST`, `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`
     -- from your Neon project's **Connect** page (`POSTGRES_PORT` defaults
     to `5432`, already filled in).
   - `API_KEY` -- optional; set any string to require `X-API-Key` on
     `/api/predict`, or leave blank to keep it open for a public demo.
   - You can leave the Postgres vars blank at first: the API degrades
     gracefully (predicts from request-time features only) rather than
     failing to boot. Fill them in later and Render will redeploy.
5. Click **Apply**. First build takes a few minutes (installs Prometheus,
   Python deps, builds the image).

## 2. Known trade-off: cold starts

Render's free plan spins the service down after ~15 minutes of no traffic.
The first request after that takes 30-60 seconds to wake it back up (worth
mentioning explicitly in the README/demo -- it's an honest, common
free-tier trade-off, not a bug).

## 3. URLs once deployed

Render gives you a URL like `https://feast-fraud-detection.onrender.com`:

- UI: `https://feast-fraud-detection.onrender.com/`
- Prediction API: `https://feast-fraud-detection.onrender.com/api/predict`
- Feast health: `https://feast-fraud-detection.onrender.com/api/feast/health`
- Prometheus UI: `https://feast-fraud-detection.onrender.com/prom/`

## 4. Feast registry and online store

The container runs `feast apply` and materializes the online store on every
boot (`deploy/run.sh`), reading the entity feature parquet files committed
under `data/processed/` and the trained model under `models/`. No separate
CI/materialize job is required for the demo to work -- redeploying (or a
cold-start wake-up) is enough to pick up new code, though the *feature
values* stay as of whenever those parquet files were last regenerated
locally (see `pipelines/build_entity_tables.py`).

## 5. Updating the deployment

Render auto-deploys on every push to the connected branch (default:
whichever branch you pointed the Blueprint at). To retrain and reship a
newer model, run `pipelines/train_model.py` locally, commit the updated
`models/` artifacts, and push.
