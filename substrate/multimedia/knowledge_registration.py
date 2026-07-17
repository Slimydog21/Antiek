"""Canonical graph registration and recursive-note twin for multimedia HTML."""

from __future__ import annotations

import asyncio
import hashlib
import html
import json
import re
import uuid
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from roles.note_taker import Distiller, run_document_pass
from roles.note_taker.distill import Distillation, DistilledQuestion
from roles.note_taker.parser import ExtractedNote
from runtime.db_lock import connect_read, connect_write
from services.html_projection.gate import ScriptViolation, assert_script_free
from substrate.event_log import emit_typed, trajectory
from substrate.graph.ops import insert_chunk, insert_document, insert_node
from substrate.multimedia.information_asset import (
    MultimediaInformationAsset,
    MultimediaKnowledgeRegistrationReceipt,
)
from substrate.schemas.events import (
    ActionType,
    ArtifactGeneratedPayload,
    GraphEdgeInsertedPayload,
    GraphNodeInsertedPayload,
)
from substrate.twin_recursion import TwinSourceEnvelopeError

_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_MAX_LINES = 10_000
_MAX_TRANSCRIPT_BYTES = 8 * 1024 * 1024
_RECOVERY_STALE_SECONDS = 15 * 60


class MultimediaKnowledgeRegistrationError(RuntimeError):
    """Canonical graph or twin registration could not be proven."""


class _Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class MultimediaTwinResult(_Model):
    registration: MultimediaKnowledgeRegistrationReceipt
    source_document_id: str
    source_event_id: str
    source_chunk_ids: tuple[str, ...]
    insight_node_ids: tuple[str, ...]
    question_node_ids: tuple[str, ...]
    twin_html: str
    twin_html_sha256: str = Field(pattern=_DIGEST.pattern)


class MultimediaDistillationState(_Model):
    state: Literal["not_started", "in_progress", "completed", "integrity_conflict"]
    recovery_eligible: bool
    recovery_stale_seconds: int = _RECOVERY_STALE_SECONDS
    claim_started_at: str | None = None


@dataclass(frozen=True)
class _TranscriptLine:
    line_id: str
    text: str
    citation_ids: tuple[str, ...]


@dataclass(frozen=True)
class _FrozenDistiller:
    result: Distillation

    def distill(self, text: str, *, source_event_ids: Any = (), context: str = "") -> Distillation:
        return self.result


class _InformationHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.lines: list[_TranscriptLine] = []
        self.metadata_text = ""
        self._line_id: str | None = None
        self._citation_ids: tuple[str, ...] = ()
        self._line_text: list[str] = []
        self._in_metadata = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "p" and values.get("data-line-id") is not None:
            if self._line_id is not None:
                raise MultimediaKnowledgeRegistrationError("nested transcript lines are invalid")
            self._line_id = values["data-line-id"]
            self._citation_ids = tuple((values.get("data-citation-ids") or "").split())
            self._line_text = []
        if tag == "template" and values.get("id") == "antiek-multimedia-metadata":
            self._in_metadata = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "p" and self._line_id is not None:
            text = "".join(self._line_text).strip()
            self.lines.append(
                _TranscriptLine(self._line_id, text, self._citation_ids)
            )
            self._line_id = None
            self._citation_ids = ()
            self._line_text = []
        if tag == "template" and self._in_metadata:
            self._in_metadata = False

    def handle_data(self, data: str) -> None:
        if self._line_id is not None:
            self._line_text.append(data)
        if self._in_metadata:
            self.metadata_text += data


