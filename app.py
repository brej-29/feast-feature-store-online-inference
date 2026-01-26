import argparse
import hashlib
import logging
import os
from typing import Any, Dict

import gradio as gr
import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("feast_fraud.gradio")

API_BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")


def _deterministic_hash(value: str) -> str:
    """
    Hash helper aligned with the offline pipeline (see pipelines/data_ingest.py).

    Uses SHA-256 and keeps the first 16 hex characters for a compact, stable ID.
    """
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def call_predict_api(
    amount: float,
    tx_type: str,
    name_orig: str,
    name_dest: str,
    is_flagged_fraud: bool,
) -> str:
    """
    Call the FastAPI /api/predict endpoint and format the response.

    This function includes basic error handling and structured logging.
    """
    try:
        amount_value = float(amount)
    except (TypeError, ValueError):
        amount_value = 0.0

    # Map raw names into entity IDs consistent with the offline pipeline.
    customer_id = name_orig
    account_id = name_orig
    merchant_id = name_dest
    device_id = _deterministic_hash(f"{name_orig}|{name_dest}")
    geo_cell_id = _deterministic_hash(name_dest)

    payload: Dict[str, Any] = {
        "entity_ids": {
            "customer_id": customer_id,
            "merchant_id": merchant_id,
            "device_id": device_id,
            "account_id": account_id,
            "geo_cell_id": geo_cell_id,
        },
        "amount": amount_value,
        "type": tx_type,
        "isFlaggedFraud": int(bool(is_flagged_fraud)),
    }

    url = f"{API_BASE_URL}/api/predict"
    logger.info(
        "sending_prediction_request",
        extra={
            "url": url,
            "payload": payload,
        },
    )

    try:
        response = requests.post(url, json=payload, timeout=5)
        response.raise_for_status()
        data = response.json()

        proba = float(data.get("proba", 0.0))
        prediction = int(data.get("prediction", 0))
        model_version = data.get("model_version", "unknown")
        feature_service = data.get("feature_service", "risk_scoring_v1")
        latency = data.get("latency_ms", {}) or {}
        total_ms = float(latency.get("total_ms", 0.0))
        feature_ms = float(latency.get("feature_fetch_ms", 0.0))
        model_ms = float(latency.get("model_ms", 0.0))

        label = "FRAUD" if prediction == 1 else "NOT FRAUD"

        logger.info(
            "prediction_response",
            extra={
                "prediction": prediction,
                "proba": proba,
                "latency_ms": total_ms,
                "model_version": model_version,
                "feature_service": feature_service,
            },
        )

        return (
            f"Prediction: {label} (thresholded)\n"
            f"Probability: {proba:.3f}\n"
            f"Latency: {total_ms:.1f} ms "
            f"(features {feature_ms:.1f} ms, model {model_ms:.1f} ms)\n"
            f"Model: {model_version} via {feature_service}"
        )

    except requests.RequestException as exc:
        logger.exception(
            "prediction_request_failed",
            extra={"url": url},
        )
        # Surface API error message if available
        try:
            detail = response.json().get("detail") if "response" in locals() else None
        except Exception:  # noqa: BLE001
            detail = None
        if detail:
            return f"Error calling prediction API: {exc} (detail: {detail})"
        return f"Error calling prediction API: {exc}"


def build_interface() -> gr.Blocks:
    """
    Build the Gradio Blocks interface for the fraud prediction demo.
    """
    with gr.Blocks(title="Feast Fraud Feature Store – Risk Scoring") as demo:
        gr.Markdown(
            """
# Online Payments Fraud – Feature Store Demo

This UI sends requests to the FastAPI backend `/api/predict`, which:

- Fetches engineered features from Feast (multi-entity + request-time)
- Applies a trained logistic regression model (if available)
- Returns a binary prediction, probability, and latency breakdowns
"""
        )

        with gr.Row():
            with gr.Column():
                amount = gr.Number(
                    label="Amount",
                    value=100.0,
                    precision=2,
                )
                tx_type = gr.Dropdown(
                    label="Transaction Type",
                    choices=["PAYMENT", "TRANSFER", "CASH_OUT", "CASH_IN", "DEBIT"],
                    value="PAYMENT",
                )
                name_orig = gr.Textbox(
                    label="Origin Account (nameOrig)",
                    value="C123456789",
                )
                name_dest = gr.Textbox(
                    label="Destination Account (nameDest)",
                    value="M123456789",
                )
                is_flagged = gr.Checkbox(
                    label="Transaction already flagged as suspicious (isFlaggedFraud)",
                    value=False,
                )
                submit = gr.Button("Predict Fraud Risk")

            with gr.Column():
                output = gr.Textbox(
                    label="Prediction Result",
                    lines=6,
                )

        submit.click(
            fn=call_predict_api,
            inputs=[amount, tx_type, name_orig, name_dest, is_flagged],
            outputs=output,
        )

    return demo


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the Gradio UI for the Feast Fraud Feature Store demo.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=7861,
        help="Port to run the Gradio app on.",
    )
    args = parser.parse_args()

    logger.info(
        "starting_gradio_app",
        extra={"port": args.port, "api_base_url": API_BASE_URL},
    )

    interface = build_interface()
    interface.queue().launch(
        server_name="0.0.0.0",
        server_port=args.port,
        show_error=True,
    )


if __name__ == "__main__":
    try:
        main()
    except Exception:  # noqa: BLE001
        logger.exception("gradio_startup_failed")
        raise