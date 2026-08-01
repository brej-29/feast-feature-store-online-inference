"""Train the fraud model on features retrieved through Feast.

Training/serving consistency
----------------------------
Training data is assembled with ``store.get_historical_features`` against the
``fraud_detection_v2`` feature service -- the exact same feature definitions
the API reads at serving time with ``get_online_features``. Feast's
point-in-time join guarantees each training row only sees feature values that
existed before that transaction (see pipelines/build_entity_tables.py for the
leakage-safety construction).

Request-time features
---------------------
Only fields available BEFORE a transaction executes are used: amount, type,
hour, and pre-transaction balances. ``newbalanceOrig``/``newbalanceDest`` are
deliberately excluded -- they describe the post-transaction state, which a
real-time scorer cannot know. (They also make PaySim near-trivially
separable, which flatters metrics dishonestly.)

Evaluation uses a temporal split: train on the earliest 80% of transactions,
test on the most recent 20%. A random split would leak future entity behavior
into training.
"""

import argparse
import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    precision_recall_curve,
    roc_auc_score,
)
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from pipelines.encoders import map_type_to_code
from pipelines.pg_config import apply_postgres_url_env

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("feast_fraud.pipelines.train_model")

FEATURE_SERVICE_NAME = "fraud_detection_v2"
LABEL_COL = "isFraud"
TS_COL = "event_timestamp"

ENTITY_ID_COLS = ["customer_id", "merchant_id", "device_id", "account_id", "geo_cell_id"]

# Features computed from the incoming request itself (no store lookup).
REQUEST_FEATURE_COLS = [
    "amount",
    "type_code",
    "txn_hour",
    "oldbalanceOrg",
    "oldbalanceDest",
    "amount_over_orig_balance",
]


def build_entity_df(transactions: pd.DataFrame) -> pd.DataFrame:
    """Entity dataframe for Feast historical retrieval + request-time features."""
    df = transactions.copy()
    df["type_code"] = df["type"].map(map_type_to_code).astype("int64")
    df["txn_hour"] = df[TS_COL].dt.hour.astype("int64")
    df["amount_over_orig_balance"] = (
        df["amount"] / (df["oldbalanceOrg"] + 1.0)
    ).astype("float64")
    cols = ENTITY_ID_COLS + [TS_COL, LABEL_COL] + REQUEST_FEATURE_COLS
    return df[cols].reset_index(drop=True)


def _default_for(feature_col: str) -> float:
    """Serving-time default when an online feature is missing (unseen entity
    or TTL-expired). Must match the fills used in the batch feature tables."""
    if feature_col.endswith("last_txn_hour"):
        return -1.0
    return 0.0


def retrieve_training_frame(store: Any, entity_df: pd.DataFrame) -> pd.DataFrame:
    service = store.get_feature_service(FEATURE_SERVICE_NAME)
    start = time.perf_counter()
    frame = store.get_historical_features(
        entity_df=entity_df,
        features=service,
        full_feature_names=True,
    ).to_df()
    elapsed = time.perf_counter() - start
    logger.info(
        "Historical features retrieved",
        extra={"rows": len(frame), "columns": len(frame.columns), "elapsed_s": round(elapsed, 1)},
    )
    # Feast's point-in-time join drops rows silently rather than raising when
    # the entity_df and the feature tables disagree on timestamp resolution
    # (ns vs us) -- you get an empty/short frame and, without this, a model
    # trained on nothing. Fail loudly instead.
    if len(frame) != len(entity_df):
        raise RuntimeError(
            f"Point-in-time join returned {len(frame)} rows for {len(entity_df)} entity rows. "
            "This usually means entity_df.event_timestamp and the feature tables have "
            f"different datetime resolutions (entity_df is {entity_df['event_timestamp'].dtype})."
        )
    return frame


