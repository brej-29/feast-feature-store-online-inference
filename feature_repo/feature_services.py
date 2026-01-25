from feast import FeatureService

from feature_views import (
    account_profile_v1,
    customer_profile_v1,
    customer_realtime_v1,
    device_profile_v1,
    geocell_profile_v1,
    merchant_profile_v1,
)

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