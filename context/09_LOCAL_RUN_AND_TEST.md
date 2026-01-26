# 09 — Local Run &amp; Test Runbook (Windows-focused)

This file is a *recipes-only* runbook for running and testing the full fraud-detection feature store project **locally**.

It assumes that design rationale, architecture, and constraints are already covered in:

- `context/00_PROJECT_GOAL.md`
- `context/01_ARCHITECTURE.md`
- `context/02_FREE_TIER_CONSTRAINTS.md`
- `context/03_COSINE_TASK_PROTOCOL.md`
- `context/04_DATASET_PLAN.md`
- `context/05_METRICS_AND_EVAL.md`
- `context/06_STEP_LOG.md`
- `context/07_DECISIONS.md`

If you are new to the repo, skim **00–05** before following this runbook.

---

## 1. Prerequisites

Before running anything, ensure you have the following installed and working on your **Windows** machine.

### 1.1 Core tools

- **Git**
  - Download: https://git-scm.com/download/win
  - Verify:
    - **PowerShell / CMD / Git Bash**:
      ```bash
      git --version
      ```

- **Python 3.10+ (64-bit)**
  - Download: https://www.python.org/downloads/windows/
  - During install: **check** “Add Python to PATH”.
  - Verify:
    - **PowerShell / CMD / Git Bash**:
      ```bash
      python --version
      pip --version
      ```

- **Docker Desktop for Windows**
  - Download: https://www.docker.com/products/docker-desktop/
  - Enable:
    - WSL2 backend (recommended).
  - Verify:
    - **PowerShell / Git Bash**:
      ```bash
      docker version
      docker compose version
      ```

- **Make (optional)**
  - Some commands use `make` as a convenience.
  - If missing on Windows, you can either:
    - Install via **chocolatey**: `choco install make`, or
    - Use the explicit `python` / `docker compose` commands shown below (no `make` required).

### 1.2 Python dependencies

- Project uses **`pyproject.toml`** + **`requirements.txt`**.
- For local development, you can use a virtual environment.

**Recommended minimal setup:**

**PowerShell / Git Bash:**
```bash
python -m venv .venv
# PowerShell:
. .venv/Scripts/Activate.ps1
# Git Bash:
# source .venv/Scripts/activate
pip install --upgrade pip
pip install -r requirements.txt
```

**CMD:**
```cmd
python -m venv .venv
call .venv\Scripts\activate.bat
pip install --upgrade pip
pip install -r requirements.txt
```

### 1.3 Accounts / API keys (optional but recommended)

- **Kaggle account** for dataset download
  - Instructions: `scripts/kaggle_download.md`
  - You can also download the CSV manually from Kaggle and place it under:
    - `data/raw/online-payments-fraud-detection-dataset.csv`

- **(Optional) Managed Postgres (Neon/Supabase)** if you want to point Feast online store to a remote DB.
  - For local-only experimentation, the default **docker-compose Postgres** is enough.

---

## 2. What to read before running

At a minimum:

1. `README.md` — overview and high-level usage.
2. `context/00_PROJECT_GOAL.md` — what we are trying to achieve.
3. `context/01_ARCHITECTURE.md` — how the pieces fit together.
4. `docs/ops_materialization.md` — how materialization works.
5. `docs/HF_DEPLOYMENT.md` (optional) — if you care about HF Spaces.

Once you’ve skimmed those, you can follow the step-by-step commands below.

---

## 3. Environment setup (`.env` and folders)

### 3.1 Create data and models folders

**PowerShell / Git Bash:**
```bash
mkdir -p data/raw
mkdir -p data/processed
mkdir -p models
```

**CMD:**
```cmd
mkdir data
mkdir data\raw
mkdir data\processed
mkdir models
```

### 3.2 Create `.env` from example

**PowerShell / Git Bash:**
```bash
cp .env.example .env
```

**CMD:**
```cmd
copy .env.example .env
```

Then open `.env` in a text editor and adjust, at minimum:

