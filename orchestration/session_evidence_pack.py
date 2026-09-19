"""SessionEvidencePack — typed DRW gather → Loop 1 Phase 6+ bridge (SPR-DRL-05).

The pack is the stable handoff artifact between cascade merge and Loop 1
synthesis tail. Exa / parallel web adapters fill ``chunks`` later; the schema
shape stays constant.

Rejected alternative: pipe raw ``StepEvent`` JSONL into the synthesizer —
the constraint loop expects typed evidence + parameter artifacts, not a
multiplexed step stream.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from substrate.schemas import ActionType

SCHEMA_VERSION = 4
_SUPPORTED_SCHEMA_VERSIONS = frozenset({1, 2, 3, SCHEMA_VERSION})

GatherMode = Literal["legacy", "contract_stub", "exa_reasoning", "authorized_multi_source"]


class PackDocument(BaseModel):
    """One document referenced by pack chunks — carries ``ip_holder_id`` even
    when null (substrate provenance invariant)."""

    model_config = ConfigDict(extra="forbid")

    document_id: str
    title: str
    ip_holder_id: str | None = None
    source_tier: int = Field(default=3, ge=1, le=5)


class PackChunk(BaseModel):
    """One evidence chunk with a complete provenance chain."""

    model_config = ConfigDict(extra="forbid")

    chunk_id: str
    document_id: str
    ip_holder_id: str | None = None
    text: str
    source_investigation_id: str
    sub_question: str
    inherited_unit_ids: tuple[str, ...] = Field(default=(), max_length=100)

    @model_validator(mode="after")
    def _validate_inherited_unit_ids(self) -> PackChunk:
        if len(set(self.inherited_unit_ids)) != len(self.inherited_unit_ids):
            raise ValueError("chunk inherited unit IDs must be unique")
        if any(
            not unit_id.strip()
            or unit_id != unit_id.strip()
            or len(unit_id) > 512
            for unit_id in self.inherited_unit_ids
        ):
            raise ValueError("chunk inherited unit ID is invalid")
        return self


class PackGatherSourceReceipt(BaseModel):
    """Bounded source truth. Provider receipt IDs and error prose stay out."""

    model_config = ConfigDict(extra="forbid")

    source: Literal["exa", "parallel", "arxiv", "substack"]
    status: Literal["succeeded", "failed", "skipped"]
    document_ids: tuple[str, ...] = Field(default=(), max_length=50)
    actual_cost_micros: int = Field(default=0, ge=0)
    tokens: int = Field(default=0, ge=0)
    failure_code: str | None = Field(default=None, min_length=1, max_length=128)


class PackGatherReport(BaseModel):
    """Secret-free terminal source coverage for one leaf investigation."""

    model_config = ConfigDict(extra="forbid")

    investigation_id: str = Field(min_length=1)
    launch_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    plan_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    legal_policy_snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    receipts: tuple[PackGatherSourceReceipt, ...] = Field(min_length=4, max_length=4)
    document_ids: tuple[str, ...] = Field(default=(), max_length=100)
    minimum_evidence_documents: int = Field(ge=1, le=100)
    evidence_complete: Literal[True]
    partial: bool

    @model_validator(mode="after")
    def _validate_terminal_truth(self) -> PackGatherReport:
        if tuple(receipt.source for receipt in self.receipts) != (
            "exa", "parallel", "arxiv", "substack"
        ):
            raise ValueError("gather receipts must use canonical source order")
        receipt_documents = tuple(dict.fromkeys(
            document_id
            for receipt in self.receipts
            for document_id in receipt.document_ids
        ))
        if self.document_ids != receipt_documents:
            raise ValueError("report documents must equal the ordered receipt union")
        if len(self.document_ids) < self.minimum_evidence_documents:
            raise ValueError("evidence-complete report lacks minimum document coverage")
        expected_partial = any(receipt.status != "succeeded" for receipt in self.receipts)
        if self.partial != expected_partial:
            raise ValueError("partial must match terminal source coverage")
        return self


class PackReusedUnitQualification(BaseModel):
    """One schema-v44 injected unit's secret-free inherited provenance."""

    model_config = ConfigDict(extra="forbid")

    unit_id: str = Field(min_length=1, max_length=512)
    source_investigation_id: str = Field(min_length=1, max_length=512)
    state: Literal["complete", "partial", "unknown"]
    source_successes: tuple[int, int, int, int]
    total_leaves: int = Field(ge=0, le=100)
    partial_leaf_count: int = Field(ge=0, le=100)

    @model_validator(mode="after")
    def _validate_truth(self) -> PackReusedUnitQualification:
        from substrate.source_coverage import SourceCoverageQualification

        SourceCoverageQualification(
            state=self.state,
            source_successes=self.source_successes,
            total_leaves=self.total_leaves,
            partial_leaf_count=self.partial_leaf_count,
        )
        return self


