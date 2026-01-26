import argparse
import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import joblib
import numpy as np
import pandas as pd
from feast import FeatureStore
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    confusion_matrix,
    f1_score,
    precision_recall_curve,
    precision_score,
    roc_auc_score,
    recall_score,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("feast_fraud.pipelines.train_model")


def _load_transactions(
    parquet_path: str,
    sample_rows: Optional[int],
    seed: int,
) -> pd.DataFrame:
    if not os.path.exists(parquet_path):
        raise FileNotFoundError(
            f"Cleaned transactions parquet not found at {parquet_path}. "
            "Run pipelines/data_ingest.py first.",
        )

    logger.info(
        "Loading cleaned transactions",
        extra={"path": parquet_path, "sample_rows": sample_rows, "seed": seed},
    )
    df = pd.read_parquet(parquet_path)

    if sample_rows is not None and sample_rows > 0 and len(df) > sample_rows:
        df = df.sample(n=sample_rows, random_state=seed)
        logger.info(
            "Sampled transactions for training",
            extra={"rows_after_sample": len(df)},
        )

    if "event_timestamp" not in df.columns:
        raise ValueError("Expected 'event_timestamp' column in processed data.")
    df["event_timestamp"] = pd.to_datetime(df["event_timestamp"], utc=True, errors="coerce")

    required_cols = [
        "customer_id",
        "merchant_id",
        "device_id",
        "account_id",
        "geo_cell_id",
        "amount",
        "type",
        "isFraud",
        "isFlaggedFraud",
    ]
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns in processed data: {missing}")

    return df


def _build_entity_df(df: pd.DataFrame) -> pd.DataFrame:
    """
    Build the entity_df passed to Feast.get_historical_features.

    It includes:
    - entity join keys
    - event_timestamp
    - request-time fields used by the OnDemandFeatureView
    - labels
    """
    cols = [
        "event_timestamp",
        "customer_id",
        "merchant_id",
        "device_id",
        "account_id",
        "geo_cell_id",
        "amount",
        "type",
        "isFlaggedFraud",
        "isFraud",
    ]
    entity_df = df[cols].copy()
    entity_df = entity_df.sort_values("event_timestamp")
    return entity_df


def _fetch_historical_features(
    store: FeatureStore,
    feature_service_name: str,
    entity_df: pd.DataFrame,
) -> pd.DataFrame:
    logger.info(
        "Fetching historical features from Feast",
        extra={"feature_service": feature_service_name, "rows": len(entity_df)},
    )
    feature_service = store.get_feature_service(feature_service_name)
    training_df = store.get_historical_features(
        entity_df=entity_df,
        features=feature_service,
    ).to_df()

    logger.info(
        "Historical features fetched",
        extra={"rows": len(training_df), "columns": list(training_df.columns)},
    )
    return training_df


