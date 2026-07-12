# Model Card — fraud scoring `hgb_v2_20260711`

## Summary

Gradient-boosted trees (`sklearn.ensemble.HistGradientBoostingClassifier`)
scoring the probability that an online payment transaction is fraudulent.
Features are served by a Feast feature store; training data was assembled via
`get_historical_features` (point-in-time joins) against the same
`fraud_detection_v2` feature service used at serving time.

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
- Fraud-label-derived features (`fraud_rate_prior`, ...) only count transactions whose labels had matured (72h delay) at feature time.
- Post-transaction fields (`newbalanceOrig`, `newbalanceDest`) are excluded:
  a real-time scorer cannot observe them.

## Metrics (synthetic test window)

| Metric | Value |
|---|---|
| PR-AUC | 0.4912 |
| ROC-AUC | 0.6690 |
| Recall @ precision ≥ 0.90 | 0.0000 |
| Precision @ recall ≥ 0.50 | 0.7697 |
| Brier score | 0.002308 |
| Test fraud prevalence (PR-AUC floor) | 0.003383 |
| Logistic-regression baseline PR-AUC | 0.0975 |

Operating threshold (max-F1 on test): `1.000000`
(F1 = 0.6611).

## Features

Request-time: `amount`, `type_code`, `txn_hour`, `oldbalanceOrg`, `oldbalanceDest`, `amount_over_orig_balance`.

Feast online features (54): entity behavior profiles
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