class CanonicalMultimediaKnowledgeRegistrar:
    """Register source HTML/chunks/entity through Antiek's sole graph writers."""

    def __init__(
        self,
        *,
        db_path: str,
        owner_id: str,
        events_dir: str | None = None,
    ) -> None:
        self.db_path = db_path
        self.owner_id = _owner(owner_id)
        self.owner_digest = hashlib.sha256(self.owner_id.encode()).hexdigest()
        self.events_dir = events_dir

    def register(
        self, asset: MultimediaInformationAsset
    ) -> MultimediaKnowledgeRegistrationReceipt:
        lines = _validate_and_parse(asset, self.owner_digest)
        source_document_id, twin_document_id, graph_node_id = _identities(asset)
        metadata = _source_metadata(asset, graph_node_id, twin_document_id)
        connection = connect_write(self.db_path, purpose="multimedia_knowledge_register")
        try:
            connection.execute("BEGIN")
            try:
                insert_document(
                    connection,
                    document_id=source_document_id,
                    source_tier=1,
                    document_type="multimedia_html",
                    source_uri=f"antiek-mm://{asset.asset_id}/{asset.revision_id}/information.html",
                    title=asset.title,
                    investigation_id=_investigation_id(asset),
                    raw_text=asset.html,
                    metadata=metadata,
                    content_class="personal_reading",
                    owner_user_id=self.owner_id,
                    on_conflict="ignore",
                    events_dir=self.events_dir,
                )
                _verify_document(connection, source_document_id, asset, self.owner_id, metadata)
                for index, line in enumerate(lines):
                    chunk_id = _chunk_id(source_document_id, line.line_id)
                    insert_chunk(
                        connection,
                        document_id=source_document_id,
                        chunk_index=index,
                        section_path=line.line_id,
                        text=line.text,
                        token_count=len(line.text.split()),
                        chunk_id=chunk_id,
                    )
                    _verify_chunk(connection, chunk_id, source_document_id, index, line)
                insert_node(
                    connection,
                    canonical_label=asset.title,
                    node_type="entity",
                    graph_scope="depth",
                    investigation_id=_investigation_id(asset),
                    metadata=metadata,
                    node_id=graph_node_id,
                    on_conflict="ignore",
                    events_dir=self.events_dir,
                    owner_user_id=self.owner_id,
                    emit_event=False,
                )
                _verify_entity(connection, graph_node_id, asset.title, metadata, self.owner_id)
                connection.execute("COMMIT")
            except TwinSourceEnvelopeError as exc:
                connection.execute("ROLLBACK")
                raise MultimediaKnowledgeRegistrationError(
                    "multimedia graph document conflicts"
                ) from exc
            except Exception:
                connection.execute("ROLLBACK")
                raise
        finally:
            connection.close()
        return MultimediaKnowledgeRegistrationReceipt(
            owner_identity_digest=asset.owner_identity_digest,
            asset_id=asset.asset_id,
            revision_id=asset.revision_id,
            html_sha256=asset.html_sha256,
            graph_node_id=graph_node_id,
            twin_document_id=twin_document_id,
        )


async def register_multimedia_with_twin(
    asset: MultimediaInformationAsset,
    *,
    db_path: str,
    owner_id: str,
    distiller: Distiller,
    events_dir: str | None = None,
    embedding_provider: Any = None,
    distillation_recovery_token: str | None = None,
) -> MultimediaTwinResult:
    registrar = CanonicalMultimediaKnowledgeRegistrar(
        db_path=db_path, owner_id=owner_id, events_dir=events_dir
    )
    registration = registrar.register(asset)
    lines = _validate_and_parse(asset, registrar.owner_digest)
    source_document_id, twin_document_id, _ = _identities(asset)
    source_chunk_ids = tuple(
        _chunk_id(source_document_id, line.line_id) for line in lines
    )
    source_event_id = _ensure_source_event(
        asset, registration.graph_node_id, events_dir
    )
    _ensure_committed_graph_events(
        db_path,
        _investigation_id(asset),
        (registration.graph_node_id,),
        events_dir,
    )
    transcript = "\n\n".join(line.text for line in lines)
    distillation = await _checkpoint_distillation(
        db_path=db_path,
        owner_id=registrar.owner_id,
        asset=asset,
        source_document_id=source_document_id,
        source_event_id=source_event_id,
        transcript=transcript,
        distiller=distiller,
        recovery_token=distillation_recovery_token,
    )
    connection = connect_write(db_path, purpose="multimedia_twin_promote")
    try:
        connection.execute("BEGIN")
        try:
            result = await run_document_pass(
                source_document_id,
                transcript,
                investigation_id=_investigation_id(asset),
                distiller=_FrozenDistiller(distillation),
                chunk_ids=source_chunk_ids,
                supported_by=(registration.graph_node_id,),
                source_event_ids=(source_event_id,),
                identity_scope=source_document_id,
                owner_user_id=registrar.owner_id,
                embedding_provider=embedding_provider,
                emit_events=False,
                emit_graph_events=False,
                events_dir=events_dir,
                con=connection,
            )
            connection.execute("COMMIT")
        except Exception:
            connection.execute("ROLLBACK")
            raise
    finally:
        connection.close()
    _ensure_committed_graph_events(
        db_path,
        _investigation_id(asset),
        (registration.graph_node_id, *result.insight_node_ids, *result.question_node_ids),
        events_dir,
    )
    twin_html = _render_twin(
        asset,
        source_document_id,
        tuple(result.insight_node_ids),
        tuple(result.question_node_ids),
        db_path,
        registrar.owner_id,
    )
    _register_twin_document(
        db_path=db_path,
        owner_id=registrar.owner_id,
        asset=asset,
        twin_document_id=twin_document_id,
        twin_html=twin_html,
        events_dir=events_dir,
    )
    return MultimediaTwinResult(
        registration=registration,
        source_document_id=source_document_id,
        source_event_id=source_event_id,
        source_chunk_ids=source_chunk_ids,
        insight_node_ids=tuple(result.insight_node_ids),
        question_node_ids=tuple(result.question_node_ids),
        twin_html=twin_html,
        twin_html_sha256=hashlib.sha256(twin_html.encode()).hexdigest(),
    )


