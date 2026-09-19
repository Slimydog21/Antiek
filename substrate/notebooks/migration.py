"""Idempotent migration to owner-composite notebook storage."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from typing import Any

from .authority import LOCAL_OPERATOR_ACCOUNT, notebook_account_digest
from .tiptap_codec import compose

EMPTY_DOCUMENT = {"type": "doc", "content": []}


def canonical_document_sha256(document: dict[str, Any]) -> str:
    canonical = json.dumps(
        document,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


EMPTY_DOCUMENT_SHA256 = canonical_document_sha256(EMPTY_DOCUMENT)
OPERATOR_ACCOUNT_DIGEST = notebook_account_digest(LOCAL_OPERATOR_ACCOUNT)


NOTEBOOK_AUTHORITY_SCHEMA_SQL = f"""
CREATE TABLE IF NOT EXISTS notebooks (
    account_digest       TEXT NOT NULL DEFAULT '{OPERATOR_ACCOUNT_DIGEST}'
        CHECK (length(account_digest) = 64),
    notebook_id          TEXT NOT NULL,
    title                TEXT NOT NULL,
    investigation_id     TEXT,
    investigation_digest TEXT,
    document_id          TEXT,
    owner_user_id        TEXT NOT NULL DEFAULT '{LOCAL_OPERATOR_ACCOUNT}',
    content_class        TEXT NOT NULL DEFAULT 'user_owned'
        CHECK (content_class IN ('user_owned', 'user_public_contribution')),
    schema_version       INTEGER NOT NULL DEFAULT 1 CHECK (schema_version = 1),
    revision             BIGINT NOT NULL DEFAULT 0 CHECK (revision >= 0),
    content_sha256       TEXT NOT NULL DEFAULT '{EMPTY_DOCUMENT_SHA256}'
        CHECK (length(content_sha256) = 64),
    created_at           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    metadata             TEXT,
    PRIMARY KEY (account_digest, notebook_id)
);

CREATE TABLE IF NOT EXISTS notebook_blocks (
    account_digest       TEXT NOT NULL DEFAULT '{OPERATOR_ACCOUNT_DIGEST}'
        CHECK (length(account_digest) = 64),
    block_id             TEXT NOT NULL,
    notebook_id          TEXT NOT NULL,
    block_index          INTEGER NOT NULL,
    block_type           TEXT NOT NULL
        CHECK (block_type IN (
            'prose', 'region_embed', 'claim_card', 'note', 'question_card',
            'cross_doc_link', 'chat_exchange', 'master_md_section', 'image', 'latex'
        )),
    ref_id               TEXT,
    content_json         TEXT NOT NULL,
    created_at           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (account_digest, notebook_id, block_id),
    UNIQUE (account_digest, notebook_id, block_index)
);

CREATE TABLE IF NOT EXISTS notebook_mutation_receipts (
    account_digest       TEXT NOT NULL CHECK (length(account_digest) = 64),
    notebook_id          TEXT NOT NULL,
    mutation_key         TEXT NOT NULL,
    request_sha256       TEXT NOT NULL CHECK (length(request_sha256) = 64),
    revision             BIGINT NOT NULL CHECK (revision >= 0),
    content_sha256       TEXT NOT NULL CHECK (length(content_sha256) = 64),
    created_at           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (account_digest, notebook_id, mutation_key)
);

CREATE INDEX IF NOT EXISTS idx_notebooks_investigation
    ON notebooks(account_digest, investigation_id);
CREATE INDEX IF NOT EXISTS idx_notebooks_document
    ON notebooks(account_digest, document_id);
CREATE INDEX IF NOT EXISTS idx_notebook_blocks_notebook
    ON notebook_blocks(account_digest, notebook_id, block_index);
