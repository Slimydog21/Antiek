"""Durable, spend-free authority for recursive twin materialization."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Callable
from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path
from typing import Literal, cast

from substrate.graph.insight_question import canonical_text
from substrate.research_artifact.render import render_html
from substrate.research_artifact.schema import ResearchArtifactBody
from substrate.twin_note_taker import (
    MAX_CONTENT_CHARS,
    TWIN_AUTHORITY,
    AssetContent,
    ProposedInsight,
    ProposedQuestion,
    TwinGenerationReceipt,
    TwinProposal,
    generate_twin,
    proposal_receipt_hash,
    source_asset_receipt_hash,
)

from .segmentation import TwinSegmentationManifest, verify_segmentation_manifest
from .segmentation_completion import (
    AggregateCompletionReceiptV2,
)
from .segmentation_completion import (
    completion_digest as aggregate_completion_digest,
)
from .segmentation_completion import (
    proposal_hash as aggregate_proposal_hash,
)
from .segmentation_completion import (
    verify_receipt as verify_aggregate_receipt,
)
from .segmentation_completion_ledger import (
    PaidAggregateExport,
    SegmentationCompletionLedger,
    aggregate_body,
)
from .segmentation_ledger import TwinSegmentationLedger

State = Literal["pending_authorization", "failed", "ready"]
Verdict = Literal["unknown", "partial", "universal"]
SCHEMA_VERSION = "twin-recursion-ledger-v3"


class FailureCode(StrEnum):
    AUTHORIZATION_REFUSED = "authorization_refused"
    COMPLETION_INVALID = "completion_invalid"
    DISPATCH_UNKNOWN = "dispatch_unknown"
    OPERATOR_CANCELLED = "operator_cancelled"


class TwinLedgerError(RuntimeError):
    """Base class for durable-authority failures."""


class TwinConflictError(TwinLedgerError):
    """The caller tried to substitute bytes for an immutable identity."""


class TwinIntegrityError(TwinLedgerError):
    """Persisted canonical state no longer verifies."""


@dataclass(frozen=True)
class SourceRevision:
    account_id: str
    asset: AssetContent

    @property
    def source_hash(self) -> str:
        """Identity of the complete canonical asset revision, not only its text."""
        return _source_revision_hash(self.asset)

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.asset.content_text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class TwinSnapshot:
    account_id: str
    asset_id: str
    source_hash: str
    state: State
    twinnable: bool
    job_id: str | None
    twin_id: str | None
    binding_id: str | None
    body_json: str | None
    body_hash: str | None
    proposal_hash: str | None
    receipt_id: str | None
    failure: str | None

    @property
    def body(self) -> ResearchArtifactBody | None:
        return (
            None
            if self.body_json is None
            else ResearchArtifactBody.model_validate_json(self.body_json)
        )


@dataclass(frozen=True)
class UniversalityReport:
    account_id: str
    source_revisions: int
    twinnable_revisions: int
    bound_revisions: int
    twin_revisions: int
    pending_revisions: int
    failed_revisions: int
    verdict: Verdict

    @property
    def universal(self) -> bool:
        return self.verdict == "universal"


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _digest(kind: str, *parts: str) -> str:
    return f"{kind}_" + _sha(_canonical_json([kind, *parts]))


def _source_revision_hash(asset: AssetContent) -> str:
    """Match direct receipt identity without imposing its dispatch size ceiling."""
    if len(asset.content_text) <= MAX_CONTENT_CHARS:
        return source_asset_receipt_hash(asset)
    # Reuse every canonical metadata/event check from the direct authority;
    # only substitute a bounded prefix for its dispatch-specific body ceiling.
    source_asset_receipt_hash(
        AssetContent(
            asset.asset_id,
            asset.title,
            asset.content_text[:MAX_CONTENT_CHARS],
            asset.content_class,
            asset.source_event_ids,
        )
    )
    if (
        type(asset) is not AssetContent
        or any(
            type(value) is not str
            for value in (asset.asset_id, asset.title, asset.content_text, asset.content_class)
        )
        or type(asset.source_event_ids) is not tuple
        or any(type(value) is not str for value in asset.source_event_ids)
    ):
        raise ValueError("asset must contain exact canonical source fields")
    payload = {
        "asset_id": asset.asset_id,
        "content_class": asset.content_class,
        "source_content_hash": _sha(asset.content_text),
        "source_event_ids": list(asset.source_event_ids),
        "title": asset.title,
    }
    # source_asset_receipt_hash uses json.dumps' ASCII default. Preserve exact
    # historical identities while allowing a segmented source's full body.
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _asset_commitment_json(asset: AssetContent) -> str:
    return _canonical_json(
        {
            "asset_id": asset.asset_id,
            "title": asset.title,
            "content_class": asset.content_class,
            "source_event_ids": list(asset.source_event_ids),
            "content_hash": _sha(asset.content_text),
            "content_length": len(asset.content_text),
            "source_hash": _source_revision_hash(asset),
        }
    )


def _asset_commitment(value: str) -> dict[str, object]:
    data = json.loads(value)
    if _canonical_json(data) != value or set(data) != {
        "asset_id",
        "title",
        "content_class",
        "source_event_ids",
        "content_hash",
        "content_length",
        "source_hash",
    }:
        raise TwinIntegrityError("source commitment is not canonical")
    return cast(dict[str, object], data)


def _required_str(value: dict[str, object], key: str) -> str:
    field = value.get(key)
    if not isinstance(field, str):
        raise TwinIntegrityError(f"persisted field {key!r} is malformed")
    return field


def _receipt_from_value(value: dict[str, object]) -> TwinGenerationReceipt:
    source_event_ids = value.get("source_event_ids")
    expires_at_unix = value.get("expires_at_unix")
    if (
        not isinstance(source_event_ids, list)
        or not all(isinstance(event_id, str) for event_id in source_event_ids)
        or not isinstance(expires_at_unix, int)
    ):
        raise TwinIntegrityError("persisted receipt source events are malformed")
    return TwinGenerationReceipt(
        receipt_id=_required_str(value, "receipt_id"),
        account_id=_required_str(value, "account_id"),
        asset_id=_required_str(value, "asset_id"),
        model_id=_required_str(value, "model_id"),
        budget_authority_id=_required_str(value, "budget_authority_id"),
        source_content_hash=_required_str(value, "source_content_hash"),
        source_asset_hash=_required_str(value, "source_asset_hash"),
        source_event_ids=tuple(source_event_ids),
        proposal_payload_hash=_required_str(value, "proposal_payload_hash"),
        expires_at_unix=expires_at_unix,
        signature=_required_str(value, "signature"),
    )


def _proposal_from_value(value: dict[str, object]) -> TwinProposal:
    insights = value.get("insights")
    questions = value.get("questions")
    synthesis_excerpt = value.get("synthesis_excerpt")
    if (
        not isinstance(insights, list)
        or not all(isinstance(item, dict) for item in insights)
        or not isinstance(questions, list)
        or not all(isinstance(item, dict) for item in questions)
        or not isinstance(synthesis_excerpt, str)
    ):
        raise TwinIntegrityError("persisted proposal is malformed")
    return TwinProposal(
        tuple(
            ProposedInsight(
                text=_required_str(item, "text"),
                source_asset_id=_required_str(item, "source_asset_id"),
            )
            for item in insights
        ),
        tuple(ProposedQuestion(text=_required_str(item, "text")) for item in questions),
        synthesis_excerpt,
    )


def _expected_body(asset: AssetContent, proposal: TwinProposal) -> ResearchArtifactBody:
    def unique(values: list[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for value in values:
            clean = value.strip()
            identity = canonical_text(clean)
            if clean and identity not in seen:
                seen.add(identity)
                result.append(clean)
        return result

    insights = unique([item.text for item in proposal.insights])
    questions = unique([item.text for item in proposal.questions])
    synthesis = proposal.synthesis_excerpt.strip()
    notes = [
        f"Authority: {TWIN_AUTHORITY}. Proposals are ungrounded until evidence-backed promotion.",
        f"Source asset: {asset.asset_id}",
        *(f"Proposed insight: {value}" for value in insights),
        *(f"Proposed question: {value}" for value in questions),
    ]
    if synthesis:
        notes.append(f"Proposed synthesis: {synthesis}")
    return ResearchArtifactBody(
        investigation_id=f"twin-{asset.asset_id}",
        problem_question=f"Advisory twin notes: {asset.title or asset.asset_id}",
        synthesis_withheld=True,
        agent_notes=notes if insights or questions or synthesis else [],
    )


def _completion_json(model_id: str, proposal: TwinProposal, receipt: TwinGenerationReceipt) -> str:
    return _canonical_json(
        {"model_id": model_id, "proposal": asdict(proposal), "receipt": asdict(receipt)}
    )


def _paid_aggregate_completion_json(export: PaidAggregateExport) -> str:
    return _canonical_json(
        {
            "aggregate_binding_id": export.aggregate_binding_id,
            "aggregate_completion_digest": export.completion_digest,
            "kind": "paid_aggregate_v2",
            "manifest": json.loads(export.manifest_json),
            "model_id": export.receipt.model_id,
            "ordered_segment_bindings_hash": export.ordered_segment_bindings_hash,
            "proposal": asdict(export.proposal),
            "receipt": asdict(export.receipt),
        }
    )


TABLES = {
    "twin_ledger_meta": """CREATE TABLE twin_ledger_meta (
        singleton INTEGER PRIMARY KEY CHECK(singleton=1), schema_version TEXT NOT NULL,
        schema_digest TEXT NOT NULL)""",
    "twin_sources": """CREATE TABLE twin_sources (
        account_id TEXT NOT NULL, asset_id TEXT NOT NULL, source_hash TEXT NOT NULL,
        content_hash TEXT NOT NULL, asset_commitment_json TEXT NOT NULL, parent_binding_id TEXT,
        state TEXT NOT NULL, job_id TEXT, failure_code TEXT,
        PRIMARY KEY(account_id,asset_id,source_hash),
        CHECK(state IN ('pending_authorization','failed','ready')),
        CHECK(failure_code IS NULL OR failure_code IN
          ('authorization_refused','completion_invalid','dispatch_unknown','operator_cancelled')),
        CHECK((parent_binding_id IS NULL AND job_id IS NOT NULL) OR
          (parent_binding_id IS NOT NULL AND job_id IS NULL AND state='ready' AND failure_code IS NULL)),
        CHECK((state='failed' AND failure_code IS NOT NULL) OR
          (state!='failed' AND failure_code IS NULL)))""",
    "twin_bindings": """CREATE TABLE twin_bindings (
        binding_id TEXT PRIMARY KEY, account_id TEXT NOT NULL, asset_id TEXT NOT NULL,
        source_hash TEXT NOT NULL, job_id TEXT NOT NULL UNIQUE, twin_id TEXT NOT NULL UNIQUE,
        model_id TEXT NOT NULL, proposal_hash TEXT NOT NULL, receipt_id TEXT NOT NULL,
        completion_json TEXT NOT NULL, completion_digest TEXT NOT NULL,
        body_json TEXT NOT NULL, body_hash TEXT NOT NULL,
        UNIQUE(account_id,asset_id,source_hash),
        FOREIGN KEY(account_id,asset_id,source_hash)
          REFERENCES twin_sources(account_id,asset_id,source_hash))""",
    "twin_events": """CREATE TABLE twin_events (
        sequence INTEGER PRIMARY KEY, event_id TEXT NOT NULL UNIQUE, account_id TEXT NOT NULL,
        asset_id TEXT NOT NULL, source_hash TEXT NOT NULL, event_type TEXT NOT NULL,
        event_data TEXT NOT NULL, previous_hash TEXT NOT NULL, event_hash TEXT NOT NULL UNIQUE,
        CHECK(event_type IN ('source_registered','completion_bound','failure_recorded',
          'failure_reset','twin_registered')))""",
}

TRIGGERS = {
    "twin_meta_immutable": "CREATE TRIGGER twin_meta_immutable BEFORE UPDATE ON twin_ledger_meta BEGIN SELECT RAISE(ABORT,'immutable ledger metadata'); END",
    "twin_meta_no_delete": "CREATE TRIGGER twin_meta_no_delete BEFORE DELETE ON twin_ledger_meta BEGIN SELECT RAISE(ABORT,'immutable ledger metadata'); END",
    "twin_source_identity_immutable": """CREATE TRIGGER twin_source_identity_immutable BEFORE UPDATE OF account_id,asset_id,source_hash,content_hash,asset_commitment_json,parent_binding_id,job_id ON twin_sources BEGIN SELECT RAISE(ABORT,'immutable source revision'); END""",
    "twin_source_no_delete": "CREATE TRIGGER twin_source_no_delete BEFORE DELETE ON twin_sources BEGIN SELECT RAISE(ABORT,'immutable source revision'); END",
    "twin_source_transition": """CREATE TRIGGER twin_source_transition BEFORE UPDATE OF state,failure_code ON twin_sources WHEN NOT ((OLD.state='pending_authorization' AND NEW.state IN ('failed','ready')) OR (OLD.state='failed' AND NEW.state='pending_authorization')) BEGIN SELECT RAISE(ABORT,'invalid twin state transition'); END""",
    "twin_binding_immutable": "CREATE TRIGGER twin_binding_immutable BEFORE UPDATE ON twin_bindings BEGIN SELECT RAISE(ABORT,'immutable twin binding'); END",
    "twin_binding_no_delete": "CREATE TRIGGER twin_binding_no_delete BEFORE DELETE ON twin_bindings BEGIN SELECT RAISE(ABORT,'immutable twin binding'); END",
    "twin_event_immutable": "CREATE TRIGGER twin_event_immutable BEFORE UPDATE ON twin_events BEGIN SELECT RAISE(ABORT,'immutable twin event'); END",
    "twin_event_no_delete": "CREATE TRIGGER twin_event_no_delete BEFORE DELETE ON twin_events BEGIN SELECT RAISE(ABORT,'immutable twin event'); END",
}


def _normalize_sql(sql: str) -> str:
    return " ".join(sql.split()).lower()


def _schema_digest() -> str:
    return _sha(_canonical_json({**TABLES, **TRIGGERS}))


class TwinRecursionLedger:
    """SQLite authority; it performs no model dispatch and no paid work."""

    def __init__(
        self,
        path: str | Path,
        *,
        before_commit: Callable[[], None] | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.path = str(path)
        self._before_commit = before_commit
        self._timeout = timeout
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.path, timeout=self._timeout, isolation_level=None)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        con.execute(f"PRAGMA busy_timeout={max(0, int(self._timeout * 1000))}")
        return con

    def _initialize(self) -> None:
        con = self._connect()
        try:
            con.execute("PRAGMA journal_mode=WAL")
            con.execute("BEGIN IMMEDIATE")
            existing = con.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='twin_ledger_meta'"
            ).fetchone()
            if existing is None:
                for statement in TABLES.values():
                    con.execute(statement)
                for statement in TRIGGERS.values():
                    con.execute(statement)
                con.execute(
                    "INSERT INTO twin_ledger_meta VALUES(1,?,?)", (SCHEMA_VERSION, _schema_digest())
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
            "SELECT schema_version,schema_digest FROM twin_ledger_meta WHERE singleton=1"
        ).fetchone()
        if meta is None or tuple(meta) != (SCHEMA_VERSION, _schema_digest()):
            raise TwinIntegrityError("schema metadata pin changed")
        expected = {**TABLES, **TRIGGERS}
        rows = con.execute(
            "SELECT name,sql FROM sqlite_master WHERE name LIKE 'twin_%' AND type IN ('table','trigger')"
        ).fetchall()
        actual = {row["name"]: _normalize_sql(row["sql"]) for row in rows}
        for name, sql in expected.items():
            if actual.get(name) != _normalize_sql(sql):
                raise TwinIntegrityError(f"schema object changed: {name}")

    def _append_event(
        self,
        con: sqlite3.Connection,
        *,
        account_id: str,
        asset_id: str,
        source_hash: str,
        event_type: str,
        data: object,
    ) -> None:
        prior = con.execute(
            "SELECT sequence,event_hash FROM twin_events ORDER BY sequence DESC LIMIT 1"
        ).fetchone()
        sequence = 1 if prior is None else int(prior["sequence"]) + 1
        previous = "0" * 64 if prior is None else prior["event_hash"]
        event_data = _canonical_json(data)
        event_hash = _sha(
            _canonical_json(
                [sequence, account_id, asset_id, source_hash, event_type, event_data, previous]
            )
        )
        con.execute(
            "INSERT INTO twin_events VALUES(?,?,?,?,?,?,?,?,?)",
            (
                sequence,
                _digest("event", event_hash),
                account_id,
                asset_id,
                source_hash,
                event_type,
                event_data,
                previous,
                event_hash,
            ),
        )

    def register_source(self, revision: SourceRevision) -> TwinSnapshot:
        return self._register_source(revision, allow_oversized=False)

    def _register_source(self, revision: SourceRevision, *, allow_oversized: bool) -> TwinSnapshot:
        if type(revision) is not SourceRevision:
            raise ValueError("revision must be an exact SourceRevision")
        if len(revision.asset.content_text) > MAX_CONTENT_CHARS and not allow_oversized:
            raise ValueError("oversized sources require verified aggregate projection authority")
        asset_commitment_json = _asset_commitment_json(revision.asset)
        job_id = _digest("job", revision.account_id, revision.asset.asset_id, revision.source_hash)
        con = self._connect()
        try:
            con.execute("BEGIN IMMEDIATE")
            row = con.execute(
                "SELECT * FROM twin_sources WHERE account_id=? AND asset_id=? AND source_hash=?",
                (revision.account_id, revision.asset.asset_id, revision.source_hash),
            ).fetchone()
            if row is None:
                con.execute(
                    "INSERT INTO twin_sources VALUES(?,?,?,?,?,NULL,'pending_authorization',?,NULL)",
                    (
                        revision.account_id,
                        revision.asset.asset_id,
                        revision.source_hash,
                        revision.content_hash,
                        asset_commitment_json,
                        job_id,
                    ),
                )
                self._append_event(
                    con,
                    account_id=revision.account_id,
                    asset_id=revision.asset.asset_id,
                    source_hash=revision.source_hash,
                    event_type="source_registered",
                    data={"job_id": job_id},
                )
            elif (
                row["asset_commitment_json"] != asset_commitment_json
                or row["parent_binding_id"] is not None
            ):
                raise TwinConflictError(
                    "source revision identity already has different exact bytes"
                )
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()
        return self.get(revision.account_id, revision.asset.asset_id, revision.source_hash)

    def apply_completion(
        self,
        revision: SourceRevision,
        *,
        model_id: str,
        proposal: TwinProposal,
        receipt: TwinGenerationReceipt,
    ) -> TwinSnapshot:
        completion_json = _completion_json(model_id, proposal, receipt)
        completion_digest = _sha(completion_json)
        con = self._connect()
        try:
            con.execute("BEGIN IMMEDIATE")
            row = self._source_row(con, revision)
            if row["parent_binding_id"] is not None:
                raise TwinConflictError("materialized twins cannot recursively request twins")
            existing = con.execute(
                "SELECT * FROM twin_bindings WHERE account_id=? AND asset_id=? AND source_hash=?",
                (revision.account_id, revision.asset.asset_id, revision.source_hash),
            ).fetchone()
            if existing is not None:
                if existing["completion_digest"] != completion_digest:
                    raise TwinConflictError(
                        "completion substitution conflicts with canonical binding"
                    )
                con.commit()
                return self._snapshot(con, row)
            if row["state"] != "pending_authorization":
                raise TwinConflictError(f"source revision is {row['state']}")
            document = generate_twin(
                revision.asset,
                model_id=model_id,
                authenticated_account_id=revision.account_id,
                proposal=proposal,
                receipt=receipt,
            )
            body_json = _canonical_json(document.body.model_dump(mode="json"))
            body_hash = _sha(body_json)
            twin_id = _digest(
                "twin", revision.account_id, revision.asset.asset_id, revision.source_hash
            )
            binding_id = _digest("binding", row["job_id"], twin_id)
            proposal_hash = proposal_receipt_hash(revision.asset, proposal)
            con.execute(
                "INSERT INTO twin_bindings VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    binding_id,
                    revision.account_id,
                    revision.asset.asset_id,
                    revision.source_hash,
                    row["job_id"],
                    twin_id,
                    model_id,
                    proposal_hash,
                    receipt.receipt_id,
                    completion_json,
                    completion_digest,
                    body_json,
                    body_hash,
                ),
            )
            con.execute(
                "UPDATE twin_sources SET state='ready',failure_code=NULL WHERE account_id=? AND asset_id=? AND source_hash=?",
                (revision.account_id, revision.asset.asset_id, revision.source_hash),
            )
            self._append_event(
                con,
                account_id=revision.account_id,
                asset_id=revision.asset.asset_id,
                source_hash=revision.source_hash,
                event_type="completion_bound",
                data={"binding_id": binding_id, "completion_digest": completion_digest},
            )
            if self._before_commit is not None:
                self._before_commit()
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()
        return self.get(revision.account_id, revision.asset.asset_id, revision.source_hash)

    def apply_paid_aggregate(
        self,
        revision: SourceRevision,
        *,
        manifest: TwinSegmentationManifest,
        completions: SegmentationCompletionLedger,
        registry: TwinSegmentationLedger,
    ) -> TwinSnapshot:
        """Project one verified paid oversized parent without receipt translation."""
        if type(completions) is not SegmentationCompletionLedger:
            raise TypeError("completions must be the exact canonical completion ledger")
        if type(registry) is not TwinSegmentationLedger:
            raise TypeError("registry must be the exact canonical segmentation ledger")
        verify_segmentation_manifest(manifest, account_id=revision.account_id, asset=revision.asset)
        with completions.paid_aggregate_export(
            manifest, asset=revision.asset, registry=registry
        ) as export:
            self._validate_paid_export(revision, manifest, export)
            return self._commit_paid_aggregate(revision, export)

    @staticmethod
    def _validate_paid_export(
        revision: SourceRevision,
        manifest: TwinSegmentationManifest,
        export: PaidAggregateExport,
    ) -> None:
        if type(export) is not PaidAggregateExport:
            raise TypeError("aggregate export must be the exact canonical value")
        if type(export.receipt) is not AggregateCompletionReceiptV2:
            raise TypeError("aggregate export receipt must be paid-v2 authority")
        verify_aggregate_receipt(export.receipt, now_unix=0, require_configured_key=False)
        expected_completion = aggregate_completion_digest(export.proposal, export.receipt)
        expected_binding = "aggregate_binding_" + _sha(
            _canonical_json(
                [
                    manifest.account_id,
                    manifest.asset_id,
                    manifest.parent_source_hash,
                    export.ordered_segment_bindings_hash,
                    expected_completion,
                ]
            )
        )
        expected_body = _canonical_json(
            aggregate_body(revision.asset.asset_id, export.proposal).model_dump(mode="json")
        )
        if (
            export.account_id != revision.account_id
            or export.asset_id != revision.asset.asset_id
            or export.manifest_json != manifest.to_json()
            or export.manifest_hash != manifest.manifest_hash
            or export.parent_source_hash != manifest.parent_source_hash
            or export.receipt.account_id != revision.account_id
            or export.receipt.manifest_hash != manifest.manifest_hash
            or export.receipt.parent_source_hash != manifest.parent_source_hash
            or export.receipt.ordered_segment_bindings_hash != export.ordered_segment_bindings_hash
            or export.receipt.proposal_hash != aggregate_proposal_hash(export.proposal)
            or export.completion_digest != expected_completion
            or export.aggregate_binding_id != expected_binding
            or export.body_json != expected_body
            or export.body_hash != _sha(expected_body)
        ):
            raise TwinConflictError("paid aggregate belongs to another source authority")

    def _commit_paid_aggregate(
        self, revision: SourceRevision, export: PaidAggregateExport
    ) -> TwinSnapshot:
        self._register_source(revision, allow_oversized=True)
        completion_json = _paid_aggregate_completion_json(export)
        completion_hash = _sha(completion_json)
        proposal_hash = aggregate_proposal_hash(export.proposal)
        con = self._connect()
        try:
            con.execute("BEGIN IMMEDIATE")
            self._verify_schema(con)
            row = self._source_row(con, revision)
            if row["parent_binding_id"] is not None:
                raise TwinConflictError("materialized twins cannot recursively request twins")
            existing = con.execute(
                "SELECT * FROM twin_bindings WHERE account_id=? AND asset_id=? AND source_hash=?",
                (revision.account_id, revision.asset.asset_id, revision.source_hash),
            ).fetchone()
            if existing is not None:
                if existing["completion_digest"] != completion_hash:
                    raise TwinConflictError(
                        "completion substitution conflicts with canonical binding"
                    )
                con.commit()
                return self._snapshot(con, row)
            if row["state"] != "pending_authorization":
                raise TwinConflictError(f"source revision is {row['state']}")
            if export.body_json != _canonical_json(
                aggregate_body(revision.asset.asset_id, export.proposal).model_dump(mode="json")
            ) or export.body_hash != _sha(export.body_json):
                raise TwinIntegrityError("aggregate export body is not canonical")
            twin_id = _digest(
                "twin", revision.account_id, revision.asset.asset_id, revision.source_hash
            )
            binding_id = _digest("binding", row["job_id"], twin_id)
            con.execute(
                "INSERT INTO twin_bindings VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    binding_id,
                    revision.account_id,
                    revision.asset.asset_id,
                    revision.source_hash,
                    row["job_id"],
                    twin_id,
                    export.receipt.model_id,
                    proposal_hash,
                    export.receipt.receipt_id,
                    completion_json,
                    completion_hash,
                    export.body_json,
                    export.body_hash,
                ),
            )
            con.execute(
                "UPDATE twin_sources SET state='ready',failure_code=NULL "
                "WHERE account_id=? AND asset_id=? AND source_hash=?",
                (revision.account_id, revision.asset.asset_id, revision.source_hash),
            )
            self._append_event(
                con,
                account_id=revision.account_id,
                asset_id=revision.asset.asset_id,
                source_hash=revision.source_hash,
                event_type="completion_bound",
                data={"binding_id": binding_id, "completion_digest": completion_hash},
            )
            if self._before_commit is not None:
                self._before_commit()
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()
        return self.get(revision.account_id, revision.asset.asset_id, revision.source_hash)

    def register_materialized_twin(self, binding_id: str) -> TwinSnapshot:
        """Register the exact stored twin body as excluded from recursive generation."""
        con = self._connect()
        try:
            con.execute("BEGIN IMMEDIATE")
            binding = con.execute(
                "SELECT * FROM twin_bindings WHERE binding_id=?", (binding_id,)
            ).fetchone()
            if binding is None:
                raise TwinConflictError("parent binding does not exist")
            parent = con.execute(
                "SELECT asset_commitment_json FROM twin_sources WHERE account_id=? AND asset_id=? AND source_hash=?",
                (binding["account_id"], binding["asset_id"], binding["source_hash"]),
            ).fetchone()
            parent_commitment = _asset_commitment(parent["asset_commitment_json"])
            twin_event = "evt-twin-" + _sha(binding_id)[:32]
            asset = AssetContent(
                binding["twin_id"],
                f"Twin notes: {parent_commitment['title']}",
                binding["body_json"],
                "twin",
                (twin_event,),
            )
            revision = SourceRevision(binding["account_id"], asset)
            row = con.execute(
                "SELECT * FROM twin_sources WHERE account_id=? AND asset_id=? AND source_hash=?",
                (revision.account_id, asset.asset_id, revision.source_hash),
            ).fetchone()
            if row is None:
                con.execute(
                    "INSERT INTO twin_sources VALUES(?,?,?,?,?,?,'ready',NULL,NULL)",
                    (
                        revision.account_id,
                        asset.asset_id,
                        revision.source_hash,
                        revision.content_hash,
                        _asset_commitment_json(asset),
                        binding_id,
                    ),
                )
                self._append_event(
                    con,
                    account_id=revision.account_id,
                    asset_id=asset.asset_id,
                    source_hash=revision.source_hash,
                    event_type="twin_registered",
                    data={"parent_binding_id": binding_id},
                )
            elif (
                row["asset_commitment_json"] != _asset_commitment_json(asset)
                or row["parent_binding_id"] != binding_id
            ):
                raise TwinConflictError("twin registration conflicts with canonical binding")
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()
        return self.get(revision.account_id, asset.asset_id, revision.source_hash)

    def mark_failed(self, revision: SourceRevision, failure: FailureCode) -> TwinSnapshot:
        if type(failure) is not FailureCode:
            raise ValueError("failure must be a bounded FailureCode")
        return self._transition_failure(revision, failure.value)

    def _transition_failure(self, revision: SourceRevision, failure: str) -> TwinSnapshot:
        con = self._connect()
        try:
            con.execute("BEGIN IMMEDIATE")
            row = self._source_row(con, revision)
            if row["parent_binding_id"] is not None or row["state"] != "pending_authorization":
                raise TwinConflictError("only pending source authorization may fail")
            con.execute(
                "UPDATE twin_sources SET state='failed',failure_code=? WHERE account_id=? AND asset_id=? AND source_hash=?",
                (failure, revision.account_id, revision.asset.asset_id, revision.source_hash),
            )
            self._append_event(
                con,
                account_id=revision.account_id,
                asset_id=revision.asset.asset_id,
                source_hash=revision.source_hash,
                event_type="failure_recorded",
                data={"failure_code": failure},
            )
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()
        return self.get(revision.account_id, revision.asset.asset_id, revision.source_hash)

    def reset_failed(self, revision: SourceRevision) -> TwinSnapshot:
        con = self._connect()
        try:
            con.execute("BEGIN IMMEDIATE")
            row = self._source_row(con, revision)
            if row["state"] != "failed":
                raise TwinConflictError("only failed authorization may be reset")
            previous = row["failure_code"]
            con.execute(
                "UPDATE twin_sources SET state='pending_authorization',failure_code=NULL WHERE account_id=? AND asset_id=? AND source_hash=?",
                (revision.account_id, revision.asset.asset_id, revision.source_hash),
            )
            self._append_event(
                con,
                account_id=revision.account_id,
                asset_id=revision.asset.asset_id,
                source_hash=revision.source_hash,
                event_type="failure_reset",
                data={"previous_failure_code": previous},
            )
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()
        return self.get(revision.account_id, revision.asset.asset_id, revision.source_hash)

    def _source_row(self, con: sqlite3.Connection, revision: SourceRevision) -> sqlite3.Row:
        row = con.execute(
            "SELECT * FROM twin_sources WHERE account_id=? AND asset_id=? AND source_hash=?",
            (revision.account_id, revision.asset.asset_id, revision.source_hash),
        ).fetchone()
        if row is None:
            raise TwinConflictError("source revision is not registered")
        if row["asset_commitment_json"] != _asset_commitment_json(revision.asset):
            raise TwinConflictError("source revision exact bytes do not match registration")
        return cast(sqlite3.Row, row)

    def get(self, account_id: str, asset_id: str, source_hash: str) -> TwinSnapshot:
        with self._connect() as con:
            row = con.execute(
                "SELECT * FROM twin_sources WHERE account_id=? AND asset_id=? AND source_hash=?",
                (account_id, asset_id, source_hash),
            ).fetchone()
            if row is None:
                raise KeyError((account_id, asset_id, source_hash))
            return self._snapshot(con, row)

    def _snapshot(self, con: sqlite3.Connection, source: sqlite3.Row) -> TwinSnapshot:
        binding = con.execute(
            "SELECT * FROM twin_bindings WHERE account_id=? AND asset_id=? AND source_hash=?",
            (source["account_id"], source["asset_id"], source["source_hash"]),
        ).fetchone()
        return TwinSnapshot(
            source["account_id"],
            source["asset_id"],
            source["source_hash"],
            source["state"],
            source["parent_binding_id"] is None,
            source["job_id"],
            None if binding is None else binding["twin_id"],
            None if binding is None else binding["binding_id"],
            None if binding is None else binding["body_json"],
            None if binding is None else binding["body_hash"],
            None if binding is None else binding["proposal_hash"],
            None if binding is None else binding["receipt_id"],
            source["failure_code"],
        )

    def render_twin_html(self, binding_id: str) -> str:
        with self._connect() as con:
            row = con.execute(
                "SELECT body_json FROM twin_bindings WHERE binding_id=?", (binding_id,)
            ).fetchone()
            if row is None:
                raise KeyError(binding_id)
            return render_html(ResearchArtifactBody.model_validate_json(row["body_json"]))

    def verify_integrity(self) -> None:
        with self._connect() as con:
            if con.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise TwinIntegrityError("SQLite integrity check failed")
            self._verify_schema(con)
            previous = "0" * 64
            lifecycle: dict[tuple[str, str, str], tuple[str, str | None]] = {}
            expected_sequence = 1
            for event in con.execute("SELECT * FROM twin_events ORDER BY sequence"):
                if event["sequence"] != expected_sequence:
                    raise TwinIntegrityError("event sequence is not contiguous")
                expected = _sha(
                    _canonical_json(
                        [
                            event["sequence"],
                            event["account_id"],
                            event["asset_id"],
                            event["source_hash"],
                            event["event_type"],
                            event["event_data"],
                            previous,
                        ]
                    )
                )
                if (
                    event["previous_hash"] != previous
                    or event["event_hash"] != expected
                    or event["event_id"] != _digest("event", expected)
                ):
                    raise TwinIntegrityError("event chain mismatch")
                data = json.loads(event["event_data"])
                if _canonical_json(data) != event["event_data"]:
                    raise TwinIntegrityError("event data is not canonical")
                key = (event["account_id"], event["asset_id"], event["source_hash"])
                current = lifecycle.get(key)
                if event["event_type"] == "source_registered" and current is None:
                    lifecycle[key] = ("pending_authorization", None)
                elif event["event_type"] == "twin_registered" and current is None:
                    lifecycle[key] = ("ready", data.get("parent_binding_id"))
                elif event["event_type"] == "failure_recorded" and current == (
                    "pending_authorization",
                    None,
                ):
                    lifecycle[key] = ("failed", data.get("failure_code"))
                elif (
                    event["event_type"] == "failure_reset"
                    and current is not None
                    and current[0] == "failed"
                    and data.get("previous_failure_code") == current[1]
                ):
                    lifecycle[key] = ("pending_authorization", None)
                elif event["event_type"] == "completion_bound" and current == (
                    "pending_authorization",
                    None,
                ):
                    lifecycle[key] = ("ready", data.get("binding_id"))
                else:
                    raise TwinIntegrityError("event lifecycle transition mismatch")
                previous = expected
                expected_sequence += 1
            for source in con.execute("SELECT * FROM twin_sources"):
                commitment = _asset_commitment(source["asset_commitment_json"])
                if (
                    source["asset_id"] != commitment["asset_id"]
                    or source["source_hash"] != commitment["source_hash"]
                    or source["content_hash"] != commitment["content_hash"]
                    or type(commitment["content_length"]) is not int
                    or int(commitment["content_length"]) < 24
                    or type(commitment["source_event_ids"]) is not list
                    or not commitment["source_event_ids"]
                ):
                    raise TwinIntegrityError("source revision identity mismatch")
                binding = con.execute(
                    "SELECT * FROM twin_bindings WHERE account_id=? AND asset_id=? AND source_hash=?",
                    (source["account_id"], source["asset_id"], source["source_hash"]),
                ).fetchone()
                key = (source["account_id"], source["asset_id"], source["source_hash"])
                replayed = lifecycle.pop(key, None)
                expected_marker = (
                    source["parent_binding_id"]
                    if source["parent_binding_id"] is not None
                    else (binding["binding_id"] if binding is not None else source["failure_code"])
                )
                if replayed != (source["state"], expected_marker):
                    raise TwinIntegrityError("events do not reproduce source state")
                if source["parent_binding_id"] is not None:
                    parent = con.execute(
                        "SELECT * FROM twin_bindings WHERE binding_id=?",
                        (source["parent_binding_id"],),
                    ).fetchone()
                    if (
                        parent is None
                        or source["account_id"] != parent["account_id"]
                        or source["asset_id"] != parent["twin_id"]
                        or source["state"] != "ready"
                        or binding is not None
                    ):
                        raise TwinIntegrityError("derived twin linkage mismatch")
                    parent_source = con.execute(
                        "SELECT asset_commitment_json FROM twin_sources WHERE account_id=? AND asset_id=? AND source_hash=?",
                        (parent["account_id"], parent["asset_id"], parent["source_hash"]),
                    ).fetchone()
                    parent_commitment = _asset_commitment(parent_source["asset_commitment_json"])
                    twin_event = "evt-twin-" + _sha(parent["binding_id"])[:32]
                    expected_asset = AssetContent(
                        parent["twin_id"],
                        f"Twin notes: {parent_commitment['title']}",
                        parent["body_json"],
                        "twin",
                        (twin_event,),
                    )
                    if source["asset_commitment_json"] != _asset_commitment_json(expected_asset):
                        raise TwinIntegrityError("derived twin bytes mismatch")
                    continue
                expected_job = _digest(
                    "job", source["account_id"], source["asset_id"], source["source_hash"]
                )
                if source["job_id"] != expected_job:
                    raise TwinIntegrityError("job identity mismatch")
                if (source["state"] == "ready") != (binding is not None):
                    raise TwinIntegrityError("source state and binding disagree")
                if binding is not None:
                    body = ResearchArtifactBody.model_validate_json(binding["body_json"])
                    canonical_body = _canonical_json(body.model_dump(mode="json"))
                    twin_id = _digest(
                        "twin", source["account_id"], source["asset_id"], source["source_hash"]
                    )
                    completion_value = json.loads(binding["completion_json"])
                    proposal = _proposal_from_value(completion_value["proposal"])
                    if (
                        canonical_body != binding["body_json"]
                        or _sha(canonical_body) != binding["body_hash"]
                    ):
                        raise TwinIntegrityError("canonical body mismatch")
                    if binding["twin_id"] != twin_id or binding["binding_id"] != _digest(
                        "binding", source["job_id"], twin_id
                    ):
                        raise TwinIntegrityError("binding identity mismatch")
                    if (
                        _canonical_json(completion_value) != binding["completion_json"]
                        or _sha(binding["completion_json"]) != binding["completion_digest"]
                        or completion_value["model_id"] != binding["model_id"]
                    ):
                        raise TwinIntegrityError("completion digest mismatch")
                    if completion_value.get("kind") == "paid_aggregate_v2":
                        self._verify_paid_aggregate_binding(
                            source, commitment, binding, completion_value, proposal
                        )
                    elif set(completion_value) == {"model_id", "proposal", "receipt"}:
                        receipt = _receipt_from_value(completion_value["receipt"])
                        if (
                            receipt.receipt_id != binding["receipt_id"]
                            or receipt.account_id != source["account_id"]
                            or receipt.asset_id != source["asset_id"]
                            or receipt.model_id != binding["model_id"]
                            or receipt.source_content_hash != source["content_hash"]
                            or receipt.source_asset_hash != source["source_hash"]
                            or list(receipt.source_event_ids) != commitment["source_event_ids"]
                            or receipt.proposal_payload_hash != binding["proposal_hash"]
                        ):
                            raise TwinIntegrityError("receipt binding mismatch")
                        completion_asset = AssetContent(
                            str(commitment["asset_id"]),
                            str(commitment["title"]),
                            "x" * int(commitment["content_length"]),
                            str(commitment["content_class"]),
                            cast(tuple[str, ...], tuple(commitment["source_event_ids"])),
                        )
                        if (
                            proposal_receipt_hash(completion_asset, proposal)
                            != binding["proposal_hash"]
                            or _canonical_json(
                                _expected_body(completion_asset, proposal).model_dump(mode="json")
                            )
                            != binding["body_json"]
                        ):
                            raise TwinIntegrityError("proposal and canonical body disagree")
                    else:
                        raise TwinIntegrityError("completion provenance kind is unsupported")
            if lifecycle:
                raise TwinIntegrityError("event references an absent source revision")

    def _verify_paid_aggregate_binding(
        self,
        source: sqlite3.Row,
        commitment: dict[str, object],
        binding: sqlite3.Row,
        completion_value: dict[str, object],
        proposal: TwinProposal,
    ) -> None:
        try:
            manifest = TwinSegmentationManifest.from_json(
                _canonical_json(completion_value["manifest"])
            )
            receipt_value = completion_value["receipt"]
            if not isinstance(receipt_value, dict):
                raise TypeError("receipt is not an object")
            receipt = AggregateCompletionReceiptV2(**receipt_value)
        except (KeyError, TypeError, ValueError) as exc:
            raise TwinIntegrityError("paid aggregate provenance is malformed") from exc
        verify_aggregate_receipt(receipt, now_unix=0, require_configured_key=False)
        ordered_hash = completion_value.get("ordered_segment_bindings_hash")
        aggregate_digest = completion_value.get("aggregate_completion_digest")
        aggregate_binding_id = completion_value.get("aggregate_binding_id")
        expected_aggregate_digest = aggregate_completion_digest(proposal, receipt)
        expected_aggregate_binding = "aggregate_binding_" + _sha(
            _canonical_json(
                [
                    manifest.account_id,
                    manifest.asset_id,
                    manifest.parent_source_hash,
                    ordered_hash,
                    expected_aggregate_digest,
                ]
            )
        )
        expected_body = _canonical_json(
            aggregate_body(str(source["asset_id"]), proposal).model_dump(mode="json")
        )
        if (
            set(completion_value)
            != {
                "aggregate_binding_id",
                "aggregate_completion_digest",
                "kind",
                "manifest",
                "model_id",
                "ordered_segment_bindings_hash",
                "proposal",
                "receipt",
            }
            or manifest.account_id != source["account_id"]
            or manifest.asset_id != source["asset_id"]
            or manifest.title_sha256 != _sha(str(commitment["title"]))
            or manifest.content_class_sha256 != _sha(str(commitment["content_class"]))
            or manifest.source_events_sha256
            != _sha(_canonical_json(commitment["source_event_ids"]))
            or manifest.body_sha256 != source["content_hash"]
            or manifest.body_chars != commitment["content_length"]
            or receipt.account_id != source["account_id"]
            or receipt.manifest_hash != manifest.manifest_hash
            or receipt.parent_source_hash != manifest.parent_source_hash
            or receipt.ordered_segment_bindings_hash != ordered_hash
            or receipt.proposal_hash != aggregate_proposal_hash(proposal)
            or receipt.model_id != binding["model_id"]
            or receipt.receipt_id != binding["receipt_id"]
            or binding["proposal_hash"] != aggregate_proposal_hash(proposal)
            or aggregate_digest != expected_aggregate_digest
            or aggregate_binding_id != expected_aggregate_binding
            or binding["body_json"] != expected_body
        ):
            raise TwinIntegrityError("paid aggregate binding conflicts with source authority")

    def universality_report(self, account_id: str) -> UniversalityReport:
        with self._connect() as con:
            row = con.execute(
                """SELECT count(*) total,
                sum(parent_binding_id IS NULL) twinnable,
                sum(parent_binding_id IS NOT NULL) twins,
                sum(state='pending_authorization') pending,
                sum(state='failed') failed,
                (SELECT count(*) FROM twin_bindings WHERE account_id=?) bound
                FROM twin_sources WHERE account_id=?""",
                (account_id, account_id),
            ).fetchone()
        total, twinnable, bound = (
            int(row["total"] or 0),
            int(row["twinnable"] or 0),
            int(row["bound"] or 0),
        )
        verdict: Verdict = (
            "unknown" if twinnable == 0 else ("universal" if bound == twinnable else "partial")
        )
        return UniversalityReport(
            account_id,
            total,
            twinnable,
            bound,
            int(row["twins"] or 0),
            int(row["pending"] or 0),
            int(row["failed"] or 0),
            verdict,
        )