def _train_val_split_by_time(
    df: pd.DataFrame,
    time_col: str,
    train_fraction: float = 0.8,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    df = df.sort_values(time_col)
    n = len(df)
    if n == 0:
        raise ValueError("No rows available for training/validation.")

    split_idx = int(n * train_fraction)
    if split_idx == 0 or split_idx == n:
        raise ValueError("Not enough data to perform a time-based split.")

    train_df = df.iloc[:split_idx]
    val_df = df.iloc[split_idx:]

    logger.info(
        "Time-based train/val split created",
        extra={
            "train_rows": len(train_df),
            "val_rows": len(val_df),
            "train_start": train_df[time_col].min().isoformat(),
            "train_end": train_df[time_col].max().isoformat(),
            "val_start": val_df[time_col].min().isoformat(),
            "val_end": val_df[time_col].max().isoformat(),
        },
    )
    return train_df, val_df


def _select_feature_columns(df: pd.DataFrame, target_col: str) -> List[str]:
    non_feature_cols = {
        target_col,
        "isFlaggedFraud",
        "event_timestamp",
        "customer_id",
        "merchant_id",
        "device_id",
        "account_id",
        "geo_cell_id",
    }

    feature_cols: List[str] = []
    for col in df.columns:
        if col in non_feature_cols:
            continue
        series = df[col]
        if pd.api.types.is_numeric_dtype(series):
            feature_cols.append(col)

    logger.info(
        "Selected feature columns",
        extra={"feature_count": len(feature_cols), "feature_cols": feature_cols},
    )
    return feature_cols


def _fit_model(
    X_train: pd.DataFrame,
    y_train: pd.Series,
) -> LogisticRegression:
    logger.info(
        "Fitting LogisticRegression model",
        extra={"rows": len(X_train), "features": list(X_train.columns)},
    )
    model = LogisticRegression(
        max_iter=1000,
        class_weight="balanced",
        n_jobs=-1,
        random_state=42,
    )
    model.fit(X_train, y_train)
    return model


def _compute_metrics(
    y_true: np.ndarray,
    y_score: np.ndarray,
    threshold: float,
) -> Dict[str, Any]:
    metrics: Dict[str, Any] = {}

    try:
        metrics["roc_auc"] = float(roc_auc_score(y_true, y_score))
    except ValueError:
        metrics["roc_auc"] = None

    try:
        metrics["pr_auc"] = float(average_precision_score(y_true, y_score))
    except ValueError:
        metrics["pr_auc"] = None

    y_pred = (y_score >= threshold).astype(int)

    metrics["precision"] = float(precision_score(y_true, y_pred, zero_division=0))
    metrics["recall"] = float(recall_score(y_true, y_pred, zero_division=0))
    metrics["f1"] = float(f1_score(y_true, y_pred, zero_division=0))

    tn, fp, fn, tp = confusion_matrix(y_true, y_pred).ravel()
    metrics["confusion_matrix"] = {
        "tn": int(tn),
        "fp": int(fp),
        "fn": int(fn),
        "tp": int(tp),
    }

    return metrics


def _choose_threshold_for_precision(
    y_true: np.ndarray,
    y_score: np.ndarray,
    target_precision: float = 0.9,
) -> float:
    precision, recall, thresholds = precision_recall_curve(y_true, y_score)
    # precision has length len(thresholds) + 1; ignore last point
    candidate_thresholds = thresholds[precision[:-1] >= target_precision]
    if len(candidate_thresholds) == 0:
        return 0.5
    return float(np.max(candidate_thresholds))


def _compute_permutation_importance(
    model: LogisticRegression,
    X_val: pd.DataFrame,
    y_val: pd.Series,
) -> pd.DataFrame:
    logger.info(
        "Computing permutation feature importance",
        extra={"rows": len(X_val), "features": list(X_val.columns)},
    )
    result = permutation_importance(
        model,
        X_val,
        y_val,
        n_repeats=5,
        random_state=42,
        scoring="average_precision",
        n_jobs=-1,
    )
    df_imp = pd.DataFrame(
        {
            "feature": X_val.columns,
            "importance_mean": result.importances_mean,
            "importance_std": result.importances_std,
        },
    ).sort_values("importance_mean", ascending=False)
    return df_imp


def _write_model_artifacts(
    model: LogisticRegression,
    feature_cols: List[str],
    train_metrics: Dict[str, Any],
    val_metrics: Dict[str, Any],
    threshold: float,
    feature_service_name: str,
    training_window: Dict[str, str],
    out_dir: str,
    feature_importance: pd.DataFrame,
) -> None:
    os.makedirs(out_dir, exist_ok=True)
    model_path = os.path.join(out_dir, "model.joblib")
    metadata_path = os.path.join(out_dir, "model_metadata.json")
    model_card_path = os.path.join(out_dir, "model_card.md")
    importance_path = os.path.join(out_dir, "feature_importance.csv")

    joblib.dump(model, model_path)
    feature_importance.to_csv(importance_path, index=False)

    now_iso = datetime.utcnow().isoformat() + "Z"
    metadata: Dict[str, Any] = {
        "model_type": "LogisticRegression",
        "model_version": "risk_scoring_lr_v1",
        "created_at": now_iso,
        "feature_service_name": feature_service_name,
        "feature_columns": feature_cols,
        "decision_threshold": threshold,
        "training_window": training_window,
        "metrics": {
            "train": train_metrics,
            "validation": val_metrics,
        },
    }

    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)

    # Simple, human-readable model card
    with open(model_card_path, "w", encoding="utf-8") as f:
        f.write("# Model Card – risk_scoring_lr_v1\n\n")
        f.write("## Overview\n\n")
        f.write(
            "Logistic regression model trained on engineered features from Feast "
            f"FeatureService `{feature_service_name}` for binary fraud detection.\n\n",
        )

        f.write("## Data\n\n")
        f.write(
            "- Source: Kaggle Online Payments Fraud Detection dataset, cleaned via "
            "`pipelines/data_ingest.py`.\n",
        )
        f.write("- Features: engineered per-entity + request-time features.\n")
        f.write(
            f"- Training window: {training_window['train_start']} to "
            f"{training_window['train_end']} (train), "
            f"{training_window['val_start']} to {training_window['val_end']} (validation).\n\n",
        )

        f.write("## Metrics (validation)\n\n")
        f.write(f"- PR-AUC: {val_metrics.get('pr_auc')}\n")
        f.write(f"- ROC-AUC: {val_metrics.get('roc_auc')}\n")
        f.write(f"- Threshold: {threshold}\n")
        f.write(
            f"- Precision: {val_metrics.get('precision')}  "
            f"Recall: {val_metrics.get('recall')}  "
            f"F1: {val_metrics.get('f1')}\n",
        )
        cm = val_metrics.get("confusion_matrix", {})
        f.write(
            "- Confusion matrix (TN, FP, FN, TP): "
            f"{cm.get('tn')}, {cm.get('fp')}, {cm.get('fn')}, {cm.get('tp')}\n\n",
        )

        f.write("## Limitations and ethical notes\n\n")
        f.write(
            "- The model is trained on a single dataset and may not generalize to other "
            "fraud patterns or regions.\n",
        )
        f.write(
            "- Features include behavioural signals; care must be taken to avoid using "
            "them in ways that unfairly disadvantage specific user groups.\n",
        )
        f.write(
            "- Predictions should be used as one input to human review, not as an "
            "automatic decision without oversight.\n",
        )

    logger.info(
        "Model artifacts written",
        extra={
            "model_path": model_path,
            "metadata_path": metadata_path,
            "model_card_path": model_card_path,
            "importance_path": importance_path,
        },
    )


