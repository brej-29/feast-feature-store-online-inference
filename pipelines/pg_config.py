"""Resolve Postgres connection settings from a single URL or discrete vars.

Managed Postgres providers (Neon, Supabase, Render Postgres) hand out a single
connection string, e.g.::

    postgresql://user:pass@ep-cool-name-123.us-east-2.aws.neon.tech/dbname?sslmode=require

but Feast's ``feature_store.yaml`` online store is configured from discrete
fields (host/port/database/user/password/sslmode). This module bridges the
two: if ``POSTGRES_URL`` is set it is parsed and takes precedence over any
discrete ``POSTGRES_*`` vars (which may still point at a stale local default);
otherwise the discrete vars are used as-is.

It is used from three places so every path agrees on the same connection:
- the FastAPI app and the Kafka/push helper call ``apply_postgres_url_env()``
  at startup (mutating ``os.environ`` before a ``FeatureStore`` is built);
- ``scripts/feast_apply.sh`` / ``feast_materialize.sh`` run
  ``python -m pipelines.pg_config --export`` and ``eval`` the printed
  ``export`` lines, so the Feast CLI (which reads the YAML directly) sees the
  same values.

SSL: Neon and most managed providers require SSL. When a URL is given, its
``sslmode`` query param wins; if absent we default to ``require`` (safe for
managed hosts). With no URL we default to ``disable`` (local docker-compose).
"""

import os
import shlex
from typing import Dict, Optional
from urllib.parse import parse_qs, unquote, urlparse

PG_KEYS = (
    "POSTGRES_HOST",
    "POSTGRES_PORT",
    "POSTGRES_DB",
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "POSTGRES_SSLMODE",
)


def parse_postgres_url(url: str) -> Dict[str, str]:
    """Parse a postgres(ql):// URL into discrete POSTGRES_* values.

    Percent-encoded credentials are decoded. Missing port defaults to 5432,
    missing sslmode defaults to ``require`` (managed providers need SSL).
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("postgres", "postgresql"):
        raise ValueError(
            f"POSTGRES_URL must start with postgres:// or postgresql://, got {parsed.scheme!r}"
        )

    database = parsed.path.lstrip("/") or ""
    query = parse_qs(parsed.query)
    sslmode = query.get("sslmode", ["require"])[0]

    host = parsed.hostname or ""
    # Neon's pooled endpoint (PgBouncer, transaction mode) rejects the
    # `search_path` startup parameter that Feast/psycopg send, failing the
    # connection outright ("unsupported startup parameter in options:
    # search_path"). Feast needs a direct (unpooled) connection, so strip the
    # "-pooler" suffix Neon adds to pooled hostnames. Users can paste either
    # the pooled or direct Neon string and it works.
    if host.endswith(".neon.tech") and "-pooler" in host:
        host = host.replace("-pooler", "", 1)

    out = {
        "POSTGRES_HOST": host,
        "POSTGRES_PORT": str(parsed.port or 5432),
        "POSTGRES_DB": database,
        "POSTGRES_USER": unquote(parsed.username) if parsed.username else "",
        "POSTGRES_PASSWORD": unquote(parsed.password) if parsed.password else "",
        "POSTGRES_SSLMODE": sslmode,
    }
    return out


def resolve_pg_env(environ: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """Return the POSTGRES_* values to use, preferring POSTGRES_URL when set."""
    environ = os.environ if environ is None else environ
    url = environ.get("POSTGRES_URL", "").strip()
    if url:
        return parse_postgres_url(url)

    # No URL: use discrete vars as-is, defaulting sslmode for local dev.
    resolved = {k: environ.get(k, "") for k in PG_KEYS}
    if not resolved["POSTGRES_SSLMODE"]:
        resolved["POSTGRES_SSLMODE"] = "disable"
    return resolved


def apply_postgres_url_env(environ: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """Resolve settings and write them back into the environment in-process.

    No-op (beyond ensuring POSTGRES_SSLMODE has a value) when POSTGRES_URL is
    unset, so local development using discrete vars is unaffected.
    """
    environ = os.environ if environ is None else environ
    resolved = resolve_pg_env(environ)
    if environ.get("POSTGRES_URL", "").strip():
        for key, value in resolved.items():
            environ[key] = value
    else:
        # Only backfill sslmode so the YAML's ${POSTGRES_SSLMODE} is never empty.
        environ.setdefault("POSTGRES_SSLMODE", resolved["POSTGRES_SSLMODE"])
    return resolved


def _print_exports() -> None:
    """Print `export KEY='value'` lines for `eval` in shell scripts."""
    for key, value in resolve_pg_env().items():
        print(f"export {key}={shlex.quote(value)}")


if __name__ == "__main__":
    import sys

    if "--export" in sys.argv:
        _print_exports()
    else:  # pragma: no cover - human-friendly default
        for k, v in resolve_pg_env().items():
            shown = "***" if k == "POSTGRES_PASSWORD" and v else v
            print(f"{k}={shown}")
