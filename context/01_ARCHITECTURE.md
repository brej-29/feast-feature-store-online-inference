# 01 — Architecture Overview

This document describes the target architecture for the **Feast Fraud Feature Store** stack, and what is implemented in **Step 0**.

---

## 1. Logical components

### 1.1. Core data & ML components

- **Feast Feature Store** (future steps)
  - Defines entities (customers, accounts, devices, geo cells).
  - Manages feature views and materialization.
  - Uses:
    - **Postgres** as online store
    - Object storage / offline store (TBD, e.g. local parquet or cloud storage).

- **Postgres (Online Store)**
  - Low-latency key-value style feature retrieval.
  - Hosted on:
    - Local Postgres via Docker for local dev.
    - Neon/Supabase for HF deployment.

- **Kafka / Redpanda (Event Stream)**
  - Ingests raw transaction events and feature update events.
  - Local: Redpanda via Docker.
  - Cloud: CloudKarafka free-tier for production-like experiments.

- **Model Training / EDA**
  - Implemented via notebooks under `./notebooks`.
  - Uses Kaggle **Online Payments Fraud Detection Dataset** as the primary source.

### 1.2. Serving & UI

- **FastAPI service**
  - Exposes:
    - `GET /health`
    - `GET /metrics`
    - `POST /api/predict`
  - Future:
    - Feature retrieval from Feast
    - Model inference
    - Request tracing and richer metrics.

- **Gradio UI (HF Spaces friendly)**
  - User-facing fraud prediction UI.
  - Communicates only via HTTP to the FastAPI backend.
  - Packaged in the same container as FastAPI for HF Spaces.

### 1.3. Observability and gateway

- **Prometheus**
  - Scrapes FastAPI metrics endpoint.
  - UI exposed under `/prom/` via Nginx.

- **Nginx reverse proxy**
  - Single ingress for the container.
  - Routes:
    - `/`      → Gradio (port 7861)
    - `/api/*` → FastAPI (port 8000)
    - `/prom/*` → Prometheus UI (port 9090)
  - Listens on `$PORT` (default 7860) so it is compatible with HF Spaces.

---

## 2. Step 0 implementation boundaries

In Step 0, only the following pieces are **actually implemented**:

- **FastAPI**:
  - Minimal app with `/health`, `/metrics`, `/api/predict` (stub).
  - Basic structured logging and exception handling.
  - Prometheus instrumentation via `prometheus_client`.

- **Gradio**:
  - Simple form with fields:
    - `amount`
    - `type`
    - `nameOrig`
    - `nameDest`
  - Calls the local FastAPI endpoint and displays the response or an error.

- **Prometheus**:
  - Configuration file (`monitoring/prometheus.yml`) scraping FastAPI at `http://127.0.0.1:8000/metrics`.
  - Prometheus server binary installed in the Docker image for experiments.

- **Nginx**:
  - Configured as a reverse proxy inside the same container.
  - Terminates HTTP on `$PORT` and fans out to internal services.

- **Local infrastructure**:
  - `docker-compose.yml` spins up:
    - Postgres
    - Redpanda (Kafka-compatible)
    - Stack container (FastAPI + Gradio + Prometheus + Nginx)
  - No direct Feast, Kafka, or Postgres integration is hardwired yet in Step 0.

---

## 3. Text-based architecture diagram

From the perspective of an external user, **HF Spaces** deployment:

```text
[User Browser]
     |
     v
[HF Space URL :$PORT]
     |
     v
+--------------------+
|   Nginx (reverse   |
|      proxy)        |
|   /         \      |
|  /api/*     \      |
| /            \     |
v               v    v
FastAPI       Gradio   Prometheus UI
:8000         :7861    :9090
```

Local and cloud data plane (later steps):

```text
[Kaggle Dataset] -----> [Offline Store / Files] ----+
                                                    |
                                                    v
                                             [Feast Feature Repo]
                                                    |
                                                    v
   +-------------------+      +-------------------------+
   | Postgres (online) |<-----| Materialization / Batch |
   +-------------------+      +-------------------------+
            ^
            |                               +-------------------+
            |       +--------------------+  | Model Serving     |
            |       | Kafka / Redpanda   |--| (FastAPI + Feast) |
[Events] --->------>| (CloudKarafka/local)|  +-------------------+
                    +--------------------+
```

---

## 4. Request flow (Step 0)

### 4.1. UI → API (prediction)

1. User visits the Gradio UI (via `/`).
2. User fills in:
   - Amount
   - Transaction type
   - Origin and destination account IDs
3. Gradio calls the FastAPI endpoint:
   - `POST /api/predict`
4. FastAPI:
   - Accepts the JSON payload
   - Computes a stub fraud probability
   - Logs structured information (amount, latency)
   - Returns probability + latency + model version
5. Gradio displays the result to the user.

### 4.2. Health and metrics

- Probes or humans call `GET /health`:
  - Returns `{"status": "ok"}` if application is responsive.
- Prometheus scrapes `GET /metrics` on the FastAPI service:
  - Exposed internally at `127.0.0.1:8000/metrics`
  - Routed externally via Nginx → Prometheus UI under `/prom/`.

---

## 5. Future evolution notes

Future steps should:

- Introduce Feast entities and feature views in `feature_repo/`.
- Introduce model training pipelines (e.g. via notebooks + Python modules).
- Wire FastAPI `/api/predict` to:
  - Retrieve features from Feast using entity IDs.
  - Apply a trained model artifact.
- Extend monitoring:
  - Request/feature retrieval latency histograms.
  - Model output distributions and drift monitoring.
- Respect all constraints in `context/02_FREE_TIER_CONSTRAINTS.md`.

Any architecture decision should be recorded in `context/07_DECISIONS.md` and referenced from `context/06_STEP_LOG.md` for the step where it was made.