def train_and_evaluate(
    frame: pd.DataFrame,
    feature_cols: List[str],
    test_fraction: float = 0.2,
    seed: int = 42,
    class_weight: Optional[str] = "balanced",
) -> Dict[str, Any]:
    """Temporal-split training and evaluation. Pure pandas/sklearn (testable)."""
    frame = frame.sort_values(TS_COL, kind="stable").reset_index(drop=True)

    X = frame[feature_cols].astype("float64")
    defaults = {c: _default_for(c) for c in feature_cols}
    X = X.fillna(value=defaults)
    y = frame[LABEL_COL].astype("int64").to_numpy()

    split_idx = int(len(frame) * (1.0 - test_fraction))
    split_time = frame[TS_COL].iloc[split_idx]
    X_train, X_test = X.iloc[:split_idx], X.iloc[split_idx:]
    y_train, y_test = y[:split_idx], y[split_idx:]

    logger.info(
        "Temporal split",
        extra={
            "train_rows": len(X_train),
            "test_rows": len(X_test),
            "split_time": str(split_time),
            "train_fraud_rate": round(float(y_train.mean()), 6),
            "test_fraud_rate": round(float(y_test.mean()), 6),
        },
    )

    # class_weight="balanced" matters a lot at this prevalence (~0.3% fraud):
    # unweighted, the model saturates scores near exactly 0/1 and never
    # reaches a usable high-precision operating point (recall@precision=0.90
    # was 0.0). Weighted, PR-AUC goes 0.54 -> 0.93 and recall@precision=0.90
    # goes 0.0 -> 0.84 on this test window (see D010). Parameterised so that
    # comparison can be re-run for real (--class_weight none) rather than
    # quoted from memory.
    model = HistGradientBoostingClassifier(
        max_iter=300,
        learning_rate=0.1,
        max_depth=None,
        early_stopping=True,
        random_state=seed,
        class_weight=class_weight,
    )
    model.fit(X_train, y_train)
    y_score = model.predict_proba(X_test)[:, 1]

    # Reference baselines so headline numbers have context.
    baseline_lr = make_pipeline(
        StandardScaler(), LogisticRegression(max_iter=1000, random_state=seed)
    )
    baseline_lr.fit(X_train, y_train)
    lr_score = baseline_lr.predict_proba(X_test)[:, 1]

    precision, recall, thresholds = precision_recall_curve(y_test, y_score)

    def recall_at_precision(min_precision: float) -> Optional[float]:
        mask = precision[:-1] >= min_precision
        return float(recall[:-1][mask].max()) if mask.any() else 0.0

    def precision_at_recall(min_recall: float) -> Optional[float]:
        mask = recall[:-1] >= min_recall
        return float(precision[:-1][mask].max()) if mask.any() else 0.0

    # Operating threshold: max F1 on the test PR curve.
    f1 = 2 * precision[:-1] * recall[:-1] / np.maximum(precision[:-1] + recall[:-1], 1e-12)
    best_idx = int(np.argmax(f1))
    threshold = float(thresholds[best_idx])

    metrics: Dict[str, Any] = {
        "test_rows": int(len(y_test)),
        "test_fraud_rate": float(y_test.mean()),
        "pr_auc": float(average_precision_score(y_test, y_score)),
        "roc_auc": float(roc_auc_score(y_test, y_score)),
        "brier_score": float(brier_score_loss(y_test, y_score)),
        "recall_at_precision_0.90": recall_at_precision(0.90),
        "recall_at_precision_0.95": recall_at_precision(0.95),
        "precision_at_recall_0.50": precision_at_recall(0.50),
        "threshold_max_f1": threshold,
        "f1_at_threshold": float(f1[best_idx]),
        "baseline_prevalence_pr_auc": float(y_test.mean()),
        "baseline_logreg_pr_auc": float(average_precision_score(y_test, lr_score)),
        "baseline_logreg_roc_auc": float(roc_auc_score(y_test, lr_score)),
        "train_rows": int(len(y_train)),
        "split_time": str(split_time),
    }

    return {
        "model": model,
        "metrics": metrics,
        "threshold": threshold,
        "feature_defaults": defaults,
    }


