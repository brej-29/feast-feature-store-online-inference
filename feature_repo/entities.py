from feast import Entity


customer = Entity(
    name="customer",
    join_keys=["customer_id"],
    description="Customer entity, mapped from nameOrig in the Kaggle dataset.",
)

merchant = Entity(
    name="merchant",
    join_keys=["merchant_id"],
    description="Merchant/counterparty entity, mapped from nameDest in the Kaggle dataset.",
)

device = Entity(
    name="device",
    join_keys=["device_id"],
    description="Device entity, represented as a deterministic hash of nameOrig + '|' + nameDest.",
)

account = Entity(
    name="account",
    join_keys=["account_id"],
    description="Account entity, aligned with the origin account (nameOrig).",
)

geocell = Entity(
    name="geocell",
    join_keys=["geo_cell_id"],
    description="Geo cell entity, represented as a deterministic hash of nameDest.",
)