"""Shared, stable encodings used by ingestion, training, streaming, and serving.

Training/serving consistency depends on every component encoding raw values
identically. Keep this module dependency-light (stdlib only) so it can be
imported anywhere.
"""

import hashlib
from typing import Dict

# Stable transaction-type encoding. 0 is reserved for unknown/other types
# (e.g. DEBIT, malformed input) so new types degrade gracefully.
TYPE_CODE_MAPPING: Dict[str, int] = {
    "PAYMENT": 1,
    "TRANSFER": 2,
    "CASH_OUT": 3,
    "CASH_IN": 4,
}


def map_type_to_code(tx_type: str) -> int:
    return TYPE_CODE_MAPPING.get(str(tx_type).upper().strip(), 0)


def deterministic_hash(value: str) -> str:
    """Deterministic, platform-stable 16-char hash used to derive entity IDs."""
    if value is None:
        value = ""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]
