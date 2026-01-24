# 02 — Free Tier Constraints

This project is designed to be **free-tier first**. All architecture and implementation decisions must be consistent with the limitations of:

- **Hugging Face Spaces (Docker)**
- **Neon/Supabase Postgres**
- **CloudKarafka (or similar free Kafka)**
- Typical developer laptops

---

## 1. Hugging Face Spaces (Docker)

Key constraints:

- **Single container**:
  - No `docker-compose` inside HF Spaces.
  - No nested Docker usage from within the container.
- **Ephemeral filesystem**:
  - Local writes might not persist between restarts (depending on HF config).
  - Long-lived state (feature store, models) should live in external services (Postgres, object storage).
- **Resource limits**:
  - Limited CPU/RAM; avoid heavy background jobs and excessive concurrency.
- **PORT environment variable**:
  - HF Spaces sets `$PORT` for incoming traffic.
  - Our Nginx must listen on `$PORT` (default to `7860` for local dev).

Implementation consequences:

- One **Dockerfile** at repo root.
- One **entrypoint script** (`deploy/run.sh`) that starts:
  - FastAPI
  - Gradio
  - Prometheus
  - Nginx (foreground)
- Nginx is the **only exposed listener**; it proxies to internal services.
- All services must be able to start quickly from a cold start.

---

## 2. Postgres (Neon / Supabase / local)

Constraints:

- **Connection limits**:
  - Free tiers often limit concurrent connections.
  - Use pooled connections where possible (later).
- **Storage and throughput**:
  - Feature tables must be compact and indexed carefully.
  - Prefer narrow tables, avoid unbounded growth.
- **Latency variability**:
  - Expect ~tens of milliseconds from HF Spaces to Neon/Supabase regions.

Implementation consequences:

- Use a **single logical online store** in Postgres for Feast.
- Keep schema lean and index only where needed.
- Avoid chatty transactional patterns from the API; prefer batched or cached feature retrievals where appropriate.

---

## 3. Kafka / CloudKarafka / Redpanda

Constraints:

- **Hosted Kafka (CloudKarafka)**:
  - Limited topics, partitions, and retention.
  - Limited throughput (messages per second).
- **Local Redpanda**:
  - Fine for local dev; not part of HF deployment.
  - Uses Docker in `docker-compose.yml`.

Implementation consequences:

- Use a **minimal topic set**:
  - Example:
    - `transactions`
    - `feature_updates`
  - Avoid per-user or per-tenant topics.
- Design for **small, efficient message payloads**.
- Keep consumer/producer logic simple and robust to reconnections.

---

## 4. No docker-compose in HF Spaces

This is a hard constraint:

- HF Spaces (Docker) runs **one container** built from the root `Dockerfile`.
- Therefore:
  - `docker-compose.yml` is **strictly for local development**.
  - All in-Space orchestration must be done via:
    - Shell scripts
    - Supervisor-like process handling
    - Nginx reverse proxy

Implementation consequences:

- `deploy/run.sh` is the canonical process launcher.
- `docker-compose.yml` should **never** be referenced in the HF deployment instructions.
- Code that depends on multiple containers must be guarded or used only in local/dev contexts.

---

## 5. Monitoring and metrics within constraints

- Prometheus server is run inside the same container.
- It should scrape only what is necessary:
  - FastAPI `/metrics` endpoint.
- Keep scrape intervals modest (e.g. 15s) to avoid unnecessary overhead.
- Do not assume an external long-term storage for Prometheus metrics; they may be ephemeral and only used for short-term debugging in Step 0.

---

## 6. Design rules derived from free-tier constraints

All future tasks should:

1. **Avoid heavy dependencies** that significantly increase image size or memory footprint.
2. **Prefer stateless services** with clear configuration via environment variables.
3. **Minimize resource usage** in background workers and scheduled jobs.
4. Ensure every new component:
   - Can run on a small machine (e.g., 2 vCPU / 4GB).
   - Respects the **single-container** HF deployment model.
   - Does not require paid features of Neon/Supabase/CloudKarafka.

When in doubt, choose the simpler approach and document the trade-offs in:

- `context/07_DECISIONS.md` (decision register)
- `context/06_STEP_LOG.md` (step log)