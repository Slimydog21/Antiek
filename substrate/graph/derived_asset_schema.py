"""Post-V23 schema owner for safe derived-asset merge persistence."""

from __future__ import annotations

from runtime.db_lock import LockedConnection

DERIVED_ASSET_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS derived_assets (
    derived_asset_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    asset_kind TEXT NOT NULL CHECK (asset_kind IN ('document','analysis','synthesis','composite')),
    owner_user_id TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    metadata_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_derived_assets_owner ON derived_assets(owner_user_id);
CREATE INDEX IF NOT EXISTS idx_derived_assets_kind ON derived_assets(asset_kind);

CREATE TABLE IF NOT EXISTS derived_asset_revisions (
    derived_asset_id TEXT NOT NULL REFERENCES derived_assets(derived_asset_id),
    revision_id TEXT NOT NULL,
    operation_kind TEXT NOT NULL CHECK (operation_kind IN ('create','revise','restore')),
    canonical_html TEXT NOT NULL,
    canonical_byte_count BIGINT NOT NULL
        CHECK (canonical_byte_count=octet_length(encode(canonical_html))),
    content_sha256 TEXT NOT NULL CHECK (
        regexp_full_match(content_sha256,'[0-9a-f]{64}') AND content_sha256=sha256(canonical_html)
    ),
    manifest_json TEXT NOT NULL,
    manifest_sha256 TEXT NOT NULL CHECK (
        regexp_full_match(manifest_sha256,'[0-9a-f]{64}') AND manifest_sha256=sha256(manifest_json)
    ),
    sanitizer_policy TEXT NOT NULL,
    sanitizer_version TEXT NOT NULL,
    review_id TEXT NOT NULL,
    acknowledgement_version TEXT NOT NULL,
    parent_revision_id TEXT,
    restored_from_revision_id TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    metadata_json TEXT,
    PRIMARY KEY (derived_asset_id,revision_id),
    UNIQUE (revision_id),
    UNIQUE (derived_asset_id,revision_id,content_sha256),
    FOREIGN KEY (derived_asset_id,parent_revision_id)
        REFERENCES derived_asset_revisions(derived_asset_id,revision_id),
    FOREIGN KEY (derived_asset_id,restored_from_revision_id)
        REFERENCES derived_asset_revisions(derived_asset_id,revision_id),
    CHECK (
        (operation_kind='create' AND parent_revision_id IS NULL
            AND restored_from_revision_id IS NULL)
        OR (operation_kind='revise' AND parent_revision_id IS NOT NULL
            AND restored_from_revision_id IS NULL)
        OR (operation_kind='restore' AND parent_revision_id IS NOT NULL
            AND restored_from_revision_id IS NOT NULL)
    )
);
CREATE INDEX IF NOT EXISTS idx_derived_asset_revisions_asset
    ON derived_asset_revisions(derived_asset_id);
CREATE INDEX IF NOT EXISTS idx_derived_asset_revisions_parent
    ON derived_asset_revisions(parent_revision_id);

CREATE TABLE IF NOT EXISTS derived_asset_revision_members (
    derived_asset_id TEXT NOT NULL REFERENCES derived_assets(derived_asset_id),
    revision_id TEXT NOT NULL,
    member_index INTEGER NOT NULL CHECK (member_index>=0),
    projection_id TEXT NOT NULL,
    source_asset_id TEXT NOT NULL,
    source_document_id TEXT NOT NULL,
    source_sha256 TEXT NOT NULL CHECK (regexp_full_match(source_sha256,'[0-9a-f]{64}')),
    hosted_html_sha256 TEXT NOT NULL
        CHECK (regexp_full_match(hosted_html_sha256,'[0-9a-f]{64}')),
    investigation_id TEXT,
    PRIMARY KEY (derived_asset_id,revision_id,member_index),
    UNIQUE (derived_asset_id,revision_id,projection_id),
    FOREIGN KEY (derived_asset_id,revision_id)
        REFERENCES derived_asset_revisions(derived_asset_id,revision_id)
);

CREATE TABLE IF NOT EXISTS derived_asset_revision_chunks (
    derived_asset_id TEXT NOT NULL,
    revision_id TEXT NOT NULL,
    revision_content_sha256 TEXT NOT NULL CHECK (
        regexp_full_match(revision_content_sha256,'[0-9a-f]{64}')
    ),
    chunk_ordinal INTEGER NOT NULL CHECK (chunk_ordinal>=0),
    citation_id TEXT NOT NULL UNIQUE CHECK (
        regexp_full_match(citation_id,'dchunk_[0-9a-f]{64}')
    ),
    member_index INTEGER NOT NULL CHECK (member_index>=0),
    section_anchor TEXT NOT NULL,
    section_path TEXT NOT NULL,
    chunk_text TEXT NOT NULL,
    chunk_text_sha256 TEXT NOT NULL CHECK (
        regexp_full_match(chunk_text_sha256,'[0-9a-f]{64}')
        AND chunk_text_sha256=sha256(chunk_text)
    ),
    token_count INTEGER NOT NULL CHECK (token_count>=1),
    chunker_policy TEXT NOT NULL,
    chunker_version TEXT NOT NULL,
    PRIMARY KEY (derived_asset_id,revision_id,chunk_ordinal),
    FOREIGN KEY (derived_asset_id,revision_id,revision_content_sha256)
        REFERENCES derived_asset_revisions(derived_asset_id,revision_id,content_sha256),
    FOREIGN KEY (derived_asset_id,revision_id,member_index)
        REFERENCES derived_asset_revision_members(derived_asset_id,revision_id,member_index)
);
CREATE INDEX IF NOT EXISTS idx_derived_revision_chunks_revision
    ON derived_asset_revision_chunks(derived_asset_id,revision_id);

CREATE TABLE IF NOT EXISTS derived_asset_revision_indexes (
    derived_asset_id TEXT NOT NULL,
    revision_id TEXT NOT NULL,
    revision_content_sha256 TEXT NOT NULL CHECK (
        regexp_full_match(revision_content_sha256,'[0-9a-f]{64}')
    ),
    chunk_count INTEGER NOT NULL CHECK (chunk_count>=0),
    index_sha256 TEXT NOT NULL CHECK (regexp_full_match(index_sha256,'[0-9a-f]{64}')),
    chunker_policy TEXT NOT NULL,
    chunker_version TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (derived_asset_id,revision_id),
    FOREIGN KEY (derived_asset_id,revision_id,revision_content_sha256)
        REFERENCES derived_asset_revisions(derived_asset_id,revision_id,content_sha256)
);

CREATE TABLE IF NOT EXISTS derived_asset_current_revisions (
    derived_asset_id TEXT PRIMARY KEY REFERENCES derived_assets(derived_asset_id),
    current_revision_id TEXT NOT NULL,
    current_content_sha256 TEXT NOT NULL
        CHECK (regexp_full_match(current_content_sha256,'[0-9a-f]{64}')),
    generation BIGINT NOT NULL CHECK (generation>=1),
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (derived_asset_id,current_revision_id)
        REFERENCES derived_asset_revisions(derived_asset_id,revision_id),
    FOREIGN KEY (derived_asset_id,current_revision_id,current_content_sha256)
        REFERENCES derived_asset_revisions(derived_asset_id,revision_id,content_sha256)
);

CREATE TABLE IF NOT EXISTS html_projections (
    projection_id TEXT PRIMARY KEY,
    identity_json JSON NOT NULL UNIQUE,
    projection_json JSON NOT NULL
);
CREATE TABLE IF NOT EXISTS derived_asset_merge_drafts (
    draft_id TEXT PRIMARY KEY CHECK (regexp_full_match(draft_id,'drf_[0-9a-f]{32}')),
    owner_user_id TEXT NOT NULL,
    intent TEXT NOT NULL CHECK (intent IN ('create','revise')),
    target_asset_id TEXT,
    expected_parent_revision_id TEXT,
    expected_parent_sha256 TEXT,
    title TEXT NOT NULL,
    asset_kind TEXT NOT NULL CHECK (asset_kind IN ('document','analysis','synthesis','composite')),
    canonical_html TEXT NOT NULL,
    canonical_byte_count BIGINT NOT NULL
        CHECK (canonical_byte_count=octet_length(encode(canonical_html))),
    canonical_sha256 TEXT NOT NULL CHECK (
        regexp_full_match(canonical_sha256,'[0-9a-f]{64}') AND canonical_sha256=sha256(canonical_html)
    ),
    manifest_json TEXT NOT NULL,
    manifest_sha256 TEXT NOT NULL CHECK (
        regexp_full_match(manifest_sha256,'[0-9a-f]{64}') AND manifest_sha256=sha256(manifest_json)
    ),
    sanitizer_policy TEXT NOT NULL,
    sanitizer_version TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (
        (intent='create' AND target_asset_id IS NULL
            AND expected_parent_revision_id IS NULL AND expected_parent_sha256 IS NULL)
        OR (intent='revise' AND target_asset_id IS NOT NULL
            AND expected_parent_revision_id IS NOT NULL
            AND regexp_full_match(expected_parent_sha256,'[0-9a-f]{64}'))
    ),
    UNIQUE (draft_id,owner_user_id,canonical_sha256,manifest_sha256)
);
CREATE INDEX IF NOT EXISTS idx_merge_drafts_owner ON derived_asset_merge_drafts(owner_user_id);
CREATE TABLE IF NOT EXISTS derived_asset_merge_reviews (
    review_id TEXT PRIMARY KEY CHECK (regexp_full_match(review_id,'rvw_[0-9a-f]{32}')),
    draft_id TEXT NOT NULL,
    owner_user_id TEXT NOT NULL,
    canonical_sha256 TEXT NOT NULL CHECK (regexp_full_match(canonical_sha256,'[0-9a-f]{64}')),
    manifest_sha256 TEXT NOT NULL CHECK (regexp_full_match(manifest_sha256,'[0-9a-f]{64}')),
    sanitizer_policy TEXT NOT NULL,
    sanitizer_version TEXT NOT NULL,
    acknowledgement_version TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (draft_id),
    FOREIGN KEY (draft_id,owner_user_id,canonical_sha256,manifest_sha256)
        REFERENCES derived_asset_merge_drafts(
            draft_id,owner_user_id,canonical_sha256,manifest_sha256
        )
);
CREATE INDEX IF NOT EXISTS idx_merge_reviews_owner ON derived_asset_merge_reviews(owner_user_id);

CREATE TABLE IF NOT EXISTS derived_asset_merge_operations (
    operation_id TEXT NOT NULL CHECK (regexp_full_match(operation_id,'op_[0-9a-f]{32}')),
    owner_user_id TEXT NOT NULL,
    operation_kind TEXT NOT NULL CHECK (operation_kind IN ('create','revise','restore')),
    review_id TEXT,
    derived_asset_id TEXT NOT NULL CHECK (regexp_full_match(derived_asset_id,'ast_[0-9a-f]{32}')),
    selected_revision_id TEXT,
    expected_revision_id TEXT,
    expected_content_sha256 TEXT,
    expected_generation BIGINT,
    command_sha256 TEXT NOT NULL CHECK (regexp_full_match(command_sha256,'[0-9a-f]{64}')),
    result_revision_id TEXT NOT NULL CHECK (regexp_full_match(result_revision_id,'rev_[0-9a-f]{32}')),
    result_content_sha256 TEXT NOT NULL
        CHECK (regexp_full_match(result_content_sha256,'[0-9a-f]{64}')),
    result_generation BIGINT NOT NULL CHECK (result_generation>=1),
    receipt_json TEXT NOT NULL,
    receipt_sha256 TEXT NOT NULL CHECK (
        regexp_full_match(receipt_sha256,'[0-9a-f]{64}') AND receipt_sha256=sha256(receipt_json)
    ),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (owner_user_id,operation_id),
    UNIQUE (result_revision_id),
    FOREIGN KEY (derived_asset_id,result_revision_id,result_content_sha256)
        REFERENCES derived_asset_revisions(derived_asset_id,revision_id,content_sha256),
    CHECK (
        (operation_kind IN ('create','revise') AND review_id IS NOT NULL
            AND selected_revision_id IS NULL)
        OR (operation_kind='restore' AND review_id IS NULL AND selected_revision_id IS NOT NULL)
    ),
    CHECK (
        (operation_kind='create' AND expected_revision_id IS NULL
            AND expected_content_sha256 IS NULL AND expected_generation IS NULL)
        OR (operation_kind IN ('revise','restore') AND expected_revision_id IS NOT NULL
            AND regexp_full_match(expected_content_sha256,'[0-9a-f]{64}')
            AND expected_generation>=1)
    )
);
CREATE INDEX IF NOT EXISTS idx_derived_asset_merge_operations_owner
    ON derived_asset_merge_operations(owner_user_id);
CREATE TABLE IF NOT EXISTS derived_asset_merge_outbox (
    outbox_id TEXT PRIMARY KEY CHECK (regexp_full_match(outbox_id,'out_[0-9a-f]{32}')),
    owner_user_id TEXT NOT NULL,
    operation_id TEXT NOT NULL,
    event_kind TEXT NOT NULL CHECK (event_kind='derived_asset.revision_committed.v1'),
    payload_json TEXT NOT NULL,
    payload_sha256 TEXT NOT NULL CHECK (
        regexp_full_match(payload_sha256,'[0-9a-f]{64}') AND payload_sha256=sha256(payload_json)
    ),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    published_at TIMESTAMP,
    UNIQUE (owner_user_id,operation_id),
    FOREIGN KEY (owner_user_id,operation_id)
        REFERENCES derived_asset_merge_operations(owner_user_id,operation_id)
);
"""

SENTINEL_TABLES = (
    "derived_asset_current_revisions",
    "derived_asset_revision_chunks",
    "derived_asset_revision_indexes",
    "derived_asset_merge_reviews",
    "derived_asset_merge_operations",
    "derived_asset_merge_outbox",
)


def install(con: LockedConnection) -> None:
    """Install the owner-scoped merge schema after the graph's V23 blocks."""
    _repair_empty_legacy_merge_schema(con)
    con.execute(DERIVED_ASSET_SCHEMA_SQL)
    from substrate.research_artifact.derived_html_index import (
        backfill_missing_revision_indexes,
    )

    backfill_missing_revision_indexes(con)


def sentinel_is_present(con: object) -> bool:
    row = con.execute(
        "SELECT ("
        + " AND ".join(
            "EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='main' "
            f"AND table_name='{table}')"
            for table in SENTINEL_TABLES
        )
        + " AND EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='main' "
        "AND table_name='derived_asset_merge_outbox' AND column_name='owner_user_id'))"
    ).fetchone()
    return bool(row and row[0])


def _repair_empty_legacy_merge_schema(con: LockedConnection) -> None:
    tables = {
        str(row[0])
        for row in con.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema='main' "
            "AND table_name IN ('derived_asset_merge_operations','derived_asset_merge_outbox')"
        ).fetchall()
    }
    if "derived_asset_merge_operations" not in tables:
        return
    owner_column = con.execute(
        "SELECT 1 FROM information_schema.columns WHERE table_schema='main' "
        "AND table_name='derived_asset_merge_outbox' AND column_name='owner_user_id'"
    ).fetchone()
    if owner_column == (1,):
        return
    operation_count = int(
        con.execute("SELECT count(*) FROM derived_asset_merge_operations").fetchone()[0]
    )
    outbox_count = (
        int(con.execute("SELECT count(*) FROM derived_asset_merge_outbox").fetchone()[0])
        if "derived_asset_merge_outbox" in tables
        else 0
    )
    if operation_count or outbox_count:
        raise RuntimeError(
            "legacy merge ledger is populated; refusing an unverifiable owner-key migration"
        )
    if "derived_asset_merge_outbox" in tables:
        con.execute("DROP TABLE derived_asset_merge_outbox")
    con.execute("DROP TABLE derived_asset_merge_operations")
