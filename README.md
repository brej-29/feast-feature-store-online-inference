# Feast Fraud Feature Store Skeleton

Step 0 scaffold for a free-tier friendly, production-grade feature store stack:

- **Feast Feature Store** (to be wired in later steps)
- **Postgres** for online feature storage
- **Kafka/Redpanda** for streaming events
- **FastAPI** backend exposing prediction and health/metrics endpoints
- **Gradio** UI deployed on **Hugging Face Spaces**
- **Prometheus** metrics and **Nginx** reverse proxy inside the single app container

This repository is intentionally minimal but _runnable_ so that future steps (feature engineering, Feast integration, training, etc.) stay grounded and consistent.

---

## 1. What this repo provides in Step 0

- A **context system** under `./context/` that documents:
  - Project goal and success metrics
  - High-level architecture and request flow
  - Free-tier constraints for HF Spaces, Neon/Supabase, and CloudKarafka
  - Dataset plan for Kaggle "Online Payments Fraud Detection Dataset"
  - Metrics and evaluation plan
  - Task protocol for future Cosine AI tasks
  - Decisions and change log templates

- A **minimal FastAPI service** (`services/api/app/main.py`) exposing:
  - `GET /health` → `{"status": "ok"}`
  - `GET /metrics` → Prometheus metrics (via `prometheus_client`)
  - `POST /api/predict` → stubbed prediction, latency, and debug info

- A **Gradio app** (`app.py`) that:
  - Renders a simple fraud prediction form
  - Calls the local `/api/predict` endpoint
  - Handles errors gracefully and logs failures

- **Prometheus config** (`monitoring/prometheus.yml`) to scrape FastAPI `/metrics`.

- **Nginx reverse proxy** (`deploy/nginx/nginx.conf`) that routes:
  - `/` → Gradio UI
  - `/api/*` → FastAPI
  - `/prom/*` → Prometheus UI

- A **single launcher script** (`deploy/run.sh`) that starts:
  - FastAPI
  - Gradio
  - Prometheus
  - Nginx (as the foreground process)

- **Local dev tooling**:
  - `docker-compose.yml` (local only): Postgres + Redpanda + stack container
  - `Makefile`: common commands (`setup`, `lint`, `test`, `docker-up`, `docker-down`)
  - `requirements.txt` and `requirements-dev.txt`
  - `pyproject.toml` with basic formatter/linter configuration
  - `notebooks/00_eda_feature_store_story.ipynb` scaffold for EDA/storytelling

---

## 2. Local development

### 2.1. Python environment

```bash
python -m venv .venv
source .venv/bin/activate        # On Windows: .venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

Run the FastAPI backend:

```bash
uvicorn services.api.app.main:app --host 0.0.0.0 --port 8000 --reload
```

Run the Gradio frontend in another terminal:

```bash
python app.py
```

You should be able to hit:

- FastAPI health: http://127.0.0.1:8000/health
- FastAPI metrics: http://127.0.0.1:8000/metrics
- Gradio UI: http://127.0.0.1:7861/

### 2.2. Local Docker stack

For local experiments (not HF Spaces), use Docker Compose to run:

- Postgres (for future Feast online store)
- Redpanda (Kafka-compatible broker)
- Stack container (FastAPI + Gradio + Prometheus + Nginx)

```bash
docker compose up --build
```

The stack container exposes Nginx on port `7860` by default, routing:

- `http://localhost:7860/` → Gradio UI
- `http://localhost:7860/api/` → FastAPI
- `http://localhost:7860/prom/` → Prometheus UI

To tear down:

```bash
docker compose down -v
```

---

## 3. Hugging Face Spaces deployment (conceptual)

For HF Spaces (Docker):

- **Single container only**, no `docker-compose` inside the Space.
- The root `Dockerfile` builds an image that:
  - Installs Python dependencies, Nginx, and Prometheus
  - Copies the repo into `/app`
  - Uses `deploy/run.sh` as the container entrypoint
- HF Spaces provides a `$PORT` environment variable. Nginx listens on `$PORT` and proxies to:
  - Gradio on `7861`
  - FastAPI on `8000`
  - Prometheus on `9090`

When deployed on HF Spaces:

- The **user-facing endpoint** will be the Nginx port (`$PORT`), not the raw Gradio/FastAPI ports.
- Gradio should be accessed at `https://&lt;space-url&gt;/`
- API at `https://&lt;space-url&gt;/api/predict`
- Prometheus UI at `https://&lt;space-url&gt;/prom/`

---

## 4. Context grounding system

All substantial changes to this repository should be grounded in the `./context` directory.

Before implementing a new feature or refactor:

1. Read the relevant context documents:
   - `context/00_PROJECT_GOAL.md`
   - `context/01_ARCHITECTURE.md`
   - `context/02_FREE_TIER_CONSTRAINTS.md`
   - `context/03_COSINE_TASK_PROTOCOL.md`
   - Any other files related to the area you're touching

2. For Cosine AI assisted changes:
   - Follow the protocol in `context/03_COSINE_TASK_PROTOCOL.md`
   - Update:
     - `context/06_STEP_LOG.md` with the step description
     - `context/07_DECISIONS.md` with any architecture/product decisions
   - Quote which context files were read and how they influenced the changes

This ensures that the repo remains intelligible and evolvable across multiple tasks and agents.

---

## 5. Feature store & fraud detection roadmap (high level)

Later steps (not implemented in Step 0) will include:

- Initial **Feast feature repo** under `./feature_repo`:
  - Entity definitions (customers, counterparties, accounts, devices, geo cells)
  - Batch ingestion from the Kaggle fraud dataset
  - Streaming ingestion from Kafka/Redpanda

- Offline training pipeline:
  - EDA and leakage checks in `notebooks/00_eda_feature_store_story.ipynb`
  - Baseline models (e.g., tree-based) with metrics:
    - PR-AUC, ROC-AUC
    - Recall at fixed precision thresholds
    - Calibration and cost-based evaluation

- Online serving:
  - Latency-aware feature retrieval from Postgres
  - Request-time feature construction and aggregation
  - Real-time monitoring of latency and prediction quality

The Step 0 scaffold is purposefully narrow: make **`/health`**, **`/metrics`**, and a stub **`/api/predict`** work reliably, then iterate from there.

---

## 6. Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for:

- How to run tests and linting
- How to structure changes with Cosine AI tasks
- How to update the context and decision logs

This project is designed to remain free-tier compatible and reproducible on a small machine, while still pushing toward production-grade practices.