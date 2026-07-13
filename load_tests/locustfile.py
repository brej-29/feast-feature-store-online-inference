from __future__ import annotations

import os
import random
from typing import Any, Dict

from locust import HttpUser, between, task

from pipelines.encoders import deterministic_hash


class FraudUser(HttpUser):
    """
    Locust user that exercises the /api/predict endpoint.

    Usage:

    ```bash
    TARGET_HOST=http://localhost:8000 locust -f load_tests/locustfile.py
    ```
    """

    wait_time = between(0.1, 1.0)

    def on_start(self) -> None:
        # TARGET_HOST allows overriding the base URL without editing this file.
        self.host = os.getenv("TARGET_HOST", "http://localhost:8000")

    @task
    def predict_fraud(self) -> None:
        amount = random.uniform(10.0, 5000.0)
        tx_type = random.choice(["PAYMENT", "TRANSFER", "CASH_OUT", "CASH_IN"])
        name_orig = f"CUST_{random.randint(1, 10_000):06d}"
        name_dest = f"MER_{random.randint(1, 5_000):06d}"

        payload: Dict[str, Any] = {
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
                "oldbalanceOrg": random.uniform(0.0, 20000.0),
                "oldbalanceDest": random.uniform(0.0, 20000.0),
            },
        }

        self.client.post("/api/predict", json=payload)