async def _checkpoint_distillation(
    *,
    db_path: str,
    owner_id: str,
    asset: MultimediaInformationAsset,
    source_document_id: str,
    source_event_id: str,
    transcript: str,
    distiller: Distiller,
    recovery_token: str | None = None,
) -> Distillation:
    run_id = _run_id(owner_id, source_document_id)
    row = _checkpoint_row(db_path, run_id)
    if row is not None:
        _verify_completed_claim(
            db_path,
            run_id,
            owner_id,
            source_document_id,
            asset.html_sha256,
            source_event_id,
        )
        return _decode_checkpoint(row, owner_id, source_document_id, asset, source_event_id)

    claim_token = uuid.uuid4().hex
    connection = connect_write(db_path, purpose="multimedia_distillation_claim")
    try:
        connection.execute("BEGIN")
        row = connection.execute(
            "SELECT owner_user_id, source_document_id, source_html_sha256, "
            "source_event_id, distillation_json, distillation_sha256 "
            "FROM multimedia_twin_runs WHERE run_id=?",
            [run_id],
        ).fetchone()
        if row is not None:
            claim = connection.execute(
                "SELECT owner_user_id, source_document_id, source_html_sha256, "
                "source_event_id, status FROM multimedia_distillation_claims WHERE run_id=?",
                [run_id],
            ).fetchone()
            _validate_completed_claim(
                claim,
                owner_id,
                source_document_id,
                asset.html_sha256,
                source_event_id,
            )
        if row is None:
            claim = connection.execute(
                "SELECT owner_user_id, source_document_id, source_html_sha256, "
                "source_event_id, claim_token, status "
                "FROM multimedia_distillation_claims WHERE run_id=?",
                [run_id],
            ).fetchone()
            if claim is not None:
                expected = (owner_id, source_document_id, asset.html_sha256, source_event_id)
                if tuple(claim[:4]) != expected:
                    raise MultimediaKnowledgeRegistrationError(
                        "multimedia distillation claim conflicts"
                    )
                if recovery_token is None or tuple(claim[4:]) != (
                    recovery_token,
                    "in_progress",
                ):
                    raise MultimediaKnowledgeRegistrationError(
                        "multimedia distillation outcome requires recovery"
                    )
                claim_token = recovery_token
            elif recovery_token is not None:
                raise MultimediaKnowledgeRegistrationError(
                    "multimedia distillation recovery authority conflicts"
                )
            else:
                connection.execute(
                    "INSERT INTO multimedia_distillation_claims "
                    "(run_id, owner_user_id, source_document_id, source_html_sha256, "
                    "source_event_id, claim_token, status) "
                    "VALUES (?, ?, ?, ?, ?, ?, 'in_progress')",
                    [
                        run_id,
                        owner_id,
                        source_document_id,
                        asset.html_sha256,
                        source_event_id,
                        claim_token,
                    ],
                )
        connection.execute("COMMIT")
    except Exception:
        connection.execute("ROLLBACK")
        raise
    finally:
        connection.close()
    if row is not None:
        return _decode_checkpoint(row, owner_id, source_document_id, asset, source_event_id)

    produced = await asyncio.to_thread(
        distiller.distill, transcript, source_event_ids=(source_event_id,)
    )
    payload = _encode_distillation(produced)
    digest = hashlib.sha256(payload.encode()).hexdigest()
    connection = connect_write(db_path, purpose="multimedia_distillation_checkpoint")
    try:
        connection.execute("BEGIN")
        claim = connection.execute(
            "SELECT claim_token, status FROM multimedia_distillation_claims WHERE run_id=?",
            [run_id],
        ).fetchone()
        if claim != (claim_token, "in_progress"):
            raise MultimediaKnowledgeRegistrationError("multimedia distillation claim conflicts")
        connection.execute(
            "INSERT INTO multimedia_twin_runs (run_id, owner_user_id, source_document_id, "
            "source_html_sha256, source_event_id, distillation_json, distillation_sha256) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            [run_id, owner_id, source_document_id, asset.html_sha256, source_event_id, payload, digest],
        )
        row = connection.execute(
            "SELECT owner_user_id, source_document_id, source_html_sha256, "
            "source_event_id, distillation_json, distillation_sha256 "
            "FROM multimedia_twin_runs WHERE run_id=?",
            [run_id],
        ).fetchone()
        connection.execute(
            "UPDATE multimedia_distillation_claims SET status='completed', "
            "completed_at=CURRENT_TIMESTAMP WHERE run_id=? AND claim_token=?",
            [run_id, claim_token],
        )
        connection.execute("COMMIT")
    except Exception:
        connection.execute("ROLLBACK")
        raise
    finally:
        connection.close()
    if row is None:
        raise MultimediaKnowledgeRegistrationError("multimedia distillation checkpoint is unavailable")
    return _decode_checkpoint(row, owner_id, source_document_id, asset, source_event_id)


def _checkpoint_row(db_path: str, run_id: str) -> Any:
    with connect_read(db_path) as connection:
        return connection.execute(
            "SELECT owner_user_id, source_document_id, source_html_sha256, "
            "source_event_id, distillation_json, distillation_sha256 "
            "FROM multimedia_twin_runs WHERE run_id=?",
            [run_id],
        ).fetchone()


