#!/usr/bin/env python
"""Best-effort data-drift report (Evidently).

Design notes:
- Evidently is imported lazily, *inside* the data path, so that when the
  input data is absent (the usual CI case -- transactions_clean.parquet is
  not committed) this script exits cleanly without importing Evidently at
  all. Previously the import lived at module top with the new-style
  ``from evidently import Report`` API, which does not exist in the pinned
  ``evidently==0.4.36`` (there ``Report`` lives in ``evidently.report``);
  that mismatch made the drift job fail on import before it could even
  reach the "skip, no data" branch.
- Report generation is wrapped so that any Evidently error is logged and
  swallowed: drift reporting is an optional monitoring artifact and must
  never fail the CI pipeline.
"""

import logging
import os

import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("feast_fraud.monitoring.drift_report")


def _load_report_classes():
    """Return (Report, DataDriftPreset), tolerant of Evidently's API split.

    0.4.x exposes ``evidently.report.Report``; newer releases re-export it as
    ``evidently.Report`` and move presets to ``evidently.presets``. Try both
    so the script keeps working across an Evidently upgrade.
    """
    try:  # Evidently 0.4.x (the pinned version)
        from evidently.metric_preset import DataDriftPreset
        from evidently.report import Report

        return Report, DataDriftPreset
    except ImportError:  # Evidently >= 0.6 new API
        from evidently import Report
        from evidently.presets import DataDriftPreset

        return Report, DataDriftPreset


def main() -> None:
    data_path = os.path.join("data", "processed", "transactions_clean.parquet")
    if not os.path.exists(data_path):
        logger.warning(
            "drift_report_skipped_missing_input",
            extra={"data_path": data_path},
        )
        return

    df = pd.read_parquet(data_path)
    if "event_timestamp" not in df.columns:
        logger.warning("drift_report_missing_event_timestamp")
        return

    if len(df) < 10:
        logger.warning("drift_report_not_enough_rows", extra={"rows": len(df)})
        return

    df["event_timestamp"] = pd.to_datetime(df["event_timestamp"], utc=True, errors="coerce")
    df = df.sort_values("event_timestamp")

    # Reference = earlier half of the window, current = later half.
    mid = len(df) // 2
    reference = df.iloc[:mid]
    current = df.iloc[mid:]

    logger.info(
        "running_data_drift_report",
        extra={"reference_rows": len(reference), "current_rows": len(current)},
    )

    try:
        Report, DataDriftPreset = _load_report_classes()
        report = Report(metrics=[DataDriftPreset()])
        report.run(reference_data=reference, current_data=current)

        out_dir = os.path.join("docs", "drift")
        os.makedirs(out_dir, exist_ok=True)
        html_path = os.path.join(out_dir, "drift_report.html")
        json_path = os.path.join(out_dir, "drift_summary.json")

        report.save_html(html_path)
        with open(json_path, "w", encoding="utf-8") as f:
            f.write(report.json())

        logger.info(
            "drift_report_written",
            extra={"html_path": html_path, "json_path": json_path},
        )
    except Exception:  # noqa: BLE001 -- monitoring is best-effort, never fatal
        logger.exception("drift_report_failed_non_fatal")


if __name__ == "__main__":
    main()
