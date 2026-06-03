"""Persistent federation config store (master-spec §13.9 Phase 3).

The substrate has ONE federation config — a substrate-wide policy
that controls which partner substrates may be cited from and to.
Stored in a single-row DuckDB table; the canonical schema lives in
``substrate/graph/schema.py``.

Per master-spec §13.9 + §13.7 audit: changes to this policy are
operator-driven. The substrate publishes the current state via the
``GET /cross-graph/federation-config`` endpoint; updates flow through
the ``PUT`` endpoint.
"""

from __future__ import annotations

from typing import Any

from .federation import FederationConfig

SINGLETON_KEY: str = "default"
"""All federation config rows live under a single row keyed by this
sentinel. The store is intentionally a singleton — the master spec
has not surfaced a use case for per-tenant federation configs yet
and a single row is materially simpler to audit."""


def ensure_table(con: Any) -> None:
    """Defensive table-creation. The canonical schema lives in
    ``substrate/graph/schema.py`` and runs at boot via
    ``init_database``. Read-only connections fail this call silently."""
    try:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS federation_config (
                singleton_key TEXT PRIMARY KEY,
                allowed_partner_substrates TEXT,
                require_opt_in_for_outbound_citations BOOLEAN NOT NULL DEFAULT TRUE,
                require_attribution_for_outbound_citations BOOLEAN NOT NULL DEFAULT TRUE,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
    except Exception:
        pass


def _serialize_partners(partners: tuple[str, ...]) -> str:
    """Comma-separated; no JSON dependency, no escaping required —
    partner substrate IDs are restricted to a known character class
    by upstream validation."""
    return ",".join(p for p in partners if p)


def _deserialize_partners(raw: str | None) -> tuple[str, ...]:
    if not raw:
        return ()
    return tuple(p for p in raw.split(",") if p)


def load_config(con: Any) -> FederationConfig:
    """Read the current federation config; defaults to a strict
    posture if no row exists (no partners, both opt-in + attribution
    required)."""
    ensure_table(con)
    row = con.execute(
        "SELECT allowed_partner_substrates, "
        "require_opt_in_for_outbound_citations, "
        "require_attribution_for_outbound_citations "
        "FROM federation_config WHERE singleton_key = ?",
        [SINGLETON_KEY],
    ).fetchone()
    if row is None:
        return FederationConfig(
            allowed_partner_substrates=(),
            require_opt_in_for_outbound_citations=True,
            require_attribution_for_outbound_citations=True,
        )
    return FederationConfig(
        allowed_partner_substrates=_deserialize_partners(row[0]),
        require_opt_in_for_outbound_citations=bool(row[1]),
        require_attribution_for_outbound_citations=bool(row[2]),
    )


def save_config(con: Any, config: FederationConfig) -> None:
    """Upsert the federation config singleton. The master-spec audit
    posture requires updates to land deterministically — replacement
    semantics (delete-then-insert) keep the surface uncomplicated."""
    ensure_table(con)
    partners_str = _serialize_partners(config.allowed_partner_substrates)
    exists = con.execute(
        "SELECT 1 FROM federation_config WHERE singleton_key = ?",
        [SINGLETON_KEY],
    ).fetchone()
    if exists is None:
        con.execute(
            """
            INSERT INTO federation_config (
                singleton_key,
                allowed_partner_substrates,
                require_opt_in_for_outbound_citations,
                require_attribution_for_outbound_citations,
                updated_at
            ) VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            [
                SINGLETON_KEY,
                partners_str,
                config.require_opt_in_for_outbound_citations,
                config.require_attribution_for_outbound_citations,
            ],
        )
    else:
        con.execute(
            """
            UPDATE federation_config
            SET allowed_partner_substrates = ?,
                require_opt_in_for_outbound_citations = ?,
                require_attribution_for_outbound_citations = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE singleton_key = ?
            """,
            [
                partners_str,
                config.require_opt_in_for_outbound_citations,
                config.require_attribution_for_outbound_citations,
                SINGLETON_KEY,
            ],
        )


__all__ = [
    "SINGLETON_KEY",
    "ensure_table",
    "load_config",
    "save_config",
]
