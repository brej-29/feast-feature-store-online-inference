# Feature Importance Overview

This document summarizes how feature importance is computed for the
`risk_scoring_lr_v1` model.

## Computation

- The training pipeline at `pipelines/train_model.py` uses
  `sklearn.inspection.permutation_importance` on the validation split.
- The scoring metric is **average precision** (area under the precision–recall curve).
- Features are permuted independently, and the change in score is averaged over
  multiple repeats to estimate importance.

The raw results are written to:

```text
models/feature_importance.csv
```

with columns:

- `feature`
- `importance_mean`
- `importance_std`

## Interpreting importance

- Higher `importance_mean` indicates a larger contribution to model performance
  (under the chosen metric and validation slice).
- Features with very small or negative importance can be candidates for pruning
  in later iterations, but should be reviewed carefully to avoid removing
  robustness-related signals (e.g., rare but critical patterns).
- Importance is **relative**, not absolute; rankings can change when features,
  windows, or model types change.