"""


def _columns(con: Any, table: str) -> list[tuple[Any, ...]]:
    return con.execute(f"PRAGMA table_info('{table}')").fetchall()


def _is_current(con: Any) -> bool:
    notebook_info = _columns(con, "notebooks")
    block_info = _columns(con, "notebook_blocks")
    notebook_columns = {str(row[1]) for row in notebook_info}
    block_columns = {str(row[1]) for row in block_info}
    notebook_pk = [str(row[1]) for row in notebook_info if bool(row[5])]
    block_pk = [str(row[1]) for row in block_info if bool(row[5])]
    return (
        {"account_digest", "revision", "content_sha256", "schema_version"}
        <= notebook_columns
        and "account_digest" in block_columns
        and notebook_pk == ["account_digest", "notebook_id"]
        and block_pk == ["account_digest", "block_id", "notebook_id"]
    )


def _legacy_content_hash(blocks: list[tuple[Any, ...]]) -> str:
    parsed: list[dict[str, Any]] = []
    try:
        for block in blocks:
            content = json.loads(block[5]) if isinstance(block[5], str) else block[5]
            if not isinstance(content, dict):
                raise ValueError("legacy notebook block content is invalid")
            parsed.append({"content_json": content})
    except (TypeError, ValueError, json.JSONDecodeError):
        raw = json.dumps(blocks, default=str, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return canonical_document_sha256(compose(parsed))


def migrate_notebook_authority_schema(con: Any) -> None:
    """Rebuild legacy globally keyed rows as composite owner-qualified rows."""

    if _is_current(con):
        con.execute(NOTEBOOK_AUTHORITY_SCHEMA_SQL)
        return

    notebook_columns = {str(row[1]) for row in _columns(con, "notebooks")}
    block_rows = con.execute(
        "SELECT block_id, notebook_id, block_index, block_type, ref_id, "
        "content_json, created_at FROM notebook_blocks ORDER BY notebook_id, block_index"
    ).fetchall()
    blocks_by_notebook: dict[str, list[tuple[Any, ...]]] = defaultdict(list)
    for block in block_rows:
        blocks_by_notebook[str(block[1])].append(block)

    optional = {
        "investigation_digest": "investigation_digest",
        "schema_version": "schema_version",
        "revision": "revision",
        "content_sha256": "content_sha256",
    }
    selections = [
        "notebook_id",
        "title",
        "investigation_id",
        "document_id",
        "owner_user_id",
        "content_class",
        "created_at",
        "updated_at",
        "metadata",
    ]
    selections.extend(
        column if column in notebook_columns else f"NULL AS {alias}"
        for column, alias in optional.items()
    )
    notebook_rows = con.execute(
        "SELECT " + ", ".join(selections) + " FROM notebooks ORDER BY notebook_id"
    ).fetchall()

    con.execute("BEGIN TRANSACTION")
    try:
        con.execute("DROP TABLE IF EXISTS notebook_blocks_authority_stage")
        con.execute("DROP TABLE IF EXISTS notebooks_authority_stage")
        con.execute(
            "CREATE TEMP TABLE notebooks_authority_stage AS SELECT * FROM notebooks LIMIT 0"
        )
        con.execute(
            "CREATE TEMP TABLE notebook_blocks_authority_stage AS "
            "SELECT * FROM notebook_blocks LIMIT 0"
        )
        con.execute("DROP TABLE notebook_blocks")
        con.execute("DROP TABLE notebooks")
        con.execute(NOTEBOOK_AUTHORITY_SCHEMA_SQL)

        for row in notebook_rows:
            (
                notebook_id,
                title,
                investigation_id,
                document_id,
                owner_user_id,
                content_class,
                created_at,
                updated_at,
                metadata,
                investigation_digest,
                schema_version,
                revision,
                content_sha256,
            ) = row
            owner = str(owner_user_id or LOCAL_OPERATOR_ACCOUNT)
            notebook_blocks = blocks_by_notebook.get(str(notebook_id), [])
            resolved_hash = (
                str(content_sha256)
                if isinstance(content_sha256, str) and len(content_sha256) == 64
                else _legacy_content_hash(notebook_blocks)
            )
            resolved_revision = (
                int(revision)
                if isinstance(revision, int) and revision >= 0
                else (1 if notebook_blocks else 0)
            )
            con.execute(
                "INSERT INTO notebooks (account_digest, notebook_id, title, "
                "investigation_id, investigation_digest, document_id, owner_user_id, "
                "content_class, schema_version, revision, content_sha256, created_at, "
                "updated_at, metadata) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    notebook_account_digest(owner),
                    notebook_id,
                    title,
                    investigation_id,
                    investigation_digest,
                    document_id,
                    owner,
                    content_class,
                    int(schema_version or 1),
                    resolved_revision,
                    resolved_hash,
                    created_at,
                    updated_at,
                    metadata,
                ],
            )
            for block in notebook_blocks:
                con.execute(
                    "INSERT INTO notebook_blocks (account_digest, block_id, notebook_id, "
                    "block_index, block_type, ref_id, content_json, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    [notebook_account_digest(owner), *block],
                )
        con.execute("DROP TABLE notebook_blocks_authority_stage")
        con.execute("DROP TABLE notebooks_authority_stage")
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise


__all__ = [
    "EMPTY_DOCUMENT",
    "EMPTY_DOCUMENT_SHA256",
    "NOTEBOOK_AUTHORITY_SCHEMA_SQL",
    "canonical_document_sha256",
    "migrate_notebook_authority_schema",
]