- `POSTGRES_HOST=postgres` (for docker-compose Postgres)
- `POSTGRES_PORT=5432`
- `POSTGRES_DB=feast`
- `POSTGRES_USER=feast`
- `POSTGRES_PASSWORD=feast`
- `KAFKA_BROKERS=redpanda:29092` (for local Redpanda in docker-compose)
- Any HF-specific variables if you plan to deploy later (can be left as defaults for local).

---

## 4. Clone the repo (if not already)

**PowerShell / Git Bash / CMD:**
```bash
git clone &lt;YOUR_FORK_OR_REPO_URL&gt; fraud-feature-store
cd fraud-feature-store
```

Replace `&lt;YOUR_FORK_OR_REPO_URL&gt;` with your GitHub URL.

---

## 5. Offline pipeline: data → features → model

This section assumes you run commands from the repo root.

### 5.1 Download Kaggle dataset

**Option A – Use helper script (Git Bash / WSL recommended)**

Requires `kaggle` CLI configured.

**Git Bash / WSL:**
```bash
bash scripts/kaggle_download.sh
```

**PowerShell:**
```powershell
wsl bash scripts/kaggle_download.sh
```

**CMD:**
```cmd
wsl bash scripts/kaggle_download.sh
```

### 5.2 Or download manually

1. Go to Kaggle dataset page described in `scripts/kaggle_download.md`.
2. Download the CSV file.
3. Place it at:

   - `data/raw/online-payments-fraud-detection-dataset.csv`

### 5.3 Create virtual environment and install dependencies

See **Section 1.2**. Quick recap:

**PowerShell:**
```powershell
python -m venv .venv
. .venv/Scripts/Activate.ps1
pip install --upgrade pip
pip install -r requirements.txt
```

**CMD:**
```cmd
python -m venv .venv
call .venv\Scripts\activate.bat
pip install --upgrade pip
pip install -r requirements.txt
```

**Git Bash:**
```bash
python -m venv .venv
source .venv/Scripts/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### 5.4 Step 1 – Ingest raw CSV → cleaned parquet

**PowerShell / Git Bash / CMD** (with venv activated):

```bash
python pipelines/data_ingest.py ^
  --raw_path data/raw/online-payments-fraud-detection-dataset.csv ^
  --out_dir data/processed ^
  --sample_rows 200000 ^
  --seed 42
```

For **PowerShell** you can use backticks or a single line if preferred:

```powershell
python pipelines/data_ingest.py `
  --raw_path data/raw/online-payments-fraud-detection-dataset.csv `
  --out_dir data/processed `
  --sample_rows 200000 `
  --seed 42
```

**Resulting key files:**

- `data/processed/transactions_clean.parquet`
- `data/processed/transactions_full_schema.json`
- `data/processed/data_profile.json`

### 5.5 Step 3 – Windowed feature engineering

**PowerShell (preferred multi-line):**
```powershell
python pipelines/feature_engineering.py `
  --transactions_path data/processed/transactions_clean.parquet `
  --out_dir data/processed `
  --sample_rows 200000 `
  --max_entities 5000 `
  --skip_if_missing_input
```

**CMD (single line):**
```cmd
python pipelines\feature_engineering.py --transactions_path data/processed/transactions_clean.parquet --out_dir data/processed --sample_rows 200000 --max_entities 5000 --skip_if_missing_input
```

**Git Bash:**
```bash
python pipelines/feature_engineering.py \
  --transactions_path data/processed/transactions_clean.parquet \
  --out_dir data/processed \
  --sample_rows 200000 \
  --max_entities 5000 \
  --skip_if_missing_input
```

**Resulting key files (under `data/processed/feature_tables/`):**

- `customer_features_v1.parquet` (+ schema JSON)
- `merchant_features_v1.parquet`
- `device_features_v1.parquet`
- `account_features_v1.parquet`
- `geocell_features_v1.parquet`

### 5.6 Step 4 – Apply Feast definitions

Feast operates on the feature repo in `feature_repo/`.

**PowerShell / Git Bash / CMD:**
```bash
bash scripts/feast_apply.sh
```

On **Windows without Bash**, use WSL:

**PowerShell:**
```powershell
wsl bash scripts/feast_apply.sh
```

**CMD:**
```cmd
wsl bash scripts/feast_apply.sh
```