class PackLeafReuseReport(BaseModel):
    """Exactly one knowledge-reuse truth report for one authorized leaf."""

    model_config = ConfigDict(extra="forbid")

    investigation_id: str = Field(min_length=1, max_length=512)
    state: Literal[
        "not_attempted", "attempted_zero", "qualified", "legacy_unqualified"
    ]
    injected_unit_count: int = Field(ge=0, le=100)
    injected_unit_ids: tuple[str, ...] = Field(default=(), max_length=100)
    qualifications: tuple[PackReusedUnitQualification, ...] = Field(
        default=(), max_length=100
    )

    @model_validator(mode="after")
    def _validate_state(self) -> PackLeafReuseReport:
        if len(set(self.injected_unit_ids)) != len(self.injected_unit_ids):
            raise ValueError("injected reuse unit IDs must be unique")
        if self.injected_unit_ids and len(self.injected_unit_ids) != self.injected_unit_count:
            raise ValueError("injected reuse unit IDs must match injected count")
        if self.state in {"not_attempted", "attempted_zero"}:
            if self.injected_unit_count or self.injected_unit_ids or self.qualifications:
                raise ValueError(f"{self.state} cannot claim injected units")
        elif self.state == "legacy_unqualified":
            if self.injected_unit_count == 0 or self.qualifications:
                raise ValueError("legacy unqualified reuse requires an unqualified injection")
        elif (
            self.injected_unit_count == 0
            or len(self.qualifications) != self.injected_unit_count
        ):
            raise ValueError("qualified reuse requires one qualification per injected unit")
        unit_ids = [item.unit_id for item in self.qualifications]
        if len(set(unit_ids)) != len(unit_ids):
            raise ValueError("reuse qualification unit IDs must be unique")
        if self.injected_unit_ids and tuple(unit_ids) not in ((), self.injected_unit_ids):
            raise ValueError("reuse qualifications must match injected unit IDs")
        return self


