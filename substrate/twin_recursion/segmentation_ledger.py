"""Hash-only durable registry for segment and parent-aggregate obligations."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from substrate.twin_note_taker import AssetContent

from .segmentation import (
    TwinSegmentationError,
    TwinSegmentationManifest,
    verify_segmentation_manifest,
)

SCHEMA_VERSION = "twin-segmentation-ledger-v1"


class TwinSegmentationIntegrityError(RuntimeError):
    """Persisted segmentation authority does not match the pinned schema."""


@dataclass(frozen=True)
class SegmentationSnapshot:
    account_id: str
    asset_id: str
    parent_source_hash: str
    manifest_hash: str
    segment_count: int
    pending_segments: int
    aggregate_state: str

    @property
    def parent_ready(self) -> bool:
        return self.aggregate_state == "ready"


TABLES = {
    "segmentation_meta": """CREATE TABLE segmentation_meta (
        singleton INTEGER PRIMARY KEY CHECK(singleton=1), schema_version TEXT NOT NULL,
        schema_digest TEXT NOT NULL)""",
    "segmentation_manifests": """CREATE TABLE segmentation_manifests (
        account_id TEXT NOT NULL, asset_id TEXT NOT NULL, parent_source_hash TEXT NOT NULL,
        manifest_hash TEXT NOT NULL, manifest_json TEXT NOT NULL,
        aggregate_obligation_id TEXT NOT NULL UNIQUE, aggregate_state TEXT NOT NULL,
        PRIMARY KEY(account_id,asset_id,parent_source_hash),
        CHECK(aggregate_state='pending'))""",
    "segmentation_obligations": """CREATE TABLE segmentation_obligations (
        account_id TEXT NOT NULL, asset_id TEXT NOT NULL, parent_source_hash TEXT NOT NULL,
        segment_index INTEGER NOT NULL, start_char INTEGER NOT NULL, end_char INTEGER NOT NULL,
        content_sha256 TEXT NOT NULL, state TEXT NOT NULL,
        PRIMARY KEY(account_id,asset_id,parent_source_hash,segment_index),
        FOREIGN KEY(account_id,asset_id,parent_source_hash)
          REFERENCES segmentation_manifests(account_id,asset_id,parent_source_hash),
        CHECK(segment_index>=0 AND start_char>=0 AND end_char>start_char),
        CHECK(state='pending'))""",
}

TRIGGERS = {
    "segmentation_meta_no_update": "CREATE TRIGGER segmentation_meta_no_update BEFORE UPDATE ON segmentation_meta BEGIN SELECT RAISE(ABORT,'immutable metadata'); END",
    "segmentation_meta_no_delete": "CREATE TRIGGER segmentation_meta_no_delete BEFORE DELETE ON segmentation_meta BEGIN SELECT RAISE(ABORT,'immutable metadata'); END",
    "segmentation_manifest_no_update": "CREATE TRIGGER segmentation_manifest_no_update BEFORE UPDATE ON segmentation_manifests BEGIN SELECT RAISE(ABORT,'immutable manifest'); END",
    "segmentation_manifest_no_delete": "CREATE TRIGGER segmentation_manifest_no_delete BEFORE DELETE ON segmentation_manifests BEGIN SELECT RAISE(ABORT,'immutable manifest'); END",
    "segmentation_obligation_no_update": "CREATE TRIGGER segmentation_obligation_no_update BEFORE UPDATE ON segmentation_obligations BEGIN SELECT RAISE(ABORT,'immutable obligation'); END",
    "segmentation_obligation_no_delete": "CREATE TRIGGER segmentation_obligation_no_delete BEFORE DELETE ON segmentation_obligations BEGIN SELECT RAISE(ABORT,'immutable obligation'); END",
}


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _schema_digest() -> str:
    return _sha(_canonical_json({**TABLES, **TRIGGERS}))


def _normalize_sql(value: str) -> str:
    return " ".join(value.split()).lower()


class TwinSegmentationLedger:
    """Registers obligations atomically; no method can claim segment or parent completion."""

    def __init__(self, path: str | Path, *, timeout: float = 30.0) -> None:
        self.path = str(path)
        self.timeout = timeout
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.path, timeout=self.timeout)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        return con

    def _initialize(self) -> None:
        con = self._connect()
        try:
            con.execute("BEGIN IMMEDIATE")
            exists = con.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='segmentation_meta'"
            ).fetchone()
            if exists is None:
                for statement in TABLES.values():
                    con.execute(statement)
                for statement in TRIGGERS.values():
                    con.execute(statement)
                con.execute(
                    "INSERT INTO segmentation_meta VALUES(1,?,?)",
                    (SCHEMA_VERSION, _schema_digest()),
                )
            self._verify_schema(con)
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()

    def _verify_schema(self, con: sqlite3.Connection) -> None:
        meta = con.execute(
            "SELECT schema_version,schema_digest FROM segmentation_meta WHERE singleton=1"
        ).fetchone()
        if meta is None or tuple(meta) != (SCHEMA_VERSION, _schema_digest()):
            raise TwinSegmentationIntegrityError("segmentation schema metadata changed")
        expected = {**TABLES, **TRIGGERS}
        rows = con.execute(
            "SELECT name,sql FROM sqlite_master WHERE name LIKE 'segmentation_%' "
            "AND type IN ('table','trigger')"
        ).fetchall()
        actual = {str(row["name"]): _normalize_sql(str(row["sql"])) for row in rows}
        for name, statement in expected.items():
            if actual.get(name) != _normalize_sql(statement):
                raise TwinSegmentationIntegrityError(f"segmentation schema object changed: {name}")

    def register(
        self, manifest: TwinSegmentationManifest, *, account_id: str, asset: AssetContent
    ) -> SegmentationSnapshot:
        verify_segmentation_manifest(manifest, account_id=account_id, asset=asset)
        manifest_json = manifest.to_json()
        TwinSegmentationManifest.from_json(manifest_json)
        con = self._connect()
        try:
            con.execute("BEGIN IMMEDIATE")
            self._verify_schema(con)
            key = (manifest.account_id, manifest.asset_id, manifest.parent_source_hash)
            row = con.execute(
                "SELECT * FROM segmentation_manifests "
                "WHERE account_id=? AND asset_id=? AND parent_source_hash=?",
                key,
            ).fetchone()
            if row is not None and row["manifest_json"] != manifest_json:
                raise TwinSegmentationIntegrityError("manifest substitution for source identity")
            if row is not None:
                self._verify_manifest_row(con, row)
            if row is None:
                con.execute(
                    "INSERT INTO segmentation_manifests VALUES(?,?,?,?,?,?,'pending')",
                    (*key, manifest.manifest_hash, manifest_json, manifest.aggregate_obligation_id),
                )
                con.executemany(
                    "INSERT INTO segmentation_obligations VALUES(?,?,?,?,?,?,?,'pending')",
                    [
                        (
                            *key,
                            segment.index,
                            segment.start_char,
                            segment.end_char,
                            segment.content_sha256,
                        )
                        for segment in manifest.segments
                    ],
                )
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()
        return self.get(*key)

    def get(self, account_id: str, asset_id: str, parent_source_hash: str) -> SegmentationSnapshot:
        with self._connect() as con:
            self._verify_schema(con)
            row = con.execute(
                "SELECT * FROM segmentation_manifests "
                "WHERE account_id=? AND asset_id=? AND parent_source_hash=?",
                (account_id, asset_id, parent_source_hash),
            ).fetchone()
            if row is None:
                raise KeyError((account_id, asset_id, parent_source_hash))
            self._verify_manifest_row(con, row)
            count = con.execute(
                "SELECT count(*),sum(state='pending') FROM segmentation_obligations "
                "WHERE account_id=? AND asset_id=? AND parent_source_hash=?",
                (account_id, asset_id, parent_source_hash),
            ).fetchone()
            return SegmentationSnapshot(
                account_id,
                asset_id,
                parent_source_hash,
                str(row["manifest_hash"]),
                int(count[0]),
                int(count[1]),
                str(row["aggregate_state"]),
            )

    def verify_integrity(self) -> None:
        with self._connect() as con:
            self._verify_schema(con)
            manifests = con.execute(
                "SELECT * FROM segmentation_manifests ORDER BY account_id,asset_id,parent_source_hash"
            ).fetchall()
            for row in manifests:
                self._verify_manifest_row(con, row)

    def _verify_manifest_row(self, con: sqlite3.Connection, row: sqlite3.Row) -> None:
        if _sha(str(row["manifest_json"])) != row["manifest_hash"]:
            raise TwinSegmentationIntegrityError("manifest digest mismatch")
        if row["aggregate_state"] != "pending":
            raise TwinSegmentationIntegrityError("aggregate state is invalid")
        try:
            manifest = TwinSegmentationManifest.from_json(str(row["manifest_json"]))
        except TwinSegmentationError as exc:
            raise TwinSegmentationIntegrityError("persisted manifest is invalid") from exc
        if (
            manifest.account_id != row["account_id"]
            or manifest.asset_id != row["asset_id"]
            or manifest.parent_source_hash != row["parent_source_hash"]
            or manifest.aggregate_obligation_id != row["aggregate_obligation_id"]
        ):
            raise TwinSegmentationIntegrityError("manifest identity conflicts with index")
        expected = [
            (item.index, item.start_char, item.end_char, item.content_sha256, "pending")
            for item in manifest.segments
        ]
        actual = [
            tuple(item)
            for item in con.execute(
                "SELECT segment_index,start_char,end_char,content_sha256,state "
                "FROM segmentation_obligations WHERE account_id=? AND asset_id=? "
                "AND parent_source_hash=? ORDER BY segment_index",
                (row["account_id"], row["asset_id"], row["parent_source_hash"]),
            ).fetchall()
        ]
        if actual != expected:
            raise TwinSegmentationIntegrityError("segment obligations conflict with manifest")


__all__ = [
    "SegmentationSnapshot",
    "TwinSegmentationIntegrityError",
    "TwinSegmentationLedger",
]
