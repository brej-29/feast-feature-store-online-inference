# 05 — Metrics and Evaluation

This document outlines the metrics and evaluation strategy for the fraud detection system.

The focus is on:

- Handling **class imbalance** appropriately.
- Tracking **online performance** (latency and reliability).
- Providing a clear link between offline metrics and online behavior.

---

## 1. Classification metrics for fraud detection

Fraud detection is a **highly imbalanced** binary classification problem:

- Positive class: `isFraud = 1`
- Negative class: `isFraud = 0`

We care more about **catching fraud** than about perfectly minimizing false positives, but false positives still have user and business costs.

### 1.1. Core metrics

1. **PR-AUC (Precision-Recall Area Under Curve)** — primary metric
   - More informative than ROC-AUC under strong class imbalance.
   - Tells us how well we can trade off precision and recall across thresholds.

2. **ROC-AUC (Receiver Operating Characteristic AUC)** — secondary metric
   - Useful as a familiar benchmark.
   - Should not be used alone to make deployment decisions.

3. **Recall@Precision threshold**
   - E.g., recall at 95% precision.
   - Interpretation: “If we want at most 5% of flagged transactions to be false positives, what fraction of actual fraud can we catch?”

4. **Precision@Recall threshold**
   - E.g., precision at 80% recall.
   - Interpretation: “If we want to catch 80% of fraud, what is the fraction of our flags that are actually fraud?”

5. **Calibration metrics (later)**
   - Brier score, reliability diagrams, or calibration curves.
   - Important if scores are used in downstream decision rules (e.g., risk-based pricing, manual review).

### 1.2. Operating point selection

We will select one or more **operating thresholds** on model scores using:

- Validation or out-of-time test sets (respecting `step` ordering).
- Optimizing for:
  - Business-weighted cost function (later), or
  - Target precision/recall constraints (initially).

These thresholds must be recorded in this document and/or configuration files when finalized.

---

## 2. Offline evaluation protocol

1. **Dataset splits**:
   - Use time-aware splits based on `step` to avoid leakage:
     - Train: early steps
     - Validation: middle steps
     - Test: later steps
   - Exact boundaries to be determined in the EDA notebook.

2. **Cross-validation** (optional in later steps):
   - Time-series or rolling window CV for more robust estimates.

3. **Reporting**:
   - For each model version, record:
     - PR-AUC
     - ROC-AUC
     - Recall@precision thresholds
     - Precision@recall thresholds
   - Keep a simple model registry (even if it is just a Markdown table) with:
     - Model version ID
     - Features used
     - Training dataset version
     - Offline metrics

4. **Reproducibility**:
   - Fix random seeds where feasible.
   - Log data snapshot IDs or hashes if using external storage.

---

## 3. Online serving metrics

### 3.1. Latency metrics

For online serving, latency is critical. We will track at least:

- **Request latency** (FastAPI):
  - Histogram/summary of end-to-end request times.
  - Percentiles: **p50**, **p90**, **p95**, **p99**.
- **Feature retrieval latency** (later, with Feast):
  - Time spent fetching features from Postgres / online store.
  - Time spent in any streaming lookups or aggregations (if applicable).

Target SLOs (initial aspirational values):

- **p95 prediction latency ≤ 150 ms** on HF Spaces (end-to-end, including feature retrieval).
- **p99 prediction latency ≤ 300 ms**.

These are stretch goals; actual numbers must be measured and recorded as we iterate.

### 3.2. Availability and error metrics

- **HTTP error rates**:
  - Rate of 5xx responses for `/api/predict`.
  - Rate of timeouts or client errors.
- **Health checks**:
  - `/health` success rates.

Implementation details (Step 0):

- `prometheus_client` provides:
  - Counters for request counts.
  - Histograms for request latency.
- FastAPI middleware in `services/api/app/main.py`:
  - Logs each request with path, method, status, and latency.

As the system evolves, we can introduce:

- Per-endpoint metrics.
- Model version labels on metrics.
- Feature retrieval latency metrics.

---

## 4. Monitoring dashboards (future)

In later steps, we can deploy or configure dashboards on top of Prometheus data, e.g.:

- Grafana running locally or in another environment.
- Simplified HTML dashboards, if we choose to embed them.

Key views:

1. **Latency dashboard**:
   - Histograms and percentile plots for `/api/predict`.
2. **Error dashboard**:
   - Error rates over time.
3. **Model performance dashboard** (if online labels are available):
   - Rolling window estimates of precision/recall (requires ground truth feedback).

---

## 5. Linking offline and online metrics

Whenever we deploy a new model version:

1. Record offline metrics in a model registry/log.
2. Annotate with the corresponding:
   - Feast feature definitions / versions
   - Dataset snapshot IDs
3. Track online metrics by model version:
   - Include `model_version` as a label in logs and metrics where practical.

The goal is to be able to answer:

> “Given that we deployed model version X with features Y trained on snapshot Z, what did we see in terms of latency and real-world fraud detection performance?”

Even in early stages, we should structure the system so that this linkage can be added with minimal friction later.