class SessionEvidencePack(BaseModel):
    """Immutable merge artifact keyed by ``session_id``."""

    model_config = ConfigDict(extra="forbid")

    schema_version: int = SCHEMA_VERSION
    session_id: str
    problem_question: str
    chunks: list[PackChunk] = Field(default_factory=list)
    documents: list[PackDocument] = Field(default_factory=list)
    leaf_investigation_ids: list[str] = Field(default_factory=list)
    gather_mode: GatherMode = "legacy"
    gather_plan_fingerprint: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    gather_reports: list[PackGatherReport] = Field(default_factory=list)
    reuse_reports: list[PackLeafReuseReport] = Field(default_factory=list)
    content_hash: str = ""

    @model_validator(mode="after")
    def _validate_provenance_and_hash(self) -> SessionEvidencePack:
        if self.schema_version not in _SUPPORTED_SCHEMA_VERSIONS:
            raise ValueError(
                f"unsupported schema_version {self.schema_version!r}; "
                f"supported={sorted(_SUPPORTED_SCHEMA_VERSIONS)}"
            )
        if self.schema_version == 1 and (
            self.gather_mode != "legacy"
            or self.gather_plan_fingerprint is not None
            or self.gather_reports
        ):
            raise ValueError("schema v1 cannot carry gather coverage")
        if self.schema_version < 3 and self.reuse_reports:
            raise ValueError("schema v1/v2 cannot carry inherited reuse")
        reuse_by_leaf = {report.investigation_id: report for report in self.reuse_reports}
        if len(reuse_by_leaf) != len(self.reuse_reports):
            raise ValueError("duplicate reuse report investigation_id")
        if self.schema_version >= 3 and set(reuse_by_leaf) != set(
            self.leaf_investigation_ids
        ):
            raise ValueError("schema v3+ requires exactly one reuse report per leaf")
        report_by_leaf = {report.investigation_id: report for report in self.gather_reports}
        if len(report_by_leaf) != len(self.gather_reports):
            raise ValueError("duplicate gather report investigation_id")
        if self.gather_mode == "authorized_multi_source":
            if self.schema_version < 2 or self.gather_plan_fingerprint is None:
                raise ValueError("multi-source pack requires v2+ launch fingerprint")
            if set(report_by_leaf) != set(self.leaf_investigation_ids):
                raise ValueError("multi-source pack requires exactly one report per leaf")
            if any(
                report.launch_fingerprint != self.gather_plan_fingerprint
                for report in self.gather_reports
            ):
                raise ValueError("gather report launch fingerprint does not match launch")
        elif self.gather_reports or self.gather_plan_fingerprint is not None:
            raise ValueError("non-multi-source pack cannot carry gather reports")

        doc_by_id = {d.document_id: d for d in self.documents}
        if len(doc_by_id) != len(self.documents):
            raise ValueError("duplicate document_id in documents")
        chunk_ids = [chunk.chunk_id for chunk in self.chunks]
        if len(set(chunk_ids)) != len(chunk_ids):
            raise ValueError("duplicate chunk_id in chunks")
        for chunk in self.chunks:
            doc = doc_by_id.get(chunk.document_id)
            if doc is None:
                raise ValueError(
                    f"chunk {chunk.chunk_id!r} references unknown "
                    f"document {chunk.document_id!r}"
                )
            chunk_ip = chunk.ip_holder_id
            doc_ip = doc.ip_holder_id
            if chunk_ip != doc_ip:
                raise ValueError(
                    f"chunk {chunk.chunk_id!r} ip_holder_id {chunk_ip!r} "
                    f"!= document {chunk.document_id!r} ip_holder_id {doc_ip!r}"
                )
            if self.schema_version < 4 and chunk.inherited_unit_ids:
                raise ValueError("schema v1-v3 cannot carry claim support lineage")
            if chunk.inherited_unit_ids:
                reuse_report = reuse_by_leaf.get(chunk.source_investigation_id)
                if reuse_report is None:
                    raise ValueError("chunk inherited citations lack a leaf reuse report")
                allowed_units = set(reuse_report.injected_unit_ids) or {
                    item.unit_id for item in reuse_report.qualifications
                }
                if any(unit_id not in allowed_units for unit_id in chunk.inherited_unit_ids):
                    raise ValueError("chunk cites an unavailable inherited unit")
        report_document_ids = {
            document_id
            for report in self.gather_reports
            for document_id in report.document_ids
        }
        if self.gather_mode == "authorized_multi_source" and report_document_ids != set(
            doc_by_id
        ):
            raise ValueError("gather report documents must exactly match evidence pack")
        expected = compute_content_hash(
            session_id=self.session_id,
            problem_question=self.problem_question,
            chunks=self.chunks,
            documents=self.documents,
            leaf_investigation_ids=self.leaf_investigation_ids,
            schema_version=self.schema_version,
            gather_mode=self.gather_mode,
            gather_plan_fingerprint=self.gather_plan_fingerprint,
            gather_reports=self.gather_reports,
            reuse_reports=self.reuse_reports,
        )
        if self.content_hash and self.content_hash != expected:
            raise ValueError(
                f"content_hash mismatch: got {self.content_hash!r}, "
                f"expected {expected!r}"
            )
        if not self.content_hash:
            object.__setattr__(self, "content_hash", expected)
        return self


class SessionEvidencePackError(ValueError):
    """Raised when a pack cannot be built or validated."""


