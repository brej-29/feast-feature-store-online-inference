#!/usr/bin/env python
import argparse
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict

from kafka import KafkaProducer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("feast_fraud.scripts.kafka_seed_events")


def _build_event(index: int) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    return {
        "customer_id": f"CUST_{index:06d}",
        "event_timestamp": now.isoformat(),
        "amount": float(100 + index),
        "type": "PAYMENT" if index % 2 == 0 else "TRANSFER",
        "isFlaggedFraud": int(index % 5 == 0),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seed sample transaction events into Kafka for local testing.",
    )
    parser.add_argument(
        "--brokers",
        type=str,
        default=os.getenv("KAFKA_BROKERS", "localhost:19092"),
        help="Kafka bootstrap servers (comma-separated).",
    )
    parser.add_argument(
        "--topic",
        type=str,
        default=os.getenv("KAFKA_TOPIC", "txn_events"),
        help="Kafka topic to publish to.",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=100,
        help="Number of events to send.",
    )
    args = parser.parse_args()

    producer = KafkaProducer(
        bootstrap_servers=args.brokers.split(","),
        value_serializer=lambda v: json.dumps(v).encode("utf-8"),
    )

    logger.info(
        "Seeding Kafka events",
        extra={"brokers": args.brokers, "topic": args.topic, "count": args.count},
    )

    try:
        for i in range(args.count):
            event = _build_event(i)
            producer.send(args.topic, value=event)
        producer.flush()
    finally:
        producer.close()

    logger.info("Kafka seeding completed")


if __name__ == "__main__":
    main()