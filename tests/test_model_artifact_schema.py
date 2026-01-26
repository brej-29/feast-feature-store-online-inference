import json
import os

import pytest

METADATA_PATH = "models/model_metadata.json"


@pytest.mark.skipif(
    not os.path.exists(METADATA_PATH),
    reason="Model metadata missing; run pipelines/train_model.py to generate it.",
)
def test_model_metadata_schema():
    with open(METADATA_PATH, "r", encoding="utf-8") as f:
        meta = json.load(f)

    assert meta.get("model_type") == "LogisticRegression"
    assert isinstance(meta.get("feature_columns"), list)
    assert "decision_threshold" in meta
    assert "metrics" in meta
    assert "train" in meta["metrics"]
    assert "validation" in meta["metrics"]