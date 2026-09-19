"""Revisioned private AI composition intent; this module has no dispatch capability."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from runtime.db_lock import LockedConnection

from .authority import InterviewAccountAuthority
from .composition import get_private_draft


class CompositionProposalConflict(RuntimeError):
    pass


@dataclass(frozen=True)
class CompositionProposal:
    proposal_id: str
    draft_id: str
    project_id: str
    revision: int
    base_revision: int
    source_manifest_sha256: str
    source_body_sha256: str
    provider_id: str
    model_id: str
    projected_max_cents: int
    approved_ceiling_cents: int
    instruction: str
    state: str


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _text(value: str, label: str, *, limit: int) -> str:
    if not isinstance(value, str) or not value or value != value.strip() or len(value) > limit:
        raise ValueError(f"composition proposal {label} is invalid")
    return value


def validate_proposal_inputs(
    *,
    base_revision: int,
    instruction: str,
    provider_id: str,
    model_id: str,
    projected_max_cents: int,
    approved_ceiling_cents: int,
    allowed_model_pairs: frozenset[tuple[str, str]],
) -> None:
    _text(instruction, "instruction", limit=20_000)
    provider_id = _text(provider_id, "provider id", limit=256)
    model_id = _text(model_id, "model id", limit=256)
    if type(base_revision) is not int or base_revision < 0:
        raise ValueError("composition proposal base revision is invalid")
    maximum_cents = 1_000_000_000
    if type(projected_max_cents) is not int or not 1 <= projected_max_cents <= maximum_cents:
        raise ValueError("composition proposal projection is invalid")
    if type(approved_ceiling_cents) is not int or not 1 <= approved_ceiling_cents <= maximum_cents:
        raise ValueError("composition proposal ceiling is invalid")
    if projected_max_cents > approved_ceiling_cents:
        raise ValueError("composition proposal exceeds approved ceiling")
    if (provider_id, model_id) not in allowed_model_pairs:
        raise ValueError("composition proposal model is not registered for this provider")


def _from_row(row: tuple[Any, ...]) -> CompositionProposal:
    return CompositionProposal(
        proposal_id=str(row[0]), draft_id=str(row[1]), project_id=str(row[2]),
        revision=int(row[3]), base_revision=int(row[4]),
        source_manifest_sha256=str(row[5]), source_body_sha256=str(row[6]),
        provider_id=str(row[7]), model_id=str(row[8]), projected_max_cents=int(row[9]),
        approved_ceiling_cents=int(row[10]), instruction=str(row[11]), state=str(row[12]),
    )


def _read_row(con: Any, authority: InterviewAccountAuthority, *, proposal_id: str) -> tuple[Any, ...]:
    row = con.execute(
        "SELECT proposal_id, draft_id, project_id, revision, base_revision, "
        "source_manifest_sha256, source_body_sha256, provider_id, model_id, "
        "projected_max_cents, approved_ceiling_cents, instruction, state "
        "FROM interview_composition_proposals_authority WHERE account_digest = ? "
        "AND owner_user_id = ? AND proposal_id = ?",
        [authority.account_digest, authority.account_id, proposal_id],
    ).fetchone()
    if row is None:
        raise ValueError("composition proposal not found")
    return tuple(row)


def get_proposal(
    con: Any, authority: InterviewAccountAuthority, *, proposal_id: str
) -> CompositionProposal:
    proposal = _from_row(_read_row(con, authority, proposal_id=proposal_id))
    draft = get_private_draft(con, authority, draft_id=proposal.draft_id)
    if draft.project_id != proposal.project_id or (
        draft.manifest_sha256 != proposal.source_manifest_sha256
        or draft.body_sha256 != proposal.source_body_sha256
    ):
        raise CompositionProposalConflict("composition proposal source evidence no longer matches")
    return proposal


def create_proposal(
    con: LockedConnection,
    authority: InterviewAccountAuthority,
    *,
    project_id: str,
    draft_id: str,
    mutation_key: str,
    base_revision: int,
    instruction: str,
    provider_id: str,
    model_id: str,
    projected_max_cents: int,
    approved_ceiling_cents: int,
    allowed_model_pairs: frozenset[tuple[str, str]],
) -> CompositionProposal:
    if not isinstance(con, LockedConnection):
        raise TypeError("composition proposal requires a LockedConnection")
    project_id = _text(project_id, "project id", limit=512)
    draft_id = _text(draft_id, "draft id", limit=512)
    mutation_key = _text(mutation_key, "mutation key", limit=512)
    validate_proposal_inputs(
        base_revision=base_revision, instruction=instruction, provider_id=provider_id,
        model_id=model_id, projected_max_cents=projected_max_cents,
        approved_ceiling_cents=approved_ceiling_cents,
        allowed_model_pairs=allowed_model_pairs,
    )
    draft = get_private_draft(con, authority, draft_id=draft_id)
    if draft.project_id != project_id:
        raise ValueError("composition proposal draft not found")
    request_json = json.dumps({
        "schema_version": 1, "project_id": project_id, "draft_id": draft_id,
        "base_revision": base_revision,
        "instruction": instruction, "provider_id": provider_id, "model_id": model_id,
        "projected_max_cents": projected_max_cents,
        "approved_ceiling_cents": approved_ceiling_cents,
    }, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    request_sha = _sha(request_json)
    replay = con.execute(
        "SELECT request_sha256, proposal_id FROM interview_composition_proposals_authority "
        "WHERE account_digest = ? AND owner_user_id = ? AND mutation_key = ?",
        [authority.account_digest, authority.account_id, mutation_key],
    ).fetchone()
    if replay is not None:
        if str(replay[0]) != request_sha:
            raise CompositionProposalConflict("composition proposal key was reused with different input")
        return get_proposal(con, authority, proposal_id=str(replay[1]))
    latest = con.execute(
        "SELECT coalesce(max(revision), 0) FROM interview_composition_proposals_authority "
        "WHERE account_digest = ? AND owner_user_id = ? AND draft_id = ?",
        [authority.account_digest, authority.account_id, draft_id],
    ).fetchone()
    current_revision = int(latest[0])
    if current_revision != base_revision:
        raise CompositionProposalConflict("stale composition proposal revision")
    revision = current_revision + 1
    proposal_id = "ivap-" + _sha(
        f"antiek-ai-proposal-v1\0{authority.account_digest}\0{mutation_key}\0{request_sha}"
    )[:32]
    con.execute(
        "INSERT INTO interview_composition_proposals_authority "
        "(account_digest, proposal_id, draft_id, project_id, owner_user_id, mutation_key, "
        "request_sha256, revision, base_revision, source_manifest_sha256, source_body_sha256, "
        "provider_id, model_id, projected_max_cents, approved_ceiling_cents, instruction) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [authority.account_digest, proposal_id, draft_id, draft.project_id,
         authority.account_id, mutation_key, request_sha, revision, base_revision,
         draft.manifest_sha256, draft.body_sha256, provider_id, model_id,
         projected_max_cents, approved_ceiling_cents, instruction],
    )
    return get_proposal(con, authority, proposal_id=proposal_id)


__all__ = [
    "CompositionProposal", "CompositionProposalConflict", "create_proposal", "get_proposal",
    "validate_proposal_inputs",
]
