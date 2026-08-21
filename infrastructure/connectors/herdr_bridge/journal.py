"""Private restart journal shared by the daemon and result CLI."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import stat
from dataclasses import dataclass
from pathlib import Path

from .models import LeaseEnvelope, StructuredResult, canonical_json

DDL = """
CREATE TABLE IF NOT EXISTS bridge_attempts (
  lease_id TEXT PRIMARY KEY,
  work_id TEXT NOT NULL,
  attempt_no INTEGER NOT NULL,
  context_sha256 TEXT NOT NULL,
  lease_json TEXT NOT NULL,
  lease_sha256 TEXT NOT NULL,
  target_observed TEXT,
  prompt_receipt_sha256 TEXT,
  prompt_agent_status TEXT,
  result_json TEXT,
  result_sha256 TEXT,
  callback_delivered INTEGER NOT NULL DEFAULT 0 CHECK(callback_delivered IN (0, 1)),
  UNIQUE(work_id, attempt_no)
);
"""


@dataclass(frozen=True, slots=True)
class JournalAttempt:
    lease: LeaseEnvelope
    target_observed: str | None
    prompt_receipt_sha256: str | None
    prompt_agent_status: str | None
    result: StructuredResult | None
    callback_delivered: bool


class BridgeJournal:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser()
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(self.path.parent, 0o700)
        if self.path.exists():
            prior = self.path.lstat()
            if not stat.S_ISREG(prior.st_mode) or prior.st_nlink != 1:
                raise PermissionError("bridge journal must be a singly linked regular file")
        self._connection = sqlite3.connect(self.path, timeout=10)
        os.chmod(self.path, 0o600)
        info = self.path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            self._connection.close()
            raise PermissionError("bridge journal must be a singly linked regular file")
        self._connection.execute("PRAGMA journal_mode=DELETE")
        self._connection.execute("PRAGMA synchronous=FULL")
        self._connection.execute(DDL)
        columns = {
            str(row[1])
            for row in self._connection.execute("PRAGMA table_info(bridge_attempts)")
        }
        if "prompt_agent_status" not in columns:
            self._connection.execute(
                "ALTER TABLE bridge_attempts ADD COLUMN prompt_agent_status TEXT"
            )
        self._connection.commit()

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> BridgeJournal:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def record_lease(self, lease: LeaseEnvelope) -> None:
        encoded = canonical_json(lease.to_dict())
        digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
        with self._connection:
            prior = self._connection.execute(
                "SELECT lease_sha256 FROM bridge_attempts WHERE lease_id=?",
                [lease.lease_id],
            ).fetchone()
            if prior is not None:
                if str(prior[0]) != digest:
                    raise ValueError("lease identity was reused with different bytes")
                return
            self._connection.execute(
                "INSERT INTO bridge_attempts (lease_id, work_id, attempt_no, "
                "context_sha256, lease_json, lease_sha256) VALUES (?, ?, ?, ?, ?, ?)",
                [
                    lease.lease_id,
                    lease.work_id,
                    lease.attempt_no,
                    lease.context_sha256,
                    encoded,
                    digest,
                ],
            )

    def record_prompt_receipt(
        self,
        lease: LeaseEnvelope,
        *,
        target: str,
        receipt_sha256: str,
        agent_status: str = "unknown",
    ) -> None:
        if len(receipt_sha256) != 64:
            raise ValueError("prompt receipt digest must be SHA-256")
        with self._connection:
            row = self._connection.execute(
                "SELECT target_observed, prompt_receipt_sha256, prompt_agent_status "
                "FROM bridge_attempts "
                "WHERE lease_id=? AND work_id=? AND attempt_no=? AND context_sha256=?",
                [lease.lease_id, lease.work_id, lease.attempt_no, lease.context_sha256],
            ).fetchone()
            if row is None:
                raise ValueError("prompt receipt does not match a journaled lease")
            if row[1] is not None:
                if (str(row[0]), str(row[1]), str(row[2])) != (
                    target,
                    receipt_sha256,
                    agent_status,
                ):
                    raise ValueError("prompt receipt conflicts with the journal")
                return
            self._connection.execute(
                "UPDATE bridge_attempts SET target_observed=?, prompt_receipt_sha256=?, "
                "prompt_agent_status=? "
                "WHERE lease_id=?",
                [target, receipt_sha256, agent_status, lease.lease_id],
            )

    def capture_result(self, result: StructuredResult) -> None:
        encoded = canonical_json(result.to_dict())
        digest = result.digest()
        with self._connection:
            row = self._connection.execute(
                "SELECT result_sha256 FROM bridge_attempts WHERE work_id=? AND lease_id=? "
                "AND attempt_no=? AND context_sha256=?",
                [
                    result.work_id,
                    result.lease_id,
                    result.attempt_no,
                    result.context_sha256,
                ],
            ).fetchone()
            if row is None:
                raise ValueError("result correlation does not match a journaled attempt")
            if row[0] is not None:
                if str(row[0]) != digest:
                    raise ValueError("attempt already contains a different result")
                return
            self._connection.execute(
                "UPDATE bridge_attempts SET result_json=?, result_sha256=? WHERE lease_id=?",
                [encoded, digest, result.lease_id],
            )

    def mark_callback_delivered(self, lease_id: str, result_sha256: str) -> None:
        with self._connection:
            changed = self._connection.execute(
                "UPDATE bridge_attempts SET callback_delivered=1 WHERE lease_id=? "
                "AND result_sha256=? AND callback_delivered=0",
                [lease_id, result_sha256],
            ).rowcount
            if changed == 0:
                row = self._connection.execute(
                    "SELECT callback_delivered, result_sha256 FROM bridge_attempts "
                    "WHERE lease_id=?",
                    [lease_id],
                ).fetchone()
                if row is None or str(row[1]) != result_sha256:
                    raise ValueError("callback receipt does not match the journal")

    def mark_lease_gone(self, lease_id: str) -> None:
        with self._connection:
            changed = self._connection.execute(
                "UPDATE bridge_attempts SET callback_delivered=1 WHERE lease_id=?",
                [lease_id],
            ).rowcount
            if changed != 1:
                raise ValueError("unknown journal lease")

    def _attempts(self, where: str) -> list[JournalAttempt]:
        rows = self._connection.execute(
            "SELECT lease_json, target_observed, prompt_receipt_sha256, "
            "prompt_agent_status, result_json, "
            f"callback_delivered FROM bridge_attempts WHERE {where} ORDER BY rowid"
        ).fetchall()
        attempts: list[JournalAttempt] = []
        for lease_json, target, receipt, agent_status, result_json, delivered in rows:
            lease = LeaseEnvelope.parse(json.loads(str(lease_json)))
            result = (
                None
                if result_json is None
                else StructuredResult.parse(json.loads(str(result_json)))
            )
            attempts.append(
                JournalAttempt(
                    lease=lease,
                    target_observed=None if target is None else str(target),
                    prompt_receipt_sha256=None if receipt is None else str(receipt),
                    prompt_agent_status=(
                        None if agent_status is None else str(agent_status)
                    ),
                    result=result,
                    callback_delivered=bool(delivered),
                )
            )
        return attempts

    def pending_attempts(self) -> list[JournalAttempt]:
        return self._attempts("callback_delivered=0")

    def pending_results(self) -> list[JournalAttempt]:
        return self._attempts("result_json IS NOT NULL AND callback_delivered=0")