def compute_content_hash(
    *,
    session_id: str,
    problem_question: str,
    chunks: Sequence[PackChunk],
    documents: Sequence[PackDocument],
    leaf_investigation_ids: Sequence[str],
    schema_version: int = SCHEMA_VERSION,
    gather_mode: GatherMode = "legacy",
    gather_plan_fingerprint: str | None = None,
    gather_reports: Sequence[PackGatherReport] = (),
    reuse_reports: Sequence[PackLeafReuseReport] = (),
) -> str:
    """Deterministic SHA-256 over canonical pack body (excludes content_hash)."""
    body = {
        "schema_version": schema_version,
        "session_id": session_id,
        "problem_question": problem_question,
        "chunks": [
            c.model_dump(exclude={"inherited_unit_ids"} if schema_version < 4 else None)
            for c in sorted(chunks, key=lambda c: c.chunk_id)
        ],
        "documents": [
            d.model_dump() for d in sorted(documents, key=lambda d: d.document_id)
        ],
        "leaf_investigation_ids": sorted(leaf_investigation_ids),
    }
    if schema_version >= 2:
        body.update({
            "gather_mode": gather_mode,
            "gather_plan_fingerprint": gather_plan_fingerprint,
            "gather_reports": [
                report.model_dump(mode="json")
                for report in sorted(gather_reports, key=lambda report: report.investigation_id)
            ],
        })
    if schema_version >= 3:
        body["reuse_reports"] = [
            report.model_dump(
                mode="json",
                exclude={"injected_unit_ids"} if schema_version < 4 else None,
            )
            for report in sorted(reuse_reports, key=lambda report: report.investigation_id)
        ]
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def parse_session_evidence_pack(data: dict[str, Any]) -> SessionEvidencePack:
    """Parse + validate a pack dict. Raises ``SessionEvidencePackError``."""
    try:
        return SessionEvidencePack.model_validate(data)
    except ValidationError as exc:
        raise SessionEvidencePackError(str(exc)) from exc


def _load_problem_question(
    session_id: str,
    *,
    owner_user_id: str,
    events_dir: str,
    db_path: str,
    plan_root_node_id: str | None,
) -> str:
    from substrate.event_log import trajectory_authorized
    from substrate.investigation_tenancy import InvestigationAuthority

    session_authority = InvestigationAuthority(owner_user_id, session_id, Path(events_dir))
    import duckdb

    con = duckdb.connect(db_path, read_only=True)
    try:
        launch_row = con.execute(
            "SELECT tree_json, tree_fingerprint FROM cascade_plan_launch_authority "
            "WHERE account_digest = ? AND launch_investigation_digest = ?",
            [session_authority.account_digest, session_authority.investigation_digest],
        ).fetchone()
        if launch_row and isinstance(launch_row[0], str) and (
            hashlib.sha256(launch_row[0].encode()).hexdigest() == launch_row[1]
        ):
            document = json.loads(launch_row[0])
            question = document.get("root", {}).get("question")
            if isinstance(question, str) and question.strip():
                return question.strip()
    except (json.JSONDecodeError, AttributeError):
        pass
    finally:
        con.close()

    if plan_root_node_id:
        con = duckdb.connect(db_path, read_only=True)
        try:
            if owner_user_id == "__operator__":
                row = con.execute(
                    "SELECT canonical_label FROM nodes WHERE node_id = ?",
                    [plan_root_node_id],
                ).fetchone()
            else:
                row = con.execute(
                    "SELECT n.canonical_label FROM nodes n JOIN "
                    "investigation_node_memberships m ON m.node_id = n.node_id "
                    "WHERE n.node_id = ? AND m.account_digest = ? LIMIT 1",
                    [plan_root_node_id, session_authority.account_digest],
                ).fetchone()
            if row and row[0]:
                return str(row[0])
        finally:
            con.close()

    for ev in trajectory_authorized(
        session_authority
    ):
        if ev.get("action_type") == "cascade.launched":
            payload = ev.get("payload") or {}
            if isinstance(payload, dict):
                root = payload.get("plan_root_node_id")
                if root:
                    if str(root) == str(plan_root_node_id):
                        break
                    return _load_problem_question(
                        session_id,
                        owner_user_id=owner_user_id,
                        events_dir=events_dir,
                        db_path=db_path,
                        plan_root_node_id=str(root),
                    )
    return session_id


