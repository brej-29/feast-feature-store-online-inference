from feast import FeatureService

from feature_views import (
    account_features_fv_v1,
    account_profile_v1,
    customer_features_fv_v1,
    customer_profile_v1,
    customer_realtime_v1,
    device_features_fv_v1,
    device_profile_v1,
    geocell_features_fv_v1,
    geocell_profile_v1,
    merchant_features_fv_v1,
    merchant_profile_v1,
)
from on_demand_feature_views import transaction_request_features

# ---------------------------------------------------------------------------
# Baseline FeatureServices per entity (Step 2), retained for explorability.
# ---------------------------------------------------------------------------


customer_risk_service_v1 = FeatureService(
    name="customer_risk_service_v1",
    features=[customer_profile_v1, customer_realtime_v1],
)

merchant_risk_service_v1 = FeatureService(
    name="merchant_risk_service_v1",
    features=[merchant_profile_v1],
)

device_risk_service_v1 = FeatureService(
    name="device_risk_service_v1",
    features=[device_profile_v1],
)

account_risk_service_v1 = FeatureService(
    name="account_risk_service_v1",
    features=[account_profile_v1],
)

geocell_risk_service_v1 = FeatureService(
    name="geocell_risk_service_v1",
    features=[geocell_profile_v1],
)


# ---------------------------------------------------------------------------
# Risk-scoring FeatureServices that bundle multi-entity features + on-demand
# request-time transforms. These are used by both training and serving.
# ---------------------------------------------------------------------------


risk_scoring_v1 = FeatureService(
    name="risk_scoring_v1",
    features=[
        customer_features_fv_v1,
        merchant_features_fv_v1,
        device_features_fv_v1,
        account_features_fv_v1,
        geocell_features_fv_v1,
        customer_realtime_v1,
        transaction_request_features,
    ],
)

# Placeholder for future iterations of the model/feature set to demonstrate
# versioning. At the moment it aliases v1.
risk_scoring_v2 = FeatureService(
    name="risk_scoring_v2",
    features=[
        customer_features_fv_v1,
        merchant_features_fv_v1,
        device_features_fv_v1,
        account_features_fv_v1,
        geocell_features_fv_v1,
        customer_realtime_v1,
        transaction_request_features,
    ],
)