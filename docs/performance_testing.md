# Performance and Load Testing

This document summarizes how to exercise the `/api/predict` endpoint under load
for basic latency and throughput checks.

## 1. Locust load tests

The repo includes a simple [Locust](https://locust.io/) load test under
`load_tests/locustfile.py`.

### 1.1. Installation

Locust is a development-only dependency. Install it with:

```bash
pip install locust
```

(or add it to your dev environment as needed).

### 1.2. Running Locust

1. Start the stack (FastAPI + Gradio + Nginx) locally, for example via Docker:

   ```bash
   docker compose up --build
   ```

   This exposes Nginx on `http://localhost:7860/`.

2. In another terminal, run Locust:

   ```bash
   TARGET_HOST=http://localhost:7860 locust -f load_tests/locustfile.py
   ```

3. Open the Locust web UI (by default at `http://localhost:8089/`) and start a
   test with a desired number of users and spawn rate.

The Locust user:

- Sends POST requests to `/api/predict`
- Generates synthetic entity IDs and request payloads consistent with the model
  and Feast feature definitions

You can use the metrics from Locust in combination with Prometheus `/metrics`
to reason about per-endpoint latencies.

## 2. Simple CLI benchmark

For quick, scriptable benchmarking, use `scripts/benchmark_predict.py`:

```bash
python scripts/benchmark_predict.py \
  --base-url http://localhost:7860 \
  --n 200
```

This script:

- Sends `n` requests to `/api/predict`
- Measures per-request latency
- Prints p50 and p95 latencies, along with basic success/error counts