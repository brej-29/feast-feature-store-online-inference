from __future__ import annotations

import os
import random
from typing import Any, Dict

from locust import HttpUser, between, task


def _deterministic_hash(value: str) -> str:
    import hashlib

    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


class FraudUser(HttpUser):
    """
    Locust user that exercises the /api/predict endpoint.

    Usage:

    ```bash
    TARGET_HOST=http://localhost:7860 locust -f load_tests/locustfile.py
    ```
    """

    wait_time = between(0.1, 1.0)

    def on_start(self) -> None:
        # TARGET_HOST allows overriding the base URL without editing this file.
        self.host = os.getenv("TARGET_HOST", "http://localhost:7860")

    @task
    def predict_fraud(self) -> None:
        amount = random.uniform(10.0, 5000.0)
        tx_type = random.choice(["PAYMENT", "TRANSFER", "CASH_OUT", "CASH_IN", "DEBIT"])
        name_orig = f"CUST_{random.randint(1, 10_000):06d}"
        name_dest = f"MER_{random.randint(1, 5_000):06d}"

        customer_id = name_orig
        account_id = name_orig
        merchant_id = name_dest
        device_id = _deterministic_hash(f"{name_orig}|{name_dest}")
        geo_cell_id = _deterministic_hash(name_dest)

        payload: Dict[str, Any] = {
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

        self.client.post("/api/predict", json=payload)