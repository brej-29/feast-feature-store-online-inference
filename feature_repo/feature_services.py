from feast import FeatureService
from feature_views import (
    account_profile_v2,
    customer_profile_v2,
    customer_realtime_v1,
    device_profile_v2,
    geocell_profile_v2,
    merchant_profile_v2,
)

# Single service consumed by both the training pipeline
# (get_historical_features) and the serving API (get_online_features), so the
# model sees the same feature set in both worlds by construction.
fraud_detection_v2 = FeatureService(
    name="fraud_detection_v2",
    features=[
        customer_profile_v2,
        merchant_profile_v2,
        device_profile_v2,
        account_profile_v2,
        geocell_profile_v2,
        customer_realtime_v1,
    ],
)