def _verify_completed_claim(
    db_path: str,
    run_id: str,
    owner_id: str,
    source_document_id: str,
    source_html_sha256: str,
    source_event_id: str,
) -> None:
    with connect_read(db_path) as connection:
        claim = connection.execute(
            "SELECT owner_user_id, source_document_id, source_html_sha256, "
            "source_event_id, status FROM multimedia_distillation_claims WHERE run_id=?",
            [run_id],
        ).fetchone()
    _validate_completed_claim(
        claim,
        owner_id,
        source_document_id,
        source_html_sha256,
        source_event_id,
    )


def _validate_completed_claim(
    claim: Any,
    owner_id: str,
    source_document_id: str,
    source_html_sha256: str,
    source_event_id: str,
) -> None:
    expected = (
        owner_id,
        source_document_id,
        source_html_sha256,
        source_event_id,
        "completed",
    )
    if claim is None or tuple(claim) != expected:
        raise MultimediaKnowledgeRegistrationError(
            "multimedia distillation completed claim conflicts"
        )


def get_multimedia_distillation_state(
    asset: MultimediaInformationAsset,
    *,
    db_path: str,
    owner_id: str,
) -> MultimediaDistillationState:
    owner = _owner(owner_id)
    owner_digest = hashlib.sha256(owner.encode()).hexdigest()
    _validate_and_parse(asset, owner_digest)
    source_document_id, _, _ = _identities(asset)
    run_id = _run_id(owner, source_document_id)
    with connect_read(db_path) as connection:
        checkpoint = connection.execute(
            "SELECT owner_user_id, source_document_id, source_html_sha256, "
            "source_event_id, distillation_json, distillation_sha256 "
            "FROM multimedia_twin_runs WHERE run_id=?",
            [run_id],
        ).fetchone()
        claim = connection.execute(
            "SELECT owner_user_id, source_document_id, source_html_sha256, "
            "source_event_id, status, CAST(created_at AS VARCHAR), "
            "created_at <= CURRENT_TIMESTAMP - INTERVAL '15 minutes' "
            "FROM multimedia_distillation_claims WHERE run_id=?",
            [run_id],
        ).fetchone()
        if checkpoint is not None:
            if claim is None or tuple(claim[:3]) != (
                owner,
                source_document_id,
                asset.html_sha256,
            ) or claim[4] != "completed":
                return MultimediaDistillationState(
                    state="integrity_conflict", recovery_eligible=False
                )
            try:
                _decode_checkpoint(
                    checkpoint,
                    owner,
                    source_document_id,
                    asset,
                    str(claim[3]),
                )
            except MultimediaKnowledgeRegistrationError:
                return MultimediaDistillationState(
                    state="integrity_conflict",
                    recovery_eligible=claim[4] == "completed",
                    claim_started_at=str(claim[5]),
                )
            return MultimediaDistillationState(
                state="completed", recovery_eligible=False
            )
    if claim is None:
        return MultimediaDistillationState(state="not_started", recovery_eligible=False)
    if tuple(claim[:3]) != (owner, source_document_id, asset.html_sha256) or claim[4] != "in_progress":
        raise MultimediaKnowledgeRegistrationError("multimedia distillation claim conflicts")
    return MultimediaDistillationState(
        state="in_progress",
        claim_started_at=str(claim[5]),
        recovery_eligible=bool(claim[6]),
    )


def authorize_multimedia_distillation_recovery(
    asset: MultimediaInformationAsset,
    *,
    db_path: str,
    owner_id: str,
) -> str:
    owner = _owner(owner_id)
    owner_digest = hashlib.sha256(owner.encode()).hexdigest()
    _validate_and_parse(asset, owner_digest)
    source_document_id, _, _ = _identities(asset)
    run_id = _run_id(owner, source_document_id)
    new_token = uuid.uuid4().hex
    connection = connect_write(db_path, purpose="multimedia_distillation_recovery")
    try:
        connection.execute("BEGIN")
        checkpoint = connection.execute(
            "SELECT owner_user_id, source_document_id, source_html_sha256, "
            "source_event_id, distillation_json, distillation_sha256 "
            "FROM multimedia_twin_runs WHERE run_id=?",
            [run_id],
        ).fetchone()
        claim = connection.execute(
            "SELECT owner_user_id, source_document_id, source_html_sha256, "
            "source_event_id, claim_token, status, "
            "created_at <= CURRENT_TIMESTAMP - INTERVAL '15 minutes' "
            "FROM multimedia_distillation_claims WHERE run_id=?",
            [run_id],
        ).fetchone()
        if claim is None:
            raise MultimediaKnowledgeRegistrationError(
                "multimedia distillation recovery is unavailable"
            )
        expected = (owner, source_document_id, asset.html_sha256)
        if tuple(claim[:3]) != expected:
            raise MultimediaKnowledgeRegistrationError(
                "multimedia distillation claim conflicts"
            )
        checkpoint_corrupt = False
        if checkpoint is not None:
            try:
                _decode_checkpoint(
                    checkpoint,
                    owner,
                    source_document_id,
                    asset,
                    str(claim[3]),
                )
            except MultimediaKnowledgeRegistrationError:
                checkpoint_corrupt = True
            else:
                raise MultimediaKnowledgeRegistrationError(
                    "multimedia distillation is already completed"
                )
        if checkpoint_corrupt:
            if claim[5] != "completed":
                raise MultimediaKnowledgeRegistrationError(
                    "multimedia distillation claim conflicts"
                )
            connection.execute("DELETE FROM multimedia_twin_runs WHERE run_id=?", [run_id])
        elif claim[5] != "in_progress":
            raise MultimediaKnowledgeRegistrationError(
                "multimedia distillation claim conflicts"
            )
        elif not bool(claim[6]):
            raise MultimediaKnowledgeRegistrationError(
                "multimedia distillation claim is not stale"
            )
        old_token = claim[4]
        connection.execute(
            "UPDATE multimedia_distillation_claims SET claim_token=?, "
            "status='in_progress', created_at=CURRENT_TIMESTAMP, completed_at=NULL "
            "WHERE run_id=? AND claim_token=?",
            [new_token, run_id, old_token],
        )
        rotated = connection.execute(
            "SELECT claim_token FROM multimedia_distillation_claims WHERE run_id=?",
            [run_id],
        ).fetchone()
        if rotated != (new_token,):
            raise MultimediaKnowledgeRegistrationError(
                "multimedia distillation recovery authority conflicts"
            )
        connection.execute("COMMIT")
    except Exception:
        connection.execute("ROLLBACK")
        raise
    finally:
        connection.close()
    return new_token


