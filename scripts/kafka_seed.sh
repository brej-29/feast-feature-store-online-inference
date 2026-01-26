#!/usr/bin/env bash
set -euo pipefail

BROKERS="${KAFKA_BROKERS:-localhost:9092}"
TOPIC="${KAFKA_TOPIC:-txn_events}"
NUM_MESSAGES="${KAFKA_SEED_MESSAGES:-10}"

echo "Seeding Kafka topic '${TOPIC}' on brokers '${BROKERS}' with ${NUM_MESSAGES} synthetic events ..."
python -m services.streaming.kafka_producer \
  --brokers "${BROKERS}" \
  --topic "${TOPIC}" \
  --num-messages "${NUM_MESSAGES}"