def _load_gather_launch(
    session_id: str, *, owner_user_id: str, events_dir: str
) -> tuple[GatherMode, str | None]:
    """Read the immutable parent launch receipt; absence proves legacy mode."""
    from substrate.event_log import trajectory_authorized
    from substrate.investigation_tenancy import InvestigationAuthority

    authority = InvestigationAuthority(owner_user_id, session_id, Path(events_dir))
    launches = [
        event for event in trajectory_authorized(authority)
        if event.get("action_type") == "cascade.launched"
    ]
    if not launches:
        return "legacy", None
    if len(launches) != 1:
        raise SessionEvidencePackError("session must have exactly one durable launch")
    payload = launches[0].get("payload") or {}
    receipt = payload.get("gather_receipt") if isinstance(payload, dict) else None
    if not isinstance(receipt, dict):
        return "legacy", None
    raw_mode = receipt.get("gather_mode")
    allowed = {"contract_stub", "exa_reasoning", "authorized_multi_source"}
    if raw_mode not in allowed:
        raise SessionEvidencePackError("durable launch has invalid gather mode")
    mode = raw_mode
    if mode != "authorized_multi_source":
        return mode, None  # type: ignore[return-value]
    reviewed = receipt.get("reviewed_gather_plan")
    fingerprint = reviewed.get("fingerprint") if isinstance(reviewed, dict) else None
    if not isinstance(fingerprint, str) or len(fingerprint) != 64:
        raise SessionEvidencePackError("multi-source launch lacks reviewed fingerprint")
    return "authorized_multi_source", fingerprint


def _load_gather_report(
    investigation_id: str,
    *,
    owner_user_id: str,
    events_dir: str,
    events: Sequence[dict[str, Any]] | None = None,
) -> PackGatherReport:
    """Load and redact the single typed leaf report used by synthesis."""
    from substrate.event_log import trajectory_authorized
    from substrate.investigation_tenancy import InvestigationAuthority
    from substrate.schemas.events import GatherReportRecordedPayload

    authority = InvestigationAuthority(owner_user_id, investigation_id, Path(events_dir))
    trajectory = events if events is not None else trajectory_authorized(authority)
    raw_reports = [
        event.get("payload")
        for event in trajectory
        if event.get("action_type") == ActionType.GATHER_REPORT_RECORDED.value
    ]
    if len(raw_reports) != 1:
        raise SessionEvidencePackError(
            f"leaf {investigation_id!r} must have exactly one gather report"
        )
    try:
        report = GatherReportRecordedPayload.model_validate(raw_reports[0])
    except ValidationError as exc:
        raise SessionEvidencePackError(
            f"leaf {investigation_id!r} has invalid gather report"
        ) from exc
    if report.unknown_outcome or not report.evidence_complete:
        raise SessionEvidencePackError(
            f"leaf {investigation_id!r} gather outcome is not synthesis-safe"
        )
    return PackGatherReport(
        investigation_id=investigation_id,
        launch_fingerprint=report.launch_fingerprint,
        plan_fingerprint=report.plan_fingerprint,
        legal_policy_snapshot_sha256=report.legal_policy_snapshot_sha256,
        receipts=tuple(
            PackGatherSourceReceipt(
                source=receipt.source,
                status=receipt.status,  # type: ignore[arg-type]
                document_ids=receipt.document_ids,
                actual_cost_micros=receipt.actual_cost_micros,
                tokens=receipt.tokens,
                failure_code=receipt.failure_code,
            )
            for receipt in report.receipts
        ),
        document_ids=report.document_ids,
        minimum_evidence_documents=report.minimum_evidence_documents,
        evidence_complete=True,
        partial=report.partial,
    )