def _run_id(owner_id: str, source_document_id: str) -> str:
    return f"mm-run-{hashlib.sha256(f'{owner_id}:{source_document_id}'.encode()).hexdigest()[:24]}"


def _encode_distillation(value: Distillation) -> str:
    return json.dumps(
        {
            "insights": [
                {
                    "note_id": note.note_id,
                    "text": note.text,
                    "confidence": note.confidence,
                    "source_event_ids": list(note.source_event_ids),
                }
                for note in value.insights
            ],
            "questions": [
                {
                    "text": question.text,
                    "asks_about": list(question.asks_about),
                    "anchor_region_id": question.anchor_region_id,
                }
                for question in value.questions
            ],
        },
        sort_keys=True,
        separators=(",", ":"),
    )


def _decode_checkpoint(
    row: Any,
    owner_id: str,
    source_document_id: str,
    asset: MultimediaInformationAsset,
    source_event_id: str,
) -> Distillation:
    owner, document_id, html_digest, event_id, payload, digest = row
    if (
        owner != owner_id
        or document_id != source_document_id
        or html_digest != asset.html_sha256
        or event_id != source_event_id
        or hashlib.sha256(payload.encode()).hexdigest() != digest
    ):
        raise MultimediaKnowledgeRegistrationError("multimedia distillation checkpoint conflicts")
    try:
        decoded = json.loads(payload)
        insights = [
            ExtractedNote(
                note_id=item["note_id"],
                text=item["text"],
                confidence=item["confidence"],
                source_event_ids=tuple(item["source_event_ids"]),
            )
            for item in decoded["insights"]
        ]
        questions = [
            DistilledQuestion(
                text=item["text"],
                asks_about=tuple(item["asks_about"]),
                anchor_region_id=item["anchor_region_id"],
            )
            for item in decoded["questions"]
        ]
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        raise MultimediaKnowledgeRegistrationError("multimedia distillation checkpoint is invalid") from exc
    return Distillation(insights=insights, questions=questions)


def _ensure_committed_graph_events(
    db_path: str,
    investigation_id: str,
    node_ids: tuple[str, ...],
    events_dir: str | None,
) -> None:
    existing = trajectory(investigation_id, events_dir=events_dir)
    node_events = {
        row["payload"].get("node_id")
        for row in existing
        if row["action_type"] == ActionType.GRAPH_NODE_INSERTED.value
    }
    edge_events = {
        row["payload"].get("edge_id")
        for row in existing
        if row["action_type"] == ActionType.GRAPH_EDGE_INSERTED.value
    }
    with connect_read(db_path) as connection:
        for node_id in node_ids:
            row = connection.execute(
                "SELECT canonical_label, node_type, graph_scope, embedding FROM nodes WHERE node_id=?",
                [node_id],
            ).fetchone()
            if row is None:
                raise MultimediaKnowledgeRegistrationError("committed multimedia graph node is unavailable")
            if node_id not in node_events:
                emit_typed(
                    investigation_id,
                    GraphNodeInsertedPayload(
                        node_id=node_id,
                        canonical_label=row[0],
                        node_type=row[1],
                        graph_scope=row[2],
                        has_embedding=row[3] is not None,
                    ),
                    role="note_taker",
                    events_dir=events_dir,
                )
        placeholders = ",".join("?" for _ in node_ids)
        edges = connection.execute(
            f"SELECT edge_id, source_node_id, target_node_id, relation, source_document_id, "
            f"chunk_id, source_tier, extraction_confidence, graph_scope FROM edges "
            f"WHERE source_node_id IN ({placeholders})",
            list(node_ids),
        ).fetchall()
    for edge in edges:
        if edge[0] not in edge_events:
            emit_typed(
                investigation_id,
                GraphEdgeInsertedPayload(
                    edge_id=edge[0], source_node_id=edge[1], target_node_id=edge[2],
                    relation=edge[3], source_document_id=edge[4], chunk_id=edge[5],
                    source_tier=edge[6], extraction_confidence=edge[7], graph_scope=edge[8],
                ),
                role="note_taker",
                events_dir=events_dir,
            )
    refreshed = trajectory(investigation_id, events_dir=events_dir)
    present_nodes = {
        row["payload"].get("node_id") for row in refreshed
        if row["action_type"] == ActionType.GRAPH_NODE_INSERTED.value
    }
    present_edges = {
        row["payload"].get("edge_id") for row in refreshed
        if row["action_type"] == ActionType.GRAPH_EDGE_INSERTED.value
    }
    if not set(node_ids).issubset(present_nodes) or not {edge[0] for edge in edges}.issubset(present_edges):
        raise MultimediaKnowledgeRegistrationError("multimedia graph event reconciliation failed")