This runs `feast apply` with the configured `feature_store.yaml`.

### 5.7 Step 4 – Materialize features to online store

**PowerShell / Git Bash:**
```bash
bash scripts/feast_materialize_incremental.sh
```

**CMD (using WSL):**
```cmd
wsl bash scripts/feast_materialize_incremental.sh
```

This will:

- Materialize snapshot FeatureViews to the Postgres online store.
- Skip gracefully if feature tables are missing.

### 5.8 Step 5 – Train model with Feast features

**PowerShell:**
```powershell
python pipelines/train_model.py `
  --transactions_path data/processed/transactions_clean.parquet `
  --feature_service_name risk_scoring_v1 `
  --sample_rows 200000 `
  --out_dir models
```

**CMD:**
```cmd
python pipelines\train_model.py --transactions_path data/processed/transactions_clean.parquet --feature_service_name risk_scoring_v1 --sample_rows 200000 --out_dir models
```

**Git Bash:**
```bash
python pipelines/train_model.py \
  --transactions_path data/processed/transactions_clean.parquet \
  --feature_service_name risk_scoring_v1 \
  --sample_rows 200000 \
  --out_dir models
```

**Resulting key files:**

- `models/model.joblib`
- `models/model_metadata.json`
- `models/feature_importance.csv`
- `models/model_card.md` (or similar human-readable summary)

---

## 6. Online stack: Docker Compose + services

### 6.1 Start local stack (Postgres, Redpanda, API, Gradio, Prometheus, Nginx)

Ensure Docker Desktop is running.

**PowerShell / Git Bash / CMD:**
```bash
docker compose up --build
```

To run in the background:

```bash
docker compose up --build -d
```

This will start:

- **FastAPI** (under Nginx) exposed at `/api/*`
- **Gradio UI** at `/`
- **Prometheus** at `/prom/`
- **Postgres** and **Redpanda** as backing services

### 6.2 Verify health

Once `docker compose` is up:

**PowerShell / CMD / Git Bash:**
```bash
curl http://localhost:7860/health
curl http://localhost:7860/api/health
curl http://localhost:7860/api/feast/health
```

Or open in a browser:

- `http://localhost:7860`
- `http://localhost:7860/api/health`
- `http://localhost:7860/api/feast/health`

---

## 7. Streaming test: Kafka + Feast PushSource

### 7.1 Seed Kafka events

Requires local Redpanda from `docker compose`.

**PowerShell / Git Bash:**
```bash
python scripts/kafka_seed_events.py ^
  --brokers localhost:19092 ^
  --topic txn_events ^
  --count 100
```

(Use a single line in CMD, or adjust `^`/backticks as desired.)

**CMD:**
```cmd
python scripts\kafka_seed_events.py --brokers localhost:19092 --topic txn_events --count 100
```

The streaming service (`services/streaming/kafka_consumer.py`) should:

- Consume events from `txn_events`.
- Push features to Feast via the PushSource.
- Commit offsets only on successful push (with retries/backoff).

Check container logs:

**PowerShell / Git Bash / CMD:**
```bash
docker compose logs services_streaming -f
```

(Use the exact service name as defined in `docker-compose.yml` if different.)

---

## 8. UI and prediction tests

### 8.1 Gradio UI

With `docker compose` running, open in browser:

- `http://localhost:7860`

Interact with the Gradio UI:

1. Fill in transaction details.
2. Click predict.
3. Confirm that:
   - Response appears with **probability** and **prediction label**.
   - Latency breakdown and model info are displayed.

### 8.2 Direct API call to `/api/predict`

**PowerShell:**
```powershell
$body = @{
  amount = 100.0
  type = "TRANSFER"
  isFlaggedFraud = 0
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost:7860/api/predict" -Method POST -Body $body -ContentType "application/json"
```

**CMD (using curl from Git for Windows):**
```cmd
curl -X POST http://localhost:7860/api/predict ^
  -H "Content-Type: application/json" ^
  -d "{\"amount\": 100.0, \"type\": \"TRANSFER\", \"isFlaggedFraud\": 0}"
```