def run(
    transactions_path: str,
    repo_path: str,
    feature_service_name: str,
    sample_rows: Optional[int],
    seed: int,
    out_dir: str,
) -> None:
    df_raw = _load_transactions(
        parquet_path=transactions_path,
        sample_rows=sample_rows,
        seed=seed,
    )
    entity_df = _build_entity_df(df_raw)

    store = FeatureStore(repo_path=repo_path)
    training_df = _fetch_historical_features(
        store=store,
        feature_service_name=feature_service_name,
        entity_df=entity_df,
    )

    # Ensure event_timestamp is datetime
    training_df["event_timestamp"] = pd.to_datetime(
        training_df["event_timestamp"],
        utc=True,
        errors="coerce",
    )

    target_col = "isFraud"
    if target_col not in training_df.columns:
        raise ValueError(f"Expected target column '{target_col}' in training data.")

    train_df, val_df = _train_val_split_by_time(
        training_df,
        time_col="event_timestamp",
        train_fraction=0.8,
    )

    feature_cols = _select_feature_columns(training_df, target_col=target_col)

    X_train = train_df[feature_cols].fillna(0.0)
    y_train = train_df[target_col].astype(int)
    X_val = val_df[feature_cols].fillna(0.0)
    y_val = val_df[target_col].astype(int)

    model = _fit_model(X_train, y_train)

    # Choose threshold based on validation curve
    y_val_score = model.predict_proba(X_val)[:, 1]
    threshold = _choose_threshold_for_precision(
        y_true=y_val.to_numpy(),
        y_score=y_val_score,
        target_precision=0.9,
    )

    # Metrics
    y_train_score = model.predict_proba(X_train)[:, 1]
    train_metrics = _compute_metrics(
        y_true=y_train.to_numpy(),
        y_score=y_train_score,
        threshold=threshold,
    )
    val_metrics = _compute_metrics(
        y_true=y_val.to_numpy(),
        y_score=y_val_score,
        threshold=threshold,
    )

    logger.info(
        "Training metrics",
        extra={"train_metrics": train_metrics, "val_metrics": val_metrics},
    )

    # Permutation importance on validation set
    feature_importance = _compute_permutation_importance(
        model=model,
        X_val=X_val,
        y_val=y_val,
    )

    training_window = {
        "train_start": train_df["event_timestamp"].min().isoformat(),
        "train_end": train_df["event_timestamp"].max().isoformat(),
        "val_start": val_df["event_timestamp"].min().isoformat(),
        "val_end": val_df["event_timestamp"].max().isoformat(),
    }

    _write_model_artifacts(
        model=model,
        feature_cols=feature_cols,
        train_metrics=train_metrics,
        val_metrics=val_metrics,
        threshold=threshold,
        feature_service_name=feature_service_name,
        training_window=training_window,
        out_dir=out_dir,
        feature_importance=feature_importance,
    )


def parse_args(args: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Train a logistic regression fraud model using Feast-engineered features "
            "from a FeatureService."
        ),
    )
    parser.add_argument(
        "--transactions_path",
        type=str,
        default="data/processed/transactions_clean.parquet",
        help="Path to cleaned transactions parquet.",
    )
    parser.add_argument(
        "--repo_path",
        type=str,
        default=os.getenv("FEAST_REPO_PATH", "feature_repo"),
        help="Path to Feast feature repo.",
    )
    parser.add_argument(
        "--feature_service_name",
        type=str,
        default="risk_scoring_v1",
        help="Name of the Feast FeatureService to use for training.",
    )
    parser.add_argument(
        "--sample_rows",
        type=int,
        default=None,
        help=(
            "Optional maximum number of transaction rows to sample before training. "
            "If omitted or non-positive, use all rows."
        ),
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for sampling and model training.",
    )
    parser.add_argument(
        "--out_dir",
        type=str,
        default="models",
        help="Directory where model artifacts (joblib, metadata, model card) are written.",
    )
    return parser.parse_args(args=args)


def main(cli_args: Optional[List[str]] = None) -> None:
    args = parse_args(cli_args)
    try:
        sample_rows: Optional[int]
        if args.sample_rows is not None and args.sample_rows <= 0:
            sample_rows = None
        else:
            sample_rows = args.sample_rows

        run(
            transactions_path=args.transactions_path,
            repo_path=args.repo_path,
            feature_service_name=args.feature_service_name,
            sample_rows=sample_rows,
            seed=args.seed,
            out_dir=args.out_dir,
        )
    except FileNotFoundError:
        logger.warning(
            "train_model_skipped_missing_input",
            extra={"transactions_path": args.transactions_path},
        )
    except Exception:  # noqa: BLE001
        logger.exception("train_model_failed")
        raise


if __name__ == "__main__":
    main()