def _validate_and_parse(
    asset: MultimediaInformationAsset, owner_digest: str
) -> tuple[_TranscriptLine, ...]:
    if asset.schema_version != "antiek.multimedia-information-asset.v1":
        raise MultimediaKnowledgeRegistrationError("multimedia information schema conflicts")
    if asset.owner_identity_digest != owner_digest:
        raise MultimediaKnowledgeRegistrationError("multimedia owner identity conflicts")
    if hashlib.sha256(asset.html.encode()).hexdigest() != asset.html_sha256:
        raise MultimediaKnowledgeRegistrationError("multimedia HTML digest conflicts")
    try:
        assert_script_free(asset.html)
    except ScriptViolation as exc:
        raise MultimediaKnowledgeRegistrationError("multimedia HTML is not inert") from exc
    parser = _InformationHTMLParser()
    parser.feed(asset.html)
    parser.close()
    if not parser.lines or len(parser.lines) > _MAX_LINES:
        raise MultimediaKnowledgeRegistrationError("multimedia transcript line count is invalid")
    if any(not _ID.fullmatch(line.line_id) or not line.text for line in parser.lines):
        raise MultimediaKnowledgeRegistrationError("multimedia transcript line is invalid")
    if len({line.line_id for line in parser.lines}) != len(parser.lines):
        raise MultimediaKnowledgeRegistrationError("multimedia transcript identity conflicts")
    transcript_size = sum(len(line.text.encode()) for line in parser.lines)
    if transcript_size > _MAX_TRANSCRIPT_BYTES:
        raise MultimediaKnowledgeRegistrationError("multimedia transcript exceeds its byte bound")
    references = {reference.citation_id: reference for reference in asset.source_references}
    if len(references) != len(asset.source_references):
        raise MultimediaKnowledgeRegistrationError("multimedia citation identity conflicts")
    for reference in asset.source_references:
        expected_id = _citation_id(
            reference.line_id,
            reference.chunk_id,
            reference.document_id,
            reference.locator,
            reference.quote_sha256,
        )
        if reference.citation_id != expected_id:
            raise MultimediaKnowledgeRegistrationError("multimedia citation identity conflicts")
    html_citations = {
        citation_id for line in parser.lines for citation_id in line.citation_ids
    }
    if html_citations != set(references):
        raise MultimediaKnowledgeRegistrationError("multimedia citation envelope conflicts")
    for line in parser.lines:
        if len(line.citation_ids) != len(set(line.citation_ids)):
            raise MultimediaKnowledgeRegistrationError("multimedia citation identity conflicts")
        if any(references[citation_id].line_id != line.line_id for citation_id in line.citation_ids):
            raise MultimediaKnowledgeRegistrationError("multimedia citation line conflicts")
    try:
        metadata = json.loads(parser.metadata_text)
    except json.JSONDecodeError:
        raise MultimediaKnowledgeRegistrationError("multimedia metadata is invalid") from None
    expected_references = [ref.model_dump(mode="json") for ref in asset.source_references]
    if (
        not isinstance(metadata, dict)
        or metadata.get("owner_identity_digest") != asset.owner_identity_digest
        or metadata.get("asset_id") != asset.asset_id
        or metadata.get("revision_id") != asset.revision_id
        or metadata.get("source_references") != expected_references
    ):
        raise MultimediaKnowledgeRegistrationError("multimedia metadata conflicts")
    return tuple(parser.lines)


def _identities(asset: MultimediaInformationAsset) -> tuple[str, str, str]:
    seed = f"{asset.owner_identity_digest}:{asset.asset_id}:{asset.revision_id}"
    suffix = hashlib.sha256(seed.encode()).hexdigest()[:24]
    return f"mm-info-{suffix}", f"mm-twin-{suffix}", f"mm-entity-{suffix}"