**Git Bash:**
```bash
curl -X POST http://localhost:7860/api/predict \
  -H "Content-Type: application/json" \
  -d '{"amount": 100.0, "type": "TRANSFER", "isFlaggedFraud": 0}'
```

You should receive a JSON response with:

- `prediction` (0/1)
- `probability`
- `model_version`
- `feature_service`
- `latency_ms` fields

---

## 9. Performance testing (Locust + benchmark script)

### 9.1 Benchmark script (sequential)

**PowerShell / Git Bash / CMD:**
```bash
python scripts/benchmark_predict.py --host http://localhost:7860 --n 100
```

Outputs:

- p50 / p95 latency
- Basic stats for `/api/predict`

### 9.2 Locust load test

Locust runs as a separate process targeting the app.

**PowerShell / Git Bash:**
```bash
setx TARGET_HOST "http://localhost:7860"
locust -f load_tests/locustfile.py
```

Or, for a single run without environment variable:

```bash
locust -f load_tests/locustfile.py --host http://localhost:7860
```

Then open:

- `http://localhost:8089` in your browser,
- Set number of users, spawn rate,
- Start the test.

---

## 10. Monitoring and drift detection

### 10.1 Prometheus metrics

With Docker stack running, metrics are exposed at:

- `http://localhost:7860/metrics` (FastAPI / Prometheus exporter)
- Nginx proxies may also expose `/prom/` if configured.

Check metrics:

**PowerShell / CMD / Git Bash:**
```bash
curl http://localhost:7860/metrics
```

Look for:

- Request counters
- Latency histograms (feature fetch, model inference, etc.)

### 10.2 Evidently drift report (offline)

Requires `data/processed/transactions_clean.parquet`.

**PowerShell / Git Bash / CMD:**
```bash
python monitoring/drift_report.py
```

Outputs:

- `docs/drift/drift_report.html`
- `docs/drift/drift_summary.json`

Note: `docs/drift/` is `.gitignore`’d by design.

---

## 11. Running the test suite locally

### 11.1 Unit / integration tests (pytest)

**PowerShell / Git Bash / CMD:**
```bash
pytest
```

This runs tests including:

- Feature engineering schema (`tests/test_feature_engineering_schema.py`)
- Feast repo imports (`tests/test_feature_repo_imports.py`)
- API Pydantic models and contracts (`tests/test_api_contracts.py`)
- Prediction route smoke tests (`tests/test_predict_route_smoke.py`)
- Training pipeline imports and artifact schema tests

You can also run specific tests:

```bash
pytest tests/test_api_contracts.py -q
pytest tests/test_feature_engineering_schema.py -q
```

### 11.2 Regenerating feature catalog

**PowerShell / Git Bash / CMD:**
```bash
python scripts/export_feature_catalog.py
```

Outputs:

- `docs/feature_catalog.md` (autogenerated)

---

## 12. Quick condensed command checklist (Windows)

From repo root, after cloning and setting up `.env`:

**Once per machine / project:**

```bash
python -m venv .venv
# Activate (PowerShell)
. .venv/Scripts/Activate.ps1
pip install --upgrade pip
pip install -r requirements.txt
```

**Offline pipeline:**

```bash
python pipelines/data_ingest.py --raw_path data/raw/online-payments-fraud-detection-dataset.csv --out_dir data/processed --sample_rows 200000 --seed 42
python pipelines/feature_engineering.py --transactions_path data/processed/transactions_clean.parquet --out_dir data/processed --sample_rows 200000 --max_entities 5000 --skip_if_missing_input
wsl bash scripts/feast_apply.sh
wsl bash scripts/feast_materialize_incremental.sh
python pipelines/train_model.py --transactions_path data/processed/transactions_clean.parquet --feature_service_name risk_scoring_v1 --sample_rows 200000 --out_dir models
```

**Online stack + streaming + tests:**

```bash
docker compose up --build
python scripts/kafka_seed_events.py --brokers localhost:19092 --topic txn_events --count 100
pytest
python scripts/benchmark_predict.py --host http://localhost:7860 --n 100
python monitoring/drift_report.py
```

Use the more detailed sections above for shell-specific syntax (CMD vs PowerShell vs Git Bash) when needed.