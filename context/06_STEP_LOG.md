# 06 — Step Log

This file tracks major steps in the evolution of the project. Each entry should describe:

- What was done
- When it was done
- Who/what did it
- Which context files were used
- Any key decisions (with links to `context/07_DECISIONS.md`)

Use reverse chronological order (newest at the top).

---

## Template

```markdown
## Step X – <short title>
- **Date**: YYYY-MM-DD
- **Agent**: <human or Cosine AI identifier>
- **Context used**:
  - context/00_PROJECT_GOAL.md
  - context/01_ARCHITECTURE.md
  - context/02_FREE_TIER_CONSTRAINTS.md
  - context/03_COSINE_TASK_PROTOCOL.md
  - <any others>
- **Summary**:
  - <bullet list of key changes>
- **Files touched (high level)**:
  - <path 1>
  - <path 2>
- **Decisions referenced/added**:
  - D00X – <short description>
```

---

## Step 0 – Scaffold free-tier-first repo

- **Date**: 2026-01-24
- **Agent**: Cosine AI (Genie)
- **Context used**:
  - context/00_PROJECT_GOAL.md
  - context/01_ARCHITECTURE.md
  - context/02_FREE_TIER_CONSTRAINTS.md
  - context/03_COSINE_TASK_PROTOCOL.md
  - context/04_DATASET_PLAN.md
  - context/05_METRICS_AND_EVAL.md
- **Summary**:
  - Created initial repository structure and context documents.
  - Implemented minimal FastAPI service with `/health`, `/metrics`, and stub `/api/predict`.
  - Implemented Gradio UI calling the local `/api/predict` endpoint.
  - Added Prometheus configuration and Nginx reverse proxy config.
  - Added `deploy/run.sh` to start FastAPI, Gradio, Prometheus, and Nginx in a single container.
  - Added local `docker-compose.yml` for Postgres, Redpanda, and the stack container.
  - Added notebook scaffold for EDA and feature store story.
- **Files touched (high level)**:
  - `README.md`
  - `context/*.md`
  - `services/api/app/main.py`
  - `services/api/tests/test_health.py`
  - `app.py`
  - `Dockerfile`
  - `docker-compose.yml`
  - `deploy/run.sh`
  - `deploy/nginx/nginx.conf`
  - `monitoring/prometheus.yml`
  - `notebooks/00_eda_feature_store_story.ipynb`
- **Decisions referenced/added**:
  - D001 – Single-container HF deployment with Nginx + Prometheus inside.
  - D002 – Use local-only docker-compose for Postgres + Redpanda + stack.