def _investigation_id(asset: MultimediaInformationAsset) -> str:
    seed = f"{asset.owner_identity_digest}:{asset.asset_id}:{asset.revision_id}"
    return f"mm-investigation-{hashlib.sha256(seed.encode()).hexdigest()[:20]}"


def _chunk_id(document_id: str, line_id: str) -> str:
    return f"mm-chunk-{hashlib.sha256(f'{document_id}:{line_id}'.encode()).hexdigest()[:24]}"


def _citation_id(
    line_id: str,
    chunk_id: str,
    document_id: str,
    locator: str | None,
    quote_sha256: str | None,
) -> str:
    payload = json.dumps(
        [line_id, chunk_id, document_id, locator, quote_sha256],
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(payload).hexdigest()


def _source_metadata(
    asset: MultimediaInformationAsset, graph_node_id: str, twin_document_id: str
) -> dict[str, object]:
    return {
        "schema_version": "antiek.multimedia-graph-registration.v1",
        "owner_identity_digest": asset.owner_identity_digest,
        "asset_id": asset.asset_id,
        "revision_id": asset.revision_id,
        "html_sha256": asset.html_sha256,
        "graph_node_id": graph_node_id,
        "twin_document_id": twin_document_id,
    }


def _verify_document(connection: Any, document_id: str, asset: MultimediaInformationAsset, owner_id: str, metadata: dict[str, object]) -> None:
    row = connection.execute(
        "SELECT title, document_type, sha256(raw_text), metadata, content_class, owner_user_id "
        "FROM documents WHERE document_id=?",
        [document_id],
    ).fetchone()
    expected = (
        asset.title,
        "multimedia_html",
        asset.html_sha256,
        json.dumps(metadata, default=str),
        "personal_reading",
        owner_id,
    )
    if row is None or tuple(row) != expected:
        raise MultimediaKnowledgeRegistrationError("multimedia graph document conflicts")


def _verify_chunk(connection: Any, chunk_id: str, document_id: str, index: int, line: _TranscriptLine) -> None:
    row = connection.execute(
        "SELECT document_id, chunk_index, section_path, text FROM chunks WHERE chunk_id=?",
        [chunk_id],
    ).fetchone()
    if row is None or tuple(row) != (document_id, index, line.line_id, line.text):
        raise MultimediaKnowledgeRegistrationError("multimedia graph chunk conflicts")


def _verify_entity(connection: Any, node_id: str, title: str, metadata: dict[str, object], owner_id: str) -> None:
    row = connection.execute(
        "SELECT canonical_label, node_type, graph_scope, metadata, owner_user_id FROM nodes WHERE node_id=?",
        [node_id],
    ).fetchone()
    expected = (title, "entity", "depth", json.dumps(metadata, default=str), owner_id)
    if row is None or tuple(row) != expected:
        raise MultimediaKnowledgeRegistrationError("multimedia graph entity conflicts")


def _ensure_source_event(
    asset: MultimediaInformationAsset,
    graph_node_id: str,
    events_dir: str | None,
) -> str:
    investigation_id = _investigation_id(asset)
    artifact_id = f"mm-artifact-{hashlib.sha256(f'{asset.owner_identity_digest}:{asset.asset_id}:{asset.revision_id}'.encode()).hexdigest()[:20]}"
    intent = f"multimedia_information_asset:{graph_node_id}"
    def matches() -> list[str]:
        return [
            str(row["event_id"])
            for row in trajectory(investigation_id, events_dir=events_dir)
            if row["action_type"] == ActionType.ARTIFACT_GENERATED.value
            and row["payload"].get("artifact_id") == artifact_id
            and row["payload"].get("content_hash") == asset.html_sha256
            and row["payload"].get("intent") == intent
        ]
    existing = matches()
    if existing:
        return existing[0]
    emit_typed(
        investigation_id,
        ArtifactGeneratedPayload(
            artifact_id=artifact_id,
            artifact_kind="other",
            intent=intent,
            generating_role="note_taker",
            artifact_path=f"antiek-mm://{asset.asset_id}/{asset.revision_id}/information.html",
            content_hash=asset.html_sha256,
            size_bytes=len(asset.html.encode()),
            source_event_ids=[],
        ),
        role="note_taker",
        events_dir=events_dir,
    )
    post_emit_matches = [
        str(row["event_id"])
        for row in trajectory(investigation_id, events_dir=events_dir)
        if row["action_type"] == ActionType.ARTIFACT_GENERATED.value
        and row["payload"].get("artifact_id") == artifact_id
        and row["payload"].get("content_hash") == asset.html_sha256
        and row["payload"].get("intent") == intent
    ]
    if not post_emit_matches:
        raise MultimediaKnowledgeRegistrationError("multimedia graph source event is unavailable")
    return post_emit_matches[0]


def _render_twin(
    asset: MultimediaInformationAsset,
    source_document_id: str,
    insight_ids: tuple[str, ...],
    question_ids: tuple[str, ...],
    db_path: str,
    owner_id: str,
) -> str:
    node_ids = insight_ids + question_ids
    labels: dict[str, tuple[str, str]] = {}
    if node_ids:
        placeholders = ",".join("?" for _ in node_ids)
        with connect_read(db_path) as connection:
            rows = connection.execute(
                f"SELECT node_id, node_type, canonical_label FROM nodes "
                f"WHERE node_id IN ({placeholders}) AND owner_user_id=?",
                [*node_ids, owner_id],
            ).fetchall()
        labels = {str(row[0]): (str(row[1]), str(row[2])) for row in rows}
    if set(labels) != set(node_ids):
        raise MultimediaKnowledgeRegistrationError("multimedia twin graph nodes are unavailable")
    insights = "".join(
        f'<li data-node-id="{html.escape(node_id, quote=True)}">{html.escape(labels[node_id][1])}</li>'
        for node_id in insight_ids
    ) or '<li class="empty">No insights were proposed.</li>'
    questions = "".join(
        f'<li data-node-id="{html.escape(node_id, quote=True)}">{html.escape(labels[node_id][1])}</li>'
        for node_id in question_ids
    ) or '<li class="empty">No open questions were proposed.</li>'
    rendered = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Twin notes: {html.escape(asset.title)}</title><style>body{{max-width:760px;margin:auto;padding:28px;font:16px/1.6 system-ui;color:#18181b;background:#fafafa}}section{{border-top:1px solid #d4d4d8;padding:18px 0}}.empty{{font-style:italic;color:#52525b}}</style></head><body><main data-source-document-id="{source_document_id}" data-source-html-sha256="{asset.html_sha256}" data-owner-digest="{asset.owner_identity_digest}"><h1>Twin notes: {html.escape(asset.title)}</h1><section><h2>Insights</h2><ol>{insights}</ol></section><section><h2>Open questions</h2><ol>{questions}</ol></section><footer>Asset {html.escape(asset.asset_id)} · revision {html.escape(asset.revision_id)}</footer></main></body></html>'''
    try:
        assert_script_free(rendered)
    except ScriptViolation as exc:
        raise MultimediaKnowledgeRegistrationError("multimedia twin HTML is not inert") from exc
    return rendered


def _register_twin_document(
    *,
    db_path: str,
    owner_id: str,
    asset: MultimediaInformationAsset,
    twin_document_id: str,
    twin_html: str,
    events_dir: str | None,
) -> None:
    metadata = {
        "schema_version": "antiek.multimedia-twin.v1",
        "owner_identity_digest": asset.owner_identity_digest,
        "asset_id": asset.asset_id,
        "revision_id": asset.revision_id,
        "source_html_sha256": asset.html_sha256,
        "twin_html_sha256": hashlib.sha256(twin_html.encode()).hexdigest(),
    }
    connection = connect_write(db_path, purpose="multimedia_twin_register")
    try:
        connection.execute("BEGIN")
        try:
            insert_document(
                connection,
                document_id=twin_document_id,
                source_tier=1,
                document_type="multimedia_twin",
                source_uri=f"antiek-mm://{asset.asset_id}/{asset.revision_id}/twin.html",
                title=f"Twin notes: {asset.title}",
                investigation_id=_investigation_id(asset),
                raw_text=twin_html,
                metadata=metadata,
                content_class="personal_reading",
                owner_user_id=owner_id,
                on_conflict="ignore",
                events_dir=events_dir,
            )
            row = connection.execute(
                "SELECT source_uri, title, source_tier, document_type, investigation_id, "
                "sha256(raw_text), metadata, content_class, owner_user_id "
                "FROM documents WHERE document_id=?",
                [twin_document_id],
            ).fetchone()
            if row is None or tuple(row) != (
                f"antiek-mm://{asset.asset_id}/{asset.revision_id}/twin.html",
                f"Twin notes: {asset.title}",
                1,
                "multimedia_twin",
                _investigation_id(asset),
                hashlib.sha256(twin_html.encode()).hexdigest(),
                json.dumps(metadata, default=str),
                "personal_reading",
                owner_id,
            ):
                raise MultimediaKnowledgeRegistrationError("multimedia twin document conflicts")
            connection.execute("COMMIT")
        except TwinSourceEnvelopeError as exc:
            connection.execute("ROLLBACK")
            raise MultimediaKnowledgeRegistrationError(
                "multimedia twin document conflicts"
            ) from exc
        except Exception:
            connection.execute("ROLLBACK")
            raise
    finally:
        connection.close()


def _owner(owner_id: str) -> str:
    if not isinstance(owner_id, str):
        raise MultimediaKnowledgeRegistrationError("multimedia owner identity is invalid")
    value = owner_id.strip()
    encoded = value.encode()
    if not encoded or len(encoded) > 512 or any(byte < 32 or byte == 127 for byte in encoded):
        raise MultimediaKnowledgeRegistrationError("multimedia owner identity is invalid")
    return value


__all__ = [
    "CanonicalMultimediaKnowledgeRegistrar",
    "MultimediaKnowledgeRegistrationError",
    "MultimediaTwinResult",
    "register_multimedia_with_twin",
]
