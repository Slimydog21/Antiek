"""Owner authority and delivery receipts for immutable research compositions."""

from __future__ import annotations

from typing import Any

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS research_compositions (
    owner_user_id TEXT NOT NULL,
    composition_id TEXT NOT NULL CHECK (regexp_full_match(composition_id,'cmp-[0-9a-f]{64}')),
    ordered_set_digest TEXT NOT NULL CHECK (regexp_full_match(ordered_set_digest,'[0-9a-f]{64}')),
    composition_schema_version INTEGER NOT NULL CHECK (composition_schema_version = 1),
    member_count INTEGER NOT NULL CHECK (member_count BETWEEN 2 AND 20),
    composition_etag TEXT NOT NULL CHECK (
        composition_etag='"rc-v1-' || composition_id || '-' || ordered_set_digest || '"'
    ),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (owner_user_id, composition_id)
);
CREATE INDEX IF NOT EXISTS idx_research_compositions_owner_created
    ON research_compositions(owner_user_id, created_at, composition_id);

CREATE TABLE IF NOT EXISTS research_composition_members (
    owner_user_id TEXT NOT NULL,
    composition_id TEXT NOT NULL,
    member_ordinal INTEGER NOT NULL CHECK (member_ordinal >= 0),
    investigation_id TEXT NOT NULL CHECK (regexp_full_match(investigation_id,'[A-Za-z0-9][A-Za-z0-9_-]{0,127}')),
    content_hash TEXT NOT NULL CHECK (regexp_full_match(content_hash,'[0-9a-f]{64}')),
    rendered_sha256 TEXT NOT NULL CHECK (regexp_full_match(rendered_sha256,'[0-9a-f]{64}')),
    PRIMARY KEY (owner_user_id, composition_id, member_ordinal),
    UNIQUE (owner_user_id, composition_id, investigation_id),
    FOREIGN KEY (owner_user_id, composition_id)
        REFERENCES research_compositions(owner_user_id, composition_id)
);

CREATE TABLE IF NOT EXISTS research_composition_operations (
    owner_user_id TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    operation_kind TEXT NOT NULL CHECK (operation_kind = 'launch'),
    request_sha256 TEXT NOT NULL CHECK (regexp_full_match(request_sha256,'[0-9a-f]{64}')),
    state TEXT NOT NULL CHECK (state IN ('delivering', 'completed')),
    composition_id TEXT NOT NULL CHECK (regexp_full_match(composition_id,'cmp-[0-9a-f]{64}')),
    investigation_id TEXT NOT NULL CHECK (regexp_full_match(investigation_id,'inv-[0-9a-f]{12}')),
    delivery_event_json TEXT NOT NULL,
    delivery_event_sha256 TEXT NOT NULL CHECK (delivery_event_sha256=sha256(delivery_event_json)),
    delivery_lease_token TEXT,
    delivery_lease_expires_at TIMESTAMP,
    response_json TEXT,
    response_sha256 TEXT,
    completed_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (owner_user_id, idempotency_key),
    FOREIGN KEY (owner_user_id, composition_id)
        REFERENCES research_compositions(owner_user_id, composition_id),
    CHECK ((state='delivering' AND delivery_lease_token IS NOT NULL
            AND delivery_lease_expires_at IS NOT NULL AND response_json IS NULL
            AND response_sha256 IS NULL AND completed_at IS NULL)
        OR (state='completed' AND delivery_lease_token IS NOT NULL
            AND delivery_lease_expires_at IS NULL AND response_json IS NOT NULL
            AND response_sha256=sha256(response_json) AND completed_at IS NOT NULL))
);
"""


def install(connection: Any) -> None:
    connection.execute(SCHEMA_SQL)


def sentinel_is_present(connection: Any) -> bool:
    row = connection.execute(
        "SELECT count(*) = 3 FROM information_schema.tables WHERE table_schema='main' "
        "AND table_name IN ('research_compositions','research_composition_members',"
        "'research_composition_operations')"
    ).fetchone()
    return bool(row and row[0])
