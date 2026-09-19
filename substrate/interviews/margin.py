"""Revisioned, account-qualified plain-text operator interview margin."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

from .authority import InterviewAuthority

EMPTY_MARGIN_SHA256 = hashlib.sha256(b"").hexdigest()
MAX_MARGIN_BYTES = 1_000_000


@dataclass(frozen=True)
class InterviewMargin:
    schema_version: int
    interview_id: str
    revision: int
    content_sha256: str
    body: str
    replayed: bool = False


class MarginConflict(RuntimeError):
    def __init__(self, code: str, *, revision: int, content_sha256: str) -> None:
        super().__init__(code)
        self.code = code
        self.revision = revision
        self.content_sha256 = content_sha256


@contextmanager
def _transaction(con: Any) -> Iterator[None]:
    con.execute("BEGIN TRANSACTION")
    try:
        yield
    except BaseException:
        con.execute("ROLLBACK")
        raise
    else:
        con.execute("COMMIT")


def _parent_exists(con: Any, authority: InterviewAuthority) -> bool:
    return con.execute(
        "SELECT 1 FROM interviews_authority WHERE account_digest = ? "
        "AND owner_user_id = ? AND interview_id = ?",
        [authority.account_digest, authority.account_id, authority.interview_id],
    ).fetchone() is not None


def get_margin(con: Any, authority: InterviewAuthority) -> InterviewMargin | None:
    if not _parent_exists(con, authority):
        return None
    row = con.execute(
        "SELECT schema_version, revision, content_sha256, body FROM interview_margins "
        "WHERE account_digest = ? AND owner_user_id = ? AND interview_id = ?",
        [authority.account_digest, authority.account_id, authority.interview_id],
    ).fetchone()
    if row is None:
        return InterviewMargin(1, authority.interview_id, 0, EMPTY_MARGIN_SHA256, "")
    body = row[3]
    if not isinstance(body, str) or hashlib.sha256(body.encode()).hexdigest() != row[2]:
        raise RuntimeError("interview margin is corrupt")
    return InterviewMargin(int(row[0]), authority.interview_id, int(row[1]), str(row[2]), body)


def put_margin(con: Any, authority: InterviewAuthority, *, schema_version: int,
               base_revision: int, mutation_key: str, body: str) -> InterviewMargin | None:
    if schema_version != 1 or not isinstance(base_revision, int) or base_revision < 0:
        raise ValueError("margin version is invalid")
    if not isinstance(mutation_key, str) or not mutation_key or mutation_key != mutation_key.strip() \
            or len(mutation_key.encode()) > 200:
        raise ValueError("mutation_key is invalid")
    if not isinstance(body, str) or len(body.encode()) > MAX_MARGIN_BYTES or "\x00" in body:
        raise ValueError("margin body is invalid")
    content_sha256 = hashlib.sha256(body.encode()).hexdigest()
    request_sha256 = hashlib.sha256(json.dumps(
        {"schema_version": 1, "base_revision": base_revision,
         "mutation_key": mutation_key, "body": body},
        sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode()).hexdigest()
    with _transaction(con):
        if not _parent_exists(con, authority):
            return None
        replay = con.execute(
            "SELECT request_sha256, revision, content_sha256 FROM "
            "interview_margin_mutation_receipts WHERE account_digest = ? "
            "AND interview_id = ? AND mutation_key = ?",
            [authority.account_digest, authority.interview_id, mutation_key],
        ).fetchone()
        if replay is not None:
            if replay[0] != request_sha256:
                raise MarginConflict(
                    "mutation_key_reused", revision=int(replay[1]), content_sha256=str(replay[2])
                )
            return InterviewMargin(1, authority.interview_id, int(replay[1]), str(replay[2]), body, True)
        current = con.execute(
            "SELECT revision, content_sha256, owner_user_id FROM interview_margins WHERE account_digest = ? "
            "AND interview_id = ?",
            [authority.account_digest, authority.interview_id],
        ).fetchone()
        if current is not None and current[2] != authority.account_id:
            raise RuntimeError("interview margin authority is corrupt")
        revision = int(current[0]) if current else 0
        current_sha = str(current[1]) if current else EMPTY_MARGIN_SHA256
        if revision != base_revision:
            raise MarginConflict("stale_revision", revision=revision, content_sha256=current_sha)
        next_revision = revision + 1
        con.execute(
            "INSERT INTO interview_margins (account_digest, interview_id, owner_user_id, "
            "revision, body, content_sha256, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, CAST(CURRENT_TIMESTAMP AS TIMESTAMP)) "
            "ON CONFLICT (account_digest, interview_id) DO UPDATE SET revision = excluded.revision, "
            "body = excluded.body, content_sha256 = excluded.content_sha256, "
            "updated_at = excluded.updated_at",
            [authority.account_digest, authority.interview_id, authority.account_id,
             next_revision, body, content_sha256],
        )
        con.execute(
            "INSERT INTO interview_margin_mutation_receipts "
            "(account_digest, interview_id, mutation_key, request_sha256, revision, content_sha256) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [authority.account_digest, authority.interview_id, mutation_key, request_sha256,
             next_revision, content_sha256],
        )
    return InterviewMargin(1, authority.interview_id, next_revision, content_sha256, body)


__all__ = ["EMPTY_MARGIN_SHA256", "InterviewMargin", "MarginConflict", "get_margin", "put_margin"]
