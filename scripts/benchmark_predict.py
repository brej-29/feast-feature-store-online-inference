#!/usr/bin/env python
import argparse
import statistics
import time
from typing import Any, Dict, List

import requests

from pipelines.encoders import deterministic_hash


def _build_payload(i: int) -> Dict[str, Any]:
    amount = 100.0 + i
    tx_type = "PAYMENT" if i % 2 == 0 else "TRANSFER"
    name_orig = f"CUST_{i:06d}"
    name_dest = f"MER_{(i // 2) % 5000:06d}"

    return {
        "entity_ids": {
            "customer_id": name_orig,
            "merchant_id": name_dest,
            "account_id": name_orig,
            "device_id": deterministic_hash(f"{name_orig}|{name_dest}"),
            "geo_cell_id": deterministic_hash(name_dest),
        },
        "request": {
            "amount": amount,
            "type": tx_type,
            "oldbalanceOrg": 1000.0,
            "oldbalanceDest": 500.0,
        },
    }


def _percentile(values: List[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(int(pct * len(ordered)), len(ordered) - 1)
    return ordered[idx]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Latency benchmark for the /api/predict endpoint (p50/p95/p99, "
        "with the server-reported feature-fetch vs. inference split).",
    )
    parser.add_argument("--base-url", type=str, default="http://localhost:8000")
    parser.add_argument("--n", type=int, default=200)
    args = parser.parse_args()

    url = f"{args.base_url.rstrip('/')}/api/predict"
    total_ms: List[float] = []
    fetch_ms: List[float] = []
    infer_ms: List[float] = []
    success = 0
    errors = 0

    for i in range(args.n):
        payload = _build_payload(i)
        start = time.perf_counter()
        try:
            resp = requests.post(url, json=payload, timeout=5)
            elapsed_ms = (time.perf_counter() - start) * 1000.0
            if resp.status_code == 200:
                success += 1
                total_ms.append(elapsed_ms)
                body = resp.json()
                fetch_ms.append(float(body.get("feature_fetch_ms", 0.0)))
                infer_ms.append(float(body.get("inference_ms", 0.0)))
            else:
                errors += 1
        except requests.RequestException:
            elapsed_ms = (time.perf_counter() - start) * 1000.0
            errors += 1
        print(f"{i + 1}/{args.n} latency_ms={elapsed_ms:.1f}")

    print("\nBenchmark results")
    print(f"Base URL: {args.base_url}")
    print(f"Requests: {args.n}  Success: {success}  Errors: {errors}")
    for label, series in [
        ("total (client-observed)", total_ms),
        ("feature_fetch (server-reported)", fetch_ms),
        ("inference (server-reported)", infer_ms),
    ]:
        p50 = _percentile(series, 0.50)
        p95 = _percentile(series, 0.95)
        p99 = _percentile(series, 0.99)
        mean = statistics.mean(series) if series else 0.0
        print(f"{label}: mean={mean:.1f}ms p50={p50:.1f}ms p95={p95:.1f}ms p99={p99:.1f}ms")


if __name__ == "__main__":
    main()
