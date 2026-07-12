import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Dict, List

import pandas as pd
from kafka import KafkaConsumer

from pipelines.encoders import map_type_to_code
from services.streaming.feast_push import push_customer_realtime

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("feast_fraud.streaming.kafka_consumer")


def _build_dataframe(messages: List[Dict]) -> pd.DataFrame:
    rows = []
    for msg in messages:
        try:
            customer_id = msg["customer_id"]
            ts_str = msg["event_timestamp"]
            amount = float(msg.get("amount", 0.0))
            tx_type = msg.get("type", "UNKNOWN")
            is_flagged = int(msg.get("isFlaggedFraud", 0))

            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            last_txn_hour = ts.hour

            rows.append(
                {
                    "event_timestamp": ts.astimezone(timezone.utc),
                    "customer_id": customer_id,
                    "last_txn_amount": amount,
                    "last_txn_type_code": map_type_to_code(tx_type),
                    "last_txn_hour": last_txn_hour,
                    "last_txn_is_flagged": is_flagged,
                }
            )
        except Exception:
            logger.exception("failed_to_parse_message", extra={"message": msg})
            continue

    return pd.DataFrame(rows)


def main() -> None:
    brokers = os.getenv("KAFKA_BROKERS", "localhost:9092")
    topic = os.getenv("KAFKA_TOPIC", "txn_events")
    group_id = os.getenv("KAFKA_GROUP_ID", "feast_fraud_consumer")
    batch_size = int(os.getenv("KAFKA_CONSUMER_BATCH_SIZE", "32"))
    poll_timeout_ms = int(os.getenv("KAFKA_POLL_TIMEOUT_MS", "1000"))

    logger.info(
        "Starting Kafka consumer",
        extra={"brokers": brokers, "topic": topic, "group_id": group_id},
    )

    consumer = KafkaConsumer(
        topic,
        bootstrap_servers=brokers.split(","),
        value_deserializer=lambda v: json.loads(v.decode("utf-8")),
        auto_offset_reset="earliest",
        enable_auto_commit=False,
        group_id=group_id,
    )

    try:
        buffer: List = []
        while True:
            records = consumer.poll(timeout_ms=poll_timeout_ms)
            for tp, msgs in records.items():
                for msg in msgs:
                    buffer.append(msg)

                    if len(buffer) >= batch_size:
                        payloads = [m.value for m in buffer]
                        df = _build_dataframe(payloads)
                        if not df.empty:
                            try:
                                push_customer_realtime(df)
                                consumer.commit()
                                logger.info(
                                    "Committed Kafka offsets after Feast push",
                                    extra={
                                        "topic": tp.topic,
                                        "partition": tp.partition,
                                        "batch_size": len(buffer),
                                    },
                                )
                            except Exception:
                                logger.exception("feast_push_from_kafka_failed")
                                time.sleep(2.0)
                        buffer.clear()

            if not records:
                time.sleep(1.0)
    except KeyboardInterrupt:
        logger.info("Kafka consumer interrupted by user")
    except Exception:
        logger.exception("kafka_consumer_failed")
        raise
    finally:
        consumer.close()
        logger.info("Kafka consumer closed")


if __name__ == "__main__":
    main()