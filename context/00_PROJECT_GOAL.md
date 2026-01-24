# 00 — Project Goal

## 1. One-sentence summary

Build a **free-tier compatible, production-grade fraud feature store stack** for online payments, using **Feast + Postgres + Kafka**, served through a **FastAPI** backend and **Gradio** UI on **Hugging Face Spaces**, observability via **Prometheus**, and all orchestrated through a single Docker container for deployment.

---

## 2. Problem we are solving

Online payments fraud is:

- **Rare** (heavily imbalanced)
- **Evolving** (concept drift and adversaries)
- **Latency-sensitive** (sub-100ms budget for feature retrieval and scoring)

We want a system that:

1. **Separates modeling from data plumbing** using a feature store (Feast).
2. Supports both **offline experimentation** and **online serving** of features.
3. Can be run on **developer laptops** and **HF Spaces** using only free-tier services:
   - Postgres on **Neon** or **Supabase**
   - Kafka-compatible broker on **CloudKarafka** or self-hosted Redpanda
   - Hugging Face Spaces (Docker) with **no in-Space docker-compose**

---

## 3. Scope of Step 0

Step 0 intentionally focuses on:

- Repository structure and conventions
- Context documentation
- Minimal, but **runnable**, service skeletons

**What Step 0 MUST provide:**

- A FastAPI service with:
  - `GET /health`
  - `GET /metrics`
  - `GET /api/docs` &amp; `GET /api/redoc` for API introspection
  - `POST /api/predict` (stub)
- A Gradio app that calls `/api/predict`
- Nginx reverse proxy and Prometheus config
- A single `deploy/run.sh` that starts everything inside one container
- Local `docker-compose.yml` for:
  - Postgres
  - Kafka/Redpanda
  - The application stack container
- A context system (`./context`) that future tasks must read and honor

**What Step 0 explicitly does NOT include yet:**

- Real Feast feature repository initialization
- Production-ready models or training pipeline
- Real-time feature engineering and streaming ingestion
- CI/CD pipelines, secrets management, or full infra-as-code

These will be added in subsequent steps, referenced in `context/06_STEP_LOG.md`.

---

## 4. Non-goals and constraints

Non-goals for this phase:

- Maximizing raw performance or throughput
- Implementing every possible fraud modeling trick
- Building a multi-region, highly available cluster

Constraints:

- **Free-tier first**:
  - Hugging Face Spaces: limited RAM/CPU, potential sleep behavior
  - Neon/Supabase: storage and connection limits
  - CloudKarafka: limited partitions, throughput, and retention
- **Single Docker container** for HF Spaces:
  - No nested Docker or docker-compose
  - Nginx reverse proxy inside the container to fan-in FastAPI, Gradio, Prometheus
- **Simplicity over completeness**:
  - Favor explicit, small components that are easy to reason about
  - Defer heavy orchestration and automation to later steps

---

## 5. Success criteria (for the whole project, not just Step 0)

We will consider the project directionally successful when:

1. **ML / Data**:
   - We can train at least one baseline fraud model with:
     - PR-AUC significantly above a reasonable random baseline
     - Monitored recall@high-precision thresholds
   - Features are defined in Feast and reused consistently across training and serving.

2. **Serving**:
   - Online prediction endpoint (via FastAPI) can:
     - Retrieve features from Postgres online store
     - Score within a latency budget (e.g., p95 &lt; 150ms end-to-end) on HF Spaces.

3. **Streaming**:
   - Kafka ingestion path feeds events into the feature store (or staging tables) with:
     - Bounded lag on the order of seconds/minutes for free-tier resources.

4. **Observability and maintainability**:
   - Prometheus metrics are exposed and can be queried in the HF container.
   - Context docs remain up to date, with:
     - `context/06_STEP_LOG.md` tracking major steps
     - `context/07_DECISIONS.md` tracking key architectural decisions

Step 0 is “done” when the minimal skeleton runs locally and in a simple container, and the context documents give future agents a clear narrative and protocol to follow.