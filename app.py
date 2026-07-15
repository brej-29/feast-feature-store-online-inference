import argparse
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
API_KEY = os.getenv("API_KEY")


def call_predict_api(
    amount: float,
    tx_type: str,
    name_orig: str,
    name_dest: str,
) -> str:
    """
    Call the FastAPI /api/predict endpoint and format the response.

    This function includes basic error handling and structured logging.
    """
    payload: Dict[str, Any] = {
        "entity_ids": {
            "nameOrig": name_orig,
            "nameDest": name_dest,
        },
        "request": {
            "amount": amount,
            "type": tx_type,
        },
    }

    url = f"{API_BASE_URL}/api/predict"
    logger.info(
        "sending_prediction_request",
        extra={"url": url, "payload": payload},
    )

    headers = {"X-API-Key": API_KEY} if API_KEY else {}

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=5)
        response.raise_for_status()
        data = response.json()

        fraud_prob = data.get("fraud_probability", 0.0)
        latency_ms = data.get("latency_ms", 0.0)
        model_version = data.get("model_version", "unknown")
        is_fraud = data.get("is_fraud", False)
        fetch_ms = data.get("feature_fetch_ms", 0.0)
        infer_ms = data.get("inference_ms", 0.0)
        degraded = (data.get("debug_info") or {}).get("degraded", False)

        logger.info(
            "prediction_response",
            extra={
                "fraud_probability": fraud_prob,
                "latency_ms": latency_ms,
                "model_version": model_version,
            },
        )

        verdict = "FRAUD ALERT" if is_fraud else "Looks legitimate"
        lines = [
            f"Verdict: {verdict}",
            f"Fraud probability: {fraud_prob:.6f}",
            f"Latency: {latency_ms:.1f} ms "
            f"(features {fetch_ms:.1f} ms + inference {infer_ms:.1f} ms)",
            f"Model version: {model_version}",
        ]
        if degraded:
            lines.append("WARNING: online feature store unavailable; scored with request-time features only.")
        return "\n".join(lines)

    except requests.RequestException as exc:
        logger.exception(
            "prediction_request_failed",
            extra={"url": url},
        )
        return f"Error calling prediction API: {exc}"


def build_interface() -> gr.Blocks:
    """
    Build the Gradio Blocks interface for the fraud prediction demo.
    """
    with gr.Blocks(title="Feast Fraud Feature Store") as demo:
        gr.Markdown(
            """
# Online Payments Fraud Detection

Real-time fraud scoring backed by a **Feast feature store**:

- `/api/predict` derives entity keys, fetches online features from the
  Feast online store (Postgres), and scores with a gradient-boosted model
  trained on point-in-time correct features
- The response shows the latency split between feature retrieval and
  model inference
- Trained on **synthetic PaySim data** — see `models/MODEL_CARD.md`
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
                    choices=["PAYMENT", "TRANSFER", "CASH_OUT", "CASH_IN"],
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
                submit = gr.Button("Predict Fraud Probability")

            with gr.Column():
                output = gr.Textbox(
                    label="Prediction Result",
                    lines=4,
                )

        submit.click(
            fn=call_predict_api,
            inputs=[amount, tx_type, name_orig, name_dest],
            outputs=output,
        )

    return demo


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the Gradio UI for the Feast Fraud Feature Store scaffold.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=7861,
        help="Port to run the Gradio app on.",
    )
    args = parser.parse_args()

    logger.info("starting_gradio_app", extra={"port": args.port, "api_base_url": API_BASE_URL})

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