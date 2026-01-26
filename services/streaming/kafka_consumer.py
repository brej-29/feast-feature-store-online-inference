import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Dict, List

import pandas as pd
from kafka import KafkaConsumer

from services.streaming.feast_push import push_customer_realtime

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("feast_fraud.streaming.kafka_consumer")


TYPE_CODE_MAPPING: Dict[str, int] = {
    "PAYMENT": 1,
    "TRANSFER": 2,
    "CASH_OUT": 3,
    "CASH_IN": 4,
}


def _map_type_to_code(tx_type: str) -> int:
    return TYPE_CODE_MAPPING.get(str(tx_type).upper(), 0)


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
                    "last_txn_type_code": _map_type_to_code(tx_type),
                    "last_txn_hour": last_txn_hour,
                    "last_txn_is_flagged": is_flagged,
                }
            )
        except Exception:
            logger.exception("failed_to_parse_message", extra={"message": msg})
            continue

    return pd.DataFrame(rows)


def _push_with_retries(df: pd.DataFrame, max_retries: int = 3, base_delay: float = 1.0) -> None:
    """
    Push a dataframe to Feast with simple exponential backoff.

    Offsets should only be committed if this function returns successfully.
    """
    attempt = 0
    while True:
        try:
            push_customer_realtime(df)
            return
        except Exception:  # noqa: BLE001
            attempt += 1
            logger.exception(
                "feast_push_from_kafka_failed",
                extra={"attempt": attempt, "max_retries": max_retries},
            )
            if attempt >= max_retries:
                raise
            sleep_s = base_delay * (2** (attempt - 1))
            time.sleep(sleep_s)


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
                                _push_with_retries(df)
                                consumer.commit()
                                logger.info(
                                    "Committed Kafka offsets after Feast push",
                                    extra={
                                        "topic": tp.topic,
                                        "partition": tp.partition,
                                        "batch_size": len(buffer),
                                    },
                                )
                            except Exception:  # noqa: BLE001
                                logger.exception("feast_push_retry_exhausted")
                                # Do not commit offsets; messages will be re-consumed.
                        buffer.clear()

            if not records:
                time.sleep(1.0)
    except KeyboardInterrupt:
        logger.info("Kafka consumer interrupted by user")
    except Exception:  # noqa: BLE001
        logger.exception("kafka_consumer_failed")
        raise
    finally:
        consumer.close()
        logger.info("Kafka consumer closed")


if __name__ == "__main__":
    main()