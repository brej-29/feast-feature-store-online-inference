#!/usr/bin/env python
import logging
import os

import pandas as pd
from evidently import Report
from evidently.metric_preset import DataDriftPreset

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("feast_fraud.monitoring.drift_report")


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
        logger.warning(
            "drift_report_not_enough_rows",
            extra={"rows": len(df)},
        )
        return

    df["event_timestamp"] = pd.to_datetime(df["event_timestamp"], utc=True, errors="coerce")
    df = df.sort_values("event_timestamp")

    # Split into reference (earlier slice) and current (later slice)
    mid = len(df) // 2
    reference = df.iloc[:mid]
    current = df.iloc[mid:]

    logger.info(
        "running_data_drift_report",
        extra={
            "reference_rows": len(reference),
            "current_rows": len(current),
        },
    )

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


if __name__ == "__main__":
    main()