def _load_reuse_report(
    investigation_id: str, *, events: Sequence[dict[str, Any]]
) -> PackLeafReuseReport:
    """Validate and redact the leaf's zero-or-one knowledge-reuse event."""
    from substrate.schemas.events import KnowledgeReusedPayload

    raw_events = [
        event
        for event in events
        if event.get("action_type") == ActionType.KNOWLEDGE_REUSED.value
    ]
    if not raw_events:
        return PackLeafReuseReport(
            investigation_id=investigation_id,
            state="not_attempted",
            injected_unit_count=0,
        )
    if len(raw_events) != 1:
        raise SessionEvidencePackError(
            f"leaf {investigation_id!r} must have at most one knowledge reuse event"
        )
    raw_event = raw_events[0]
    try:
        payload = KnowledgeReusedPayload.model_validate(raw_event.get("payload"))
    except ValidationError as exc:
        raise SessionEvidencePackError(
            f"leaf {investigation_id!r} has invalid knowledge reuse event"
        ) from exc
    context_event_id = payload.context_pack_event_id
    matching_context_positions = [
        index
        for index, event in enumerate(events)
        if event.get("action_type") == ActionType.CONTEXT_PACK_ASSEMBLED.value
        and event.get("event_id") == context_event_id
    ]
    reuse_position = next(
        index for index, event in enumerate(events) if event is raw_event
    )
    if (
        len(matching_context_positions) != 1
        or raw_event.get("parent_event_id") != context_event_id
        or matching_context_positions[0] >= reuse_position
    ):
        raise SessionEvidencePackError(
            f"leaf {investigation_id!r} reuse event lacks its context pack event"
        )
    injected_count = len(payload.reused_unit_ids)
    if injected_count == 0:
        return PackLeafReuseReport(
            investigation_id=investigation_id,
            state="attempted_zero",
            injected_unit_count=0,
        )
    if payload.source_qualifications is None:
        return PackLeafReuseReport(
            investigation_id=investigation_id,
            state="legacy_unqualified",
            injected_unit_count=injected_count,
            injected_unit_ids=tuple(payload.reused_unit_ids),
        )
    return PackLeafReuseReport(
        investigation_id=investigation_id,
        state="qualified",
        injected_unit_count=injected_count,
        injected_unit_ids=tuple(payload.reused_unit_ids),
        qualifications=tuple(
            PackReusedUnitQualification(
                unit_id=item.unit_id,
                source_investigation_id=item.source_investigation_id,
                state=item.state,
                source_successes=tuple(item.source_successes),  # type: ignore[arg-type]
                total_leaves=item.total_leaves,
                partial_leaf_count=item.partial_leaf_count,
            )
            for item in payload.source_qualifications
        ),
    )