def _write_model_card(
    path: str,
    model_version: str,
    metrics: Dict[str, Any],
    feast_feature_cols: List[str],
    label_delay_note: str,
) -> None:
    card = f"""# Model Card — fraud scoring `{model_version}`

## Summary

Gradient-boosted trees (`sklearn.ensemble.HistGradientBoostingClassifier`,
`class_weight="balanced"`) scoring the probability that an online payment
transaction is fraudulent. Features are served by a Feast feature store;
training data was assembled via `get_historical_features` (point-in-time
joins) against the same `fraud_detection_v2` feature service used at serving
time.

`class_weight="balanced"` matters a lot at this prevalence (~0.34% fraud):
unweighted, predicted probabilities collapsed to almost exactly 0 or 1 and no
threshold reached 90% precision (`recall_at_precision_0.90 == 0.0`).
Weighted, PR-AUC went 0.54 → 0.93 and `recall_at_precision_0.90` went 0.0 →
0.84 on the same test window (see decision D010) -- this is a reweighted
loss, not a post-hoc calibration, so it changed the model's ranking, not just
its threshold.

## Data — read this first

- Trained on the **PaySim synthetic** mobile-money simulation
  (Kaggle "Online Payments Fraud Detection Dataset"). **All metrics below are
  on synthetic data** and will not transfer to real payment traffic.
- Uniform random sample of 300k transactions across the full ~31-day
  simulated window; timestamps re-anchored to a recent window for online
  serving demos.
- Evaluation: temporal split — trained on the earliest 80%, evaluated on the
  most recent 20%.

## Leakage controls

- Entity aggregates are point-in-time correct: each feature row only
  aggregates transactions strictly before its timestamp.
- {label_delay_note}
- Post-transaction fields (`newbalanceOrig`, `newbalanceDest`) are excluded:
  a real-time scorer cannot observe them.

## Metrics (synthetic test window)

| Metric | Value |
|---|---|
| PR-AUC | {metrics['pr_auc']:.4f} |
| ROC-AUC | {metrics['roc_auc']:.4f} |
| Recall @ precision ≥ 0.90 | {metrics['recall_at_precision_0.90']:.4f} |
| Precision @ recall ≥ 0.50 | {metrics['precision_at_recall_0.50']:.4f} |
| Brier score | {metrics['brier_score']:.6f} |
| Test fraud prevalence (PR-AUC floor) | {metrics['test_fraud_rate']:.6f} |
| Logistic-regression baseline PR-AUC | {metrics['baseline_logreg_pr_auc']:.4f} |

Operating threshold (max-F1 on test): `{metrics['threshold_max_f1']:.6f}`
(F1 = {metrics['f1_at_threshold']:.4f}).

## Features

Request-time: {', '.join(f'`{c}`' for c in REQUEST_FEATURE_COLS)}.

Feast online features ({len(feast_feature_cols)}): entity behavior profiles
(transaction counts/amounts, counterparty cardinality, matured fraud rates)
for customer, merchant, device, account, and geo-cell entities, plus
realtime last-transaction features pushed from the Kafka consumer.

## Known limitations

- Synthetic data: fraud patterns are simulator artifacts.
- Fraud labels in production arrive days/weeks late; this model assumes a
  72h maturation delay for label-derived features but instant labels for
  training targets.
- No fairness evaluation (synthetic entities carry no demographics).
- Threshold chosen for max F1; a production deployment would pick it from a
  cost matrix.
"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(card)


def _log_to_mlflow(params: Dict[str, Any], metrics: Dict[str, Any], artifacts: List[str]) -> None:
    """Log one training run to a local-file MLflow backend.

    mlflow is a dev-only dependency (see requirements-dev.txt) -- the serving
    container never imports this module, so a missing mlflow degrades to a
    warning rather than breaking training.
    """
    try:
        import mlflow
    except ImportError:
        logger.warning("mlflow_not_installed_skipping_tracking")
        return

    mlflow.set_experiment("fraud_feature_store")
    with mlflow.start_run():
        mlflow.log_params(params)
        mlflow.log_metrics({k: v for k, v in metrics.items() if isinstance(v, (int, float))})
        for path in artifacts:
            if os.path.exists(path):
                mlflow.log_artifact(path)


def run(
    transactions_path: str,
    repo_path: str,
    out_dir: str,
    max_rows: Optional[int],
    test_fraction: float,
    seed: int,
    class_weight: Optional[str] = "balanced",
    save: bool = True,
    track: bool = True,
) -> Dict[str, Any]:
    from feast import FeatureStore  # deferred: heavy import

    # Resolve POSTGRES_URL -> discrete POSTGRES_* (and load .env) before
    # building the store, same as the API and the feast CLI scripts do.
    # Without this, feature_store.yaml's ${POSTGRES_PORT} stays unsubstituted
    # and RepoConfig fails to parse.
    apply_postgres_url_env()

    transactions = pd.read_parquet(transactions_path)
    if max_rows is not None and len(transactions) > max_rows:
        transactions = (
            transactions.sample(n=max_rows, random_state=seed)
            .sort_values(TS_COL, kind="stable")
            .reset_index(drop=True)
        )
    entity_df = build_entity_df(transactions)

    store = FeatureStore(repo_path=repo_path)
    frame = retrieve_training_frame(store, entity_df)

    feast_feature_cols = [
        c
        for c in frame.columns
        if c not in set(ENTITY_ID_COLS + [TS_COL, LABEL_COL] + REQUEST_FEATURE_COLS)
    ]
    feature_cols = REQUEST_FEATURE_COLS + sorted(feast_feature_cols)
    logger.info(
        "Feature columns resolved",
        extra={"request": len(REQUEST_FEATURE_COLS), "feast": len(feast_feature_cols)},
    )

    result = train_and_evaluate(
        frame,
        feature_cols=feature_cols,
        test_fraction=test_fraction,
        seed=seed,
        class_weight=class_weight,
    )

    model_version = f"hgb_v2_{datetime.now(timezone.utc).strftime('%Y%m%d')}"
    os.makedirs(out_dir, exist_ok=True)

    bundle = {
        "model": result["model"],
        "model_version": model_version,
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "feature_names": feature_cols,
        "request_feature_names": REQUEST_FEATURE_COLS,
        "feast_feature_names": sorted(feast_feature_cols),
        "feature_service": FEATURE_SERVICE_NAME,
        "feature_defaults": result["feature_defaults"],
        "threshold": result["threshold"],
        "metrics": result["metrics"],
    }
    model_path = os.path.join(out_dir, "fraud_model_v2.joblib")
    card_path = os.path.join(out_dir, "MODEL_CARD.md")
    metrics_path = os.path.join(out_dir, "metrics_v2.json")

    # save=False is used by comparison runs (e.g. --class_weight none) so an
    # experiment variant never overwrites the served production artifact.
    if save:
        joblib.dump(bundle, model_path)
        with open(metrics_path, "w", encoding="utf-8") as f:
            json.dump({"model_version": model_version, **result["metrics"]}, f, indent=2)
        _write_model_card(
            card_path,
            model_version=model_version,
            metrics=result["metrics"],
            feast_feature_cols=sorted(feast_feature_cols),
            label_delay_note=(
                "Fraud-label-derived features (`fraud_rate_prior`, ...) only count "
                "transactions whose labels had matured (72h delay) at feature time."
            ),
        )
    else:
        logger.info("save=False; skipping artifact write (comparison run)")

    if track:
        _log_to_mlflow(
            params={
                "class_weight": class_weight or "none",
                "seed": seed,
                "test_fraction": test_fraction,
                "max_rows": max_rows if max_rows is not None else "all",
                "n_features": len(feature_cols),
                "n_feast_features": len(feast_feature_cols),
                "feature_service": FEATURE_SERVICE_NAME,
                "model": "HistGradientBoostingClassifier",
                "saved_as_production": save,
                # Distinguishes the sample-built feature tables from the
                # full-dataset Spark build (scripts/train_on_full_dataset.sh).
                "feature_table_dir": os.getenv("FEATURE_TABLE_DIR", "../data/processed"),
            },
            metrics=result["metrics"],
            artifacts=[card_path, metrics_path] if save else [],
        )

    logger.info(
        "Training complete",
        extra={
            "model_path": model_path if save else None,
            "pr_auc": result["metrics"]["pr_auc"],
            "roc_auc": result["metrics"]["roc_auc"],
        },
    )
    return {"model_path": model_path if save else None, "metrics": result["metrics"]}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Train the fraud model on Feast-served point-in-time features.",
    )
    parser.add_argument("--transactions_path", default="data/processed/transactions_clean.parquet")
    parser.add_argument("--repo_path", default="feature_repo")
    parser.add_argument("--out_dir", default="models")
    parser.add_argument("--max_rows", type=int, default=None)
    parser.add_argument("--test_fraction", type=float, default=0.2)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--class_weight",
        choices=["balanced", "none"],
        default="balanced",
        help="'none' reproduces the pre-D010 unweighted model for comparison.",
    )
    parser.add_argument(
        "--no_save",
        action="store_true",
        help="Skip writing model/metrics/card -- use for comparison runs so they "
        "don't overwrite the served production artifact.",
    )
    parser.add_argument("--no_mlflow", action="store_true", help="Skip MLflow tracking.")
    return parser.parse_args()


def main() -> None:
    try:
        args = parse_args()
        run(
            transactions_path=args.transactions_path,
            repo_path=args.repo_path,
            out_dir=args.out_dir,
            max_rows=args.max_rows,
            test_fraction=args.test_fraction,
            seed=args.seed,
            class_weight=None if args.class_weight == "none" else "balanced",
            save=not args.no_save,
            track=not args.no_mlflow,
        )
    except Exception:
        logger.exception("train_model_failed")
        raise


if __name__ == "__main__":
    main()
