"""Shared test fixtures.

pipelines/pg_config.py loads the developer's local .env at import time (so
the app works without exported vars). Tests must not inherit that machine's
secrets/config: an API_KEY in .env would make every unauthenticated predict
test fail with 401. Strip the relevant vars for every test; auth tests set
API_KEY explicitly via monkeypatch.
"""

import pytest


@pytest.fixture(autouse=True)
def _hermetic_env(monkeypatch):
    for var in ("API_KEY", "POSTGRES_URL"):
        monkeypatch.delenv(var, raising=False)