def build_session_evidence_pack(
    session_id: str,
    *,
    owner_user_id: str,
    events_dir: str,
    db_path: str,
    researches: Sequence[tuple[str, str]],
    plan_root_node_id: str | None = None,
) -> SessionEvidencePack:
    """Build a pack from cascade merge state + per-leaf JSONL trajectories.

    ``researches`` is ``(investigation_id, sub_question)`` pairs for session
    members (from ``reconstruct_session`` or live ``CascadeSession.status``).
    """
    from substrate.event_log import trajectory_authorized
    from substrate.investigation_tenancy import InvestigationAuthority

    problem_question = _load_problem_question(
        session_id,
        owner_user_id=owner_user_id,
        events_dir=events_dir,
        db_path=db_path,
        plan_root_node_id=plan_root_node_id,
    )
    gather_mode, gather_plan_fingerprint = _load_gather_launch(
        session_id, owner_user_id=owner_user_id, events_dir=events_dir
    )
    trajectories = {
        iid: trajectory_authorized(
            InvestigationAuthority(owner_user_id, iid, Path(events_dir))
        )
        for iid, _ in researches
    }
    gather_reports = (
        [
            _load_gather_report(
                iid,
                owner_user_id=owner_user_id,
                events_dir=events_dir,
                events=trajectories[iid],
            )
            for iid, _ in researches
        ]
        if gather_mode == "authorized_multi_source"
        else []
    )
    reuse_reports = [
        _load_reuse_report(iid, events=trajectories[iid]) for iid, _ in researches
    ]

    documents: dict[str, PackDocument] = {}
    chunks: list[PackChunk] = []
    leaf_ids: list[str] = []

    import duckdb

    con = duckdb.connect(db_path, read_only=True)
    try:
        for iid, sub_q in researches:
            leaf_ids.append(iid)
            rows = trajectories[iid]
            for ev in rows:
                if ev.get("action_type") != ActionType.GRAPH_NODE_INSERTED.value:
                    continue
                payload = ev.get("payload") or {}
                if not isinstance(payload, dict):
                    continue
                if payload.get("node_type") != "insight":
                    continue
                node_id = payload.get("node_id")
                label = payload.get("canonical_label") or ""
                if not node_id:
                    continue

                meta_chunk = None
                meta_doc = None
                meta_ip = None
                leaf_authority = InvestigationAuthority(owner_user_id, iid, Path(events_dir))
                node_row = con.execute(
                    "SELECT n.canonical_label, n.metadata FROM nodes n "
                    "JOIN investigation_node_memberships m ON m.node_id = n.node_id "
                    "WHERE n.node_id = ? AND m.account_digest = ? "
                    "AND m.investigation_digest = ? LIMIT 1",
                    [
                        node_id,
                        leaf_authority.account_digest,
                        leaf_authority.investigation_digest,
                    ],
                ).fetchone()
                if node_row is None:
                    continue
                if node_row[0]:
                    label = str(node_row[0])
                node_meta = node_row[1]
                if isinstance(node_meta, str):
                    try:
                        node_meta = json.loads(node_meta)
                    except json.JSONDecodeError:
                        node_meta = None
                if isinstance(node_meta, dict):
                    meta_chunk = node_meta.get("chunk_id")
                    meta_doc = node_meta.get("source_document_id")
                    meta_ip = node_meta.get("ip_holder_id")
                    meta_inherited = node_meta.get("inherited_unit_ids", [])
                else:
                    meta_inherited = []

                strict = os.environ.get("ANTIEK_LEGAL_READ_ENFORCEMENT") == "1"
                legal_document: dict[str, Any] | None = None
                if meta_doc:
                    from substrate.legal_gate.read import read_document_compatibility

                    legal_document = read_document_compatibility(
                        con,
                        str(meta_doc),
                        authority=leaf_authority,
                        enforce=strict,
                    )
                    if strict and legal_document is None:
                        # A node cannot carry denied source metadata or labels
                        # into recursive prompt context.
                        continue
                elif strict:
                    # Derived insight text is not independently readable. It
                    # must retain an admitted source document in strict mode.
                    continue

                if not str(label).strip():
                    continue

                document_id = (
                    str(meta_doc)
                    if meta_doc
                    else f"doc-gather-{session_id}-{iid}"
                )
                chunk_id = (
                    str(meta_chunk) if meta_chunk else f"chunk-{node_id}"
                )

                if document_id not in documents:
                    ip_holder = (
                        str(legal_document.get("ip_holder_id"))
                        if legal_document is not None
                        and legal_document.get("ip_holder_id") is not None
                        else str(meta_ip) if meta_ip is not None
                        else None
                    )
                    title = (
                        f"Gather source ({iid})"
                        if document_id.startswith("doc-gather-")
                        else document_id
                    )
                    if (
                        not document_id.startswith("doc-gather-")
                        and legal_document is not None
                        and legal_document.get("title")
                    ):
                        title = str(legal_document["title"])
                    documents[document_id] = PackDocument(
                        document_id=document_id,
                        title=title,
                        ip_holder_id=ip_holder,
                        source_tier=3,
                    )

                doc = documents[document_id]
                chunks.append(
                    PackChunk(
                        chunk_id=chunk_id,
                        document_id=document_id,
                        ip_holder_id=doc.ip_holder_id,
                        text=str(label).strip(),
                        source_investigation_id=iid,
                        sub_question=sub_q,
                        inherited_unit_ids=tuple(meta_inherited),
                    )
                )
    finally:
        con.close()

    content_hash = compute_content_hash(
        session_id=session_id,
        problem_question=problem_question,
        chunks=chunks,
        documents=list(documents.values()),
        leaf_investigation_ids=leaf_ids,
        gather_mode=gather_mode,
        gather_plan_fingerprint=gather_plan_fingerprint,
        gather_reports=gather_reports,
        reuse_reports=reuse_reports,
    )
    try:
        return SessionEvidencePack(
            session_id=session_id,
            problem_question=problem_question,
            chunks=chunks,
            documents=list(documents.values()),
            leaf_investigation_ids=sorted(leaf_ids),
            gather_mode=gather_mode,
            gather_plan_fingerprint=gather_plan_fingerprint,
            gather_reports=gather_reports,
            reuse_reports=reuse_reports,
            content_hash=content_hash,
        )
    except ValidationError as exc:
        raise SessionEvidencePackError("evidence pack failed source-aware validation") from exc
