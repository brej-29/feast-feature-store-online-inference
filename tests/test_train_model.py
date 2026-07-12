"""Smoke tests for the training pipeline's pure (non-Feast) core."""

from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

from pipelines.train_model import LABEL_COL, TS_COL, build_entity_df, train_and_evaluate


def _synthetic_training_frame(n: int = 2000, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    amount = rng.lognormal(mean=8.0, sigma=2.0, size=n)
    signal = rng.normal(size=n)
    # Label correlated with `signal` so the model has something to learn.
    y = (signal + rng.normal(scale=0.5, size=n) > 2.2).astype(int)
    return pd.DataFrame(
        {
            TS_COL: [t0 + timedelta(minutes=int(i)) for i in range(n)],
            LABEL_COL: y,
            "amount": amount,
            "signal": signal,
            "noise": rng.normal(size=n),
        }
    )


def test_train_and_evaluate_smoke():
    frame = _synthetic_training_frame()
    result = train_and_evaluate(frame, feature_cols=["amount", "signal", "noise"])

    metrics = result["metrics"]
    assert 0.0 <= metrics["pr_auc"] <= 1.0
    assert 0.0 <= metrics["roc_auc"] <= 1.0
    assert metrics["pr_auc"] > metrics["baseline_prevalence_pr_auc"]
    assert 0.0 <= result["threshold"] <= 1.0

    proba = result["model"].predict_proba(
        pd.DataFrame([[100.0, 3.0, 0.0]], columns=["amount", "signal", "noise"])
    )
    assert proba.shape == (1, 2)


def test_train_and_evaluate_handles_missing_values():
    frame = _synthetic_training_frame()
    frame.loc[frame.sample(frac=0.3, random_state=1).index, "signal"] = np.nan
    result = train_and_evaluate(frame, feature_cols=["amount", "signal", "noise"])
    assert result["feature_defaults"]["signal"] == 0.0


def test_build_entity_df_excludes_post_transaction_fields():
    """newbalance* must never reach the model: they are post-transaction state."""
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    transactions = pd.DataFrame(
        {
            "event_timestamp": [t0],
            "customer_id": ["C1"],
            "merchant_id": ["M1"],
            "device_id": ["D1"],
            "account_id": ["C1"],
            "geo_cell_id": ["G1"],
            "type": ["CASH_OUT"],
            "amount": [100.0],
            "oldbalanceOrg": [1000.0],
            "newbalanceOrig": [900.0],
            "oldbalanceDest": [0.0],
            "newbalanceDest": [100.0],
            "isFraud": [0],
            "isFlaggedFraud": [0],
        }
    )
    entity_df = build_entity_df(transactions)
    assert "newbalanceOrig" not in entity_df.columns
    assert "newbalanceDest" not in entity_df.columns
    assert entity_df["type_code"].iloc[0] == 3  # CASH_OUT
    assert entity_df["amount_over_orig_balance"].iloc[0] == 100.0 / 1001.0


def test_model_uses_balanced_class_weight():
    """Regression guard for D010: unweighted HGB saturates scores at this
    imbalance and never reaches a usable high-precision threshold."""
    from pipelines.train_model import HistGradientBoostingClassifier

    # Build a fresh model the way train_and_evaluate does and check the knob
    # directly, rather than re-deriving the full metric comparison here.
    frame = _synthetic_training_frame()
    result = train_and_evaluate(frame, feature_cols=["amount", "signal", "noise"])
    assert isinstance(result["model"], HistGradientBoostingClassifier)
    assert result["model"].class_weight == "balanced"
