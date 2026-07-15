"""Tests for Postgres connection resolution (POSTGRES_URL vs discrete vars)."""

import pytest

from pipelines.pg_config import (
    apply_postgres_url_env,
    parse_postgres_url,
    resolve_pg_env,
)

NEON_URL = (
    "postgresql://neondb_owner:npg_Ab1%40xyz@"
    "ep-sweet-pine-123-pooler.c-2.ap-southeast-1.aws.neon.tech/neondb"
    "?sslmode=require&channel_binding=require"
)


def test_parse_neon_url_extracts_all_fields():
    out = parse_postgres_url(NEON_URL)
    assert out["POSTGRES_DB"] == "neondb"
    assert out["POSTGRES_USER"] == "neondb_owner"
    assert out["POSTGRES_PASSWORD"] == "npg_Ab1@xyz"  # %40 decoded
    assert out["POSTGRES_PORT"] == "5432"
    assert out["POSTGRES_SSLMODE"] == "require"


def test_parse_strips_neon_pooler_suffix():
    # Feast can't use Neon's pooled endpoint; host must be the direct one.
    out = parse_postgres_url(NEON_URL)
    assert "-pooler" not in out["POSTGRES_HOST"]
    assert out["POSTGRES_HOST"] == "ep-sweet-pine-123.c-2.ap-southeast-1.aws.neon.tech"


def test_parse_defaults_sslmode_require_when_absent():
    out = parse_postgres_url("postgresql://u:p@host.example.com:6543/db")
    assert out["POSTGRES_SSLMODE"] == "require"
    assert out["POSTGRES_PORT"] == "6543"


def test_non_neon_host_pooler_not_stripped():
    out = parse_postgres_url("postgresql://u:p@my-pooler.example.com/db")
    assert out["POSTGRES_HOST"] == "my-pooler.example.com"


def test_invalid_scheme_rejected():
    with pytest.raises(ValueError):
        parse_postgres_url("mysql://u:p@host/db")


def test_url_takes_precedence_over_discrete_vars():
    env = {
        "POSTGRES_URL": NEON_URL,
        "POSTGRES_HOST": "stale-local",
        "POSTGRES_DB": "stale_db",
    }
    resolved = resolve_pg_env(env)
    assert resolved["POSTGRES_HOST"].endswith(".neon.tech")
    assert resolved["POSTGRES_DB"] == "neondb"


def test_discrete_vars_used_when_no_url():
    env = {"POSTGRES_HOST": "localhost", "POSTGRES_DB": "feature_store"}
    resolved = resolve_pg_env(env)
    assert resolved["POSTGRES_HOST"] == "localhost"
    assert resolved["POSTGRES_SSLMODE"] == "disable"  # local default


def test_apply_mutates_environ_from_url():
    env = {"POSTGRES_URL": NEON_URL, "POSTGRES_HOST": "stale"}
    apply_postgres_url_env(env)
    assert env["POSTGRES_HOST"].endswith(".neon.tech")
    assert env["POSTGRES_SSLMODE"] == "require"


def test_apply_backfills_sslmode_without_url():
    env = {"POSTGRES_HOST": "localhost"}
    apply_postgres_url_env(env)
    assert env["POSTGRES_SSLMODE"] == "disable"
    assert env["POSTGRES_HOST"] == "localhost"  # unchanged
