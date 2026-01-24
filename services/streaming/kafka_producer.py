import argparse
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List

import numpy as np
from kafka import KafkaProducer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("feast_fraud.streaming.kafka_producer")


def _build_synthetic_events(num_messages: int, seed: int) -> List[Dict[str, Any]]:
    rng = np.random.default_rng(seed)
    events: List[Dict[str, Any]] = []

    now = datetime.now(timezone.utc)

    tx_types = ["PAYMENT", "TRANSFER", "CASH_OUT", "CASH_IN"]

    for i in range(num_messages):
        customer_id = f"C{100000 + i}"
        name_dest = f"M{200000 + i}"
        amount = float(rng.uniform(1.0, 5000.0))
        tx_type = str(rng.choice(tx_types))
        is_flagged = int(rng.integers(0, 2))

        event = {
            "customer_id": customer_id,
            "event_timestamp": now.isoformat(),
            "amount": amount,
            "type": tx_type,
            "isFlaggedFraud": is_flagged,
            "nameDest": name_dest,
        }
        events.append(event)

    return events


def run(
    brokers: str,
    topic: str,
    num_messages: int,
    seed: int,
) -> None:
    logger.info(
        "Starting Kafka producer",
        extra={"brokers": brokers, "topic": topic, "num_messages": num_messages},
    )

    producer = KafkaProducer(
        bootstrap_servers=brokers.split(","),
        value_serializer=lambda v: json.dumps(v).encode("utf-8"),
    )

    events = _build_synthetic_events(num_messages=num_messages, seed=seed)
    for event in events:
        producer.send(topic, value=event)

    producer.flush()
    logger.info("Finished sending Kafka messages")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Seed a Kafka topic with synthetic transaction events.",
    )
    parser.add_argument(
        "--brokers",
        type=str,
        default=os.getenv("KAFKA_BROKERS", "localhost:9092"),
        help="Comma-separated list of Kafka bootstrap servers.",
    )
    parser.add_argument(
        "--topic",
        type=str,
        default=os.getenv("KAFKA_TOPIC", "txn_events"),
        help="Kafka topic to publish events to.",
    )
    parser.add_argument(
        "--num-messages",
        type=int,
        default=10,
        help="Number of synthetic events to publish.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for synthetic event generation.",
    )
    return parser.parse_args()


def main() -> None:
    try:
        args = parse_args()
        run(
            brokers=args.brokers,
            topic=args.topic,
            num_messages=args.num_messages,
            seed=args.seed,
        )
    except Exception:
        logger.exception("kafka_producer_failed")
        raise


if __name__ == "__main__":
    main()