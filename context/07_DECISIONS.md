# 07 — Decisions Register

This file records key architectural and product decisions in a lightweight ADR-style format.

Each decision should have:

- An ID (e.g., `D001`)
- Date
- Status (`proposed`, `accepted`, `deprecated`)
- Context / problem
- Options considered
- Chosen option
- Consequences and follow-ups

---

## Template

```markdown
## D0XX – &lt;short title&gt;
- **Date**: YYYY-MM-DD
- **Status**: proposed | accepted | deprecated
- **Context**:
  - &lt;problem / background&gt;
- **Options considered**:
  - Option A – &lt;description, pros/cons&gt;
  - Option B – &lt;description, pros/cons&gt;
- **Decision**:
  - &lt;chosen option and rationale&gt;
- **Consequences / Follow-ups**:
  - &lt;short bullet list&gt;
```

---

## D001 – Single-container HF deployment with internal Nginx and Prometheus

- **Date**: 2026-01-24
- **Status**: accepted
- **Context**:
  - Hugging Face Spaces (Docker) supports a single container and sets a single `$PORT`.
  - We need to serve:
    - Gradio UI
    - FastAPI API
    - Prometheus UI (optional but useful)
  - The system must remain free-tier friendly and simple to operate.
- **Options considered**:
  - **Option A** – Run a single Python process (e.g., FastAPI) and mount Gradio as a sub-app.
    - Pros:
      - Simpler process model (one server).
      - Fewer moving parts.
    - Cons:
      - Harder to integrate Prometheus UI.
      - Less separation of concerns between UI and API.
  - **Option B** – Use `docker-compose` in HF Spaces to run multiple containers (API, UI, Prometheus, Nginx).
    - Pros:
      - Clear separation between components.
    - Cons:
      - Not allowed on HF Spaces (no nested Docker/docker-compose).
  - **Option C** – Single container with multiple processes (FastAPI, Gradio, Prometheus) behind Nginx.
    - Pros:
      - Compatible with HF Spaces single-container model.
      - Clear routing:
        - `/` → Gradio
        - `/api/*` → FastAPI
        - `/prom/*` → Prometheus
      - Keeps internal ports stable.
    - Cons:
      - Slightly more complex startup/termination logic.
- **Decision**:
  - Adopt **Option C**: a single container that runs FastAPI, Gradio, and Prometheus, with Nginx as the reverse proxy listening on `$PORT`.
- **Consequences / Follow-ups**:
  - `deploy/run.sh` must act as the process supervisor for the container.
  - `deploy/nginx/nginx.conf` must remain compatible with HF `$PORT`.
  - Future changes to routing or monitoring must update both Nginx and Prometheus configs.

---

## D002 – Local-only docker-compose for Postgres + Redpanda + stack

- **Date**: 2026-01-24
- **Status**: accepted
- **Context**:
  - Developers need a convenient way to run:
    - Postgres
    - Kafka-compatible broker (Redpanda)
    - The application stack container
  - HF Spaces must not run docker-compose.
- **Options considered**:
  - **Option A** – Use docker-compose locally and in HF Spaces.
    - Cons:
      - Not compatible with HF Spaces constraints.
  - **Option B** – Avoid docker-compose completely.
    - Cons:
      - Local development becomes cumbersome (manual container orchestration).
  - **Option C** – Use docker-compose **only for local development**, and a single Dockerfile/entrypoint for HF Spaces.
    - Pros:
      - Maximizes local developer productivity.
      - Fully compatible with HF Spaces.
- **Decision**:
  - Adopt **Option C**: `docker-compose.yml` is **strictly for local dev**, while HF deployment uses only the root `Dockerfile` + `deploy/run.sh`.
- **Consequences / Follow-ups**:
  - Documentation must clearly separate local dev vs. HF deployment.
  - Any future service that needs to run in HF Spaces must be added to the single-container setup, not to a separate HF-only compose file.