#!/usr/bin/env python
import argparse
import hashlib
import statistics
import time
from typing import Any, Dict

import requests


def _deterministic_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def _build_payload(i: int) -> Dict[str, Any]:
    amount = 100.0 + i
    tx_type = "PAYMENT" if i % 2 == 0 else "TRANSFER"
    name_orig = f"CUST_{i:06d}"
    name_dest = f"MER_{(i // 2) % 5000:06d}"

    customer_id = name_orig
    account_id = name_orig
    merchant_id = name_dest
    device_id = _deterministic_hash(f"{name_orig}|{name_dest}")
    geo_cell_id = _deterministic_hash(name_dest)

    return {
        "entity_ids": {
            "customer_id": customer_id,
            "merchant_id": merchant_id,
            "device_id": device_id,
            "account_id": account_id,
            "geo_cell_id": geo_cell_id,
        },
        "amount": amount,
        "type": tx_type,
        "isFlaggedFraud": 0,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Simple latency benchmark for the /api/predict endpoint.",
    )
    parser.add_argument(
        "--base-url",
        type=str,
        default="http://localhost:7860",
        help="Base URL for the service (e.g. http://localhost:7860).",
    )
    parser.add_argument(
        "--n",
        type=int,
        default=100,
        help="Number of requests to send.",
    )
    args = parser.parse_args()

    url = f"{args.base_url.rstrip('/')}/api/predict"
    latencies_ms = []
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
                latencies_ms.append(elapsed_ms)
            else:
                errors += 1
        except requests.RequestException:
            elapsed_ms = (time.perf_counter() - start) * 1000.0
            errors += 1
        print(f"{i+1}/{args.n} latency_ms={elapsed_ms:.1f}")

    if latencies_ms:
        p50 = statistics.median(latencies_ms)
        p95 = sorted(latencies_ms)[int(0.95 * len(latencies_ms)) - 1]
    else:
        p50 = p95 = 0.0

    print("\nBenchmark results")
    print(f"Base URL: {args.base_url}")
    print(f"Requests: {args.n}")
    print(f"Success:  {success}")
    print(f"Errors:   {errors}")
    print(f"p50 latency: {p50:.1f} ms")
    print(f"p95 latency: {p95:.1f} ms")


if __name__ == "__main__":
    main()