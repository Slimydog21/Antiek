"""Import one verified research composition as a provenance-bound Write draft."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from runtime.db_lock import LockedConnection
from substrate.graph.ops import insert_deliverable, insert_section
from substrate.research_artifact.compose import VerifiedComposition, VerifiedCompositionMember

from .outline_block import place_block

_SNAPSHOT_KEYS = {
    "composition_id",
    "content_hash",
    "investigation_id",
    "member_index",
    "node_id",
    "rendered_sha256",
    "source_profile",
    "snapshot_text",
}


@dataclass(frozen=True)
class CompositionDraftMember:
    member_index: int
    investigation_id: str
    content_hash: str
    rendered_sha256: str
    source_section_id: str
    evidence_count: int
    insufficient_evidence: bool


@dataclass(frozen=True)
class CompositionDraft:
    deliverable_id: str
    composition_id: str
    ordered_set_digest: str
    analysis_section_id: str
    members: list[CompositionDraftMember]
    replayed: bool

    @property
    def insufficient_evidence_members(self) -> list[str]:
        return [member.investigation_id for member in self.members if member.insufficient_evidence]


@dataclass(frozen=True)
class _PreparedMember:
    source: VerifiedCompositionMember
    evidence: list[tuple[str, str, str]]


def composition_draft_request_digest(
    *, composition_id: str, title: str, deliverable_kind: str, idempotency_key: str
) -> str:
    canonical = json.dumps(
        {
            "composition_id": composition_id,
            "deliverable_kind": deliverable_kind,
            "idempotency_key": idempotency_key,
            "title": title,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def composition_snapshot_text(metadata: dict | None, *, node_id: str | None) -> str | None:
    if not isinstance(metadata, dict) or metadata.get("source_profile") is None:
        return None
    if (
        set(metadata) != _SNAPSHOT_KEYS
        or metadata.get("source_profile") != "composition_member_v1"
        or metadata.get("node_id") != node_id
        or not isinstance(metadata.get("snapshot_text"), str)
        or not metadata["snapshot_text"].strip()
        or not isinstance(metadata.get("member_index"), int)
        or isinstance(metadata.get("member_index"), bool)
        or metadata["member_index"] < 0
        or any(
            not isinstance(metadata.get(key), str) or not metadata[key]
            for key in ("composition_id", "investigation_id", "content_hash", "rendered_sha256")
        )
        or len(metadata["content_hash"]) != 64
        or len(metadata["rendered_sha256"]) != 64
    ):
        raise ValueError("invalid composition snapshot block metadata")
    return metadata["snapshot_text"]


def _snapshot_metadata(
    composition: VerifiedComposition,
    member: VerifiedCompositionMember,
    member_index: int,
    node_id: str,
    snapshot_text: str,
) -> dict[str, object]:
    return {
        "composition_id": composition.composition_id,
        "content_hash": member.content_hash,
        "investigation_id": member.investigation_id,
        "member_index": member_index,
        "node_id": node_id,
        "rendered_sha256": member.rendered_sha256,
        "source_profile": "composition_member_v1",
        "snapshot_text": snapshot_text,
    }


def _prepare(composition: VerifiedComposition) -> list[_PreparedMember]:
    prepared: list[_PreparedMember] = []
    for member in composition.members:
        evidence = [(item.node_id, "insight", item.text) for item in member.body.insights] + [
            (item.node_id, "open_question", item.text) for item in member.body.open_questions
        ]
        node_ids = [item[0] for item in evidence]
        if len(set(node_ids)) != len(node_ids):
            raise ValueError("composition member contains duplicate evidence node IDs")
        prepared.append(_PreparedMember(member, evidence))
    return prepared


def _read_draft(con: LockedConnection, deliverable_id: str, *, replayed: bool) -> CompositionDraft:
    head = con.execute(
        "SELECT composition_id, ordered_set_digest, analysis_section_id "
        "FROM deliverable_compositions WHERE deliverable_id = ?",
        [deliverable_id],
    ).fetchone()
    if head is None:
        raise ValueError("composition draft receipt is missing")
    rows = con.execute(
        "SELECT member_index, investigation_id, content_hash, rendered_sha256, "
        "source_section_id, evidence_count, insufficient_evidence "
        "FROM deliverable_composition_members WHERE deliverable_id = ? "
        "ORDER BY member_index",
        [deliverable_id],
    ).fetchall()
    members = [
        CompositionDraftMember(
            member_index=int(row[0]),
            investigation_id=row[1],
            content_hash=row[2],
            rendered_sha256=row[3],
            source_section_id=row[4],
            evidence_count=int(row[5]),
            insufficient_evidence=bool(row[6]),
        )
        for row in rows
    ]
    if not 2 <= len(members) <= 20 or [member.member_index for member in members] != list(
        range(len(members))
    ):
        raise ValueError("composition draft member receipt is incomplete")
    return CompositionDraft(
        deliverable_id=deliverable_id,
        composition_id=head[0],
        ordered_set_digest=head[1],
        analysis_section_id=head[2],
        members=members,
        replayed=replayed,
    )


def _verify_replay(
    con: LockedConnection,
    *,
    owner_user_id: str,
    request_digest: str,
    composition: VerifiedComposition,
    prepared: list[_PreparedMember],
    deliverable_id: str,
) -> CompositionDraft:
    head = con.execute(
        "SELECT dc.owner_user_id, dc.request_digest, dc.composition_id, "
        "dc.ordered_set_digest, dc.composition_schema_version, dc.analysis_section_id, "
        "d.owner_user_id FROM deliverable_compositions dc JOIN deliverables d "
        "ON d.deliverable_id = dc.deliverable_id WHERE dc.deliverable_id = ?",
        [deliverable_id],
    ).fetchone()
    if (
        head is None
        or head[:5]
        != (
            owner_user_id,
            request_digest,
            composition.composition_id,
            composition.ordered_set_digest,
            composition.schema_version,
        )
        or head[6] != owner_user_id
    ):
        raise ValueError("stored composition draft authority disagrees with source")
    result = _read_draft(con, deliverable_id, replayed=True)
    expected_members = [
        (
            index,
            item.source.investigation_id,
            item.source.content_hash,
            item.source.rendered_sha256,
            len(item.evidence),
            not item.evidence,
        )
        for index, item in enumerate(prepared)
    ]
    actual_members = [
        (
            member.member_index,
            member.investigation_id,
            member.content_hash,
            member.rendered_sha256,
            member.evidence_count,
            member.insufficient_evidence,
        )
        for member in result.members
    ]
    section_ids = [result.analysis_section_id] + [
        member.source_section_id for member in result.members
    ]
    section_count = con.execute(
        "SELECT count(*) FROM deliverable_sections WHERE deliverable_id = ? "
        "AND section_id = ANY(?)",
        [deliverable_id, section_ids],
    ).fetchone()[0]
    if actual_members != expected_members or section_count != len(section_ids):
        raise ValueError("stored composition draft authority disagrees with source")

    expected_blocks: list[tuple[str, str, str, str]] = []
    analysis_seen: set[str] = set()
    for index, item in enumerate(prepared):
        source_section = result.members[index].source_section_id
        for node_id, block_kind, snapshot_text in item.evidence:
            metadata = json.dumps(
                _snapshot_metadata(composition, item.source, index, node_id, snapshot_text),
                sort_keys=True,
                separators=(",", ":"),
            )
            expected_blocks.append((source_section, node_id, block_kind, metadata))
            if node_id not in analysis_seen:
                expected_blocks.append((result.analysis_section_id, node_id, block_kind, metadata))
                analysis_seen.add(node_id)
    rows = con.execute(
        "SELECT ob.section_id, ob.node_id, ob.block_kind, ob.metadata "
        "FROM outline_blocks ob JOIN deliverable_sections ds "
        "ON ds.section_id = ob.section_id WHERE ds.deliverable_id = ?",
        [deliverable_id],
    ).fetchall()
    actual_blocks: list[tuple[str, str, str, str]] = []
    for section_id, node_id, block_kind, metadata_text in rows:
        try:
            metadata = json.loads(metadata_text) if metadata_text else None
        except (TypeError, ValueError):
            raise ValueError("stored composition draft block metadata is invalid") from None
        if not isinstance(metadata, dict) or metadata.get("source_profile") != "composition_member_v1":
            continue
        canonical = json.dumps(metadata, sort_keys=True, separators=(",", ":"))
        actual_blocks.append((section_id, node_id, block_kind, canonical))
    if sorted(actual_blocks) != sorted(expected_blocks):
        raise ValueError("stored composition draft scaffold disagrees with source")
    return result


def create_composition_draft(
    con: LockedConnection,
    *,
    owner_user_id: str,
    composition: VerifiedComposition,
    title: str,
    deliverable_kind: str,
    idempotency_key: str,
) -> CompositionDraft:
    request_digest = composition_draft_request_digest(
        composition_id=composition.composition_id,
        title=title,
        deliverable_kind=deliverable_kind,
        idempotency_key=idempotency_key,
    )
    prepared = _prepare(composition)
    con.execute("BEGIN TRANSACTION")
    try:
        replay = con.execute(
            "SELECT deliverable_id, request_digest FROM deliverable_compositions "
            "WHERE owner_user_id = ? AND idempotency_key = ?",
            [owner_user_id, idempotency_key],
        ).fetchone()
        if replay is not None:
            if replay[1] != request_digest:
                raise ValueError("idempotency key was already used for a different draft request")
            result = _verify_replay(
                con,
                owner_user_id=owner_user_id,
                request_digest=request_digest,
                composition=composition,
                prepared=prepared,
                deliverable_id=replay[0],
            )
            con.execute("COMMIT")
            return result

        deliverable_id = insert_deliverable(
            con,
            title=title,
            deliverable_kind=deliverable_kind,
            owner_user_id=owner_user_id,
            metadata={"review_state": "source_scaffold"},
        )
        analysis_section_id = insert_section(
            con,
            deliverable_id=deliverable_id,
            section_index=0,
            title="Analysis",
        )
        con.execute(
            "INSERT INTO deliverable_compositions "
            "(deliverable_id, owner_user_id, idempotency_key, request_digest, "
            "composition_id, ordered_set_digest, composition_schema_version, "
            "analysis_section_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                deliverable_id,
                owner_user_id,
                idempotency_key,
                request_digest,
                composition.composition_id,
                composition.ordered_set_digest,
                composition.schema_version,
                analysis_section_id,
            ],
        )

        analysis_index = 0
        analysis_seen: set[str] = set()
        for member_index, item in enumerate(prepared):
            member = item.source
            body = member.body
            evidence = item.evidence
            source_section_id = insert_section(
                con,
                deliverable_id=deliverable_id,
                section_index=member_index + 1,
                title=body.problem_question[:300],
            )
            con.execute(
                "INSERT INTO deliverable_composition_members "
                "(deliverable_id, member_index, investigation_id, content_hash, "
                "rendered_sha256, source_section_id, evidence_count, insufficient_evidence) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    deliverable_id,
                    member_index,
                    member.investigation_id,
                    member.content_hash,
                    member.rendered_sha256,
                    source_section_id,
                    len(evidence),
                    not evidence,
                ],
            )
            for source_index, (node_id, block_kind, snapshot_text) in enumerate(evidence):
                metadata = _snapshot_metadata(
                    composition,
                    member,
                    member_index,
                    node_id,
                    snapshot_text,
                )
                common = {
                    "block_kind": block_kind,
                    "provenance_kind": "graph_node",
                    "node_id": node_id,
                    "content": None,
                    "metadata": metadata,
                    "deliverable_id": deliverable_id,
                    "investigation_id": member.investigation_id,
                    "emit_event": False,
                }
                place_block(
                    con,
                    section_id=source_section_id,
                    block_index=source_index,
                    **common,
                )
                if node_id not in analysis_seen:
                    place_block(
                        con,
                        section_id=analysis_section_id,
                        block_index=analysis_index,
                        **common,
                    )
                    analysis_seen.add(node_id)
                    analysis_index += 1

        result = _read_draft(con, deliverable_id, replayed=False)
        con.execute("COMMIT")
        return result
    except BaseException:
        con.execute("ROLLBACK")
        raise
