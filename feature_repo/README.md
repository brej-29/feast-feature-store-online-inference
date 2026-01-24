# Feature Repository (Feast) – Placeholder

This directory will contain the **Feast feature repository** in later steps.

Planned contents:

- Feast project configuration (e.g., `feature_store.yaml`).
- Entity definitions for:
  - Customers / accounts (`nameOrig`)
  - Counterparties (`nameDest`)
  - Devices (`hash(nameOrig + nameDest)`)
  - Geo cells (`hash(nameDest)` or improved geo representation)
- Feature views for:
  - Transaction velocity
  - Balances and ratios
  - Counterparty interaction patterns
- Materialization scripts/jobs to populate the Postgres online store.

For Step 0, this directory exists to anchor the architecture and provide a home for future Feast configuration. No Feast-specific code is implemented yet.