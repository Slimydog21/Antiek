"""Zero-spend interrogation preview packets for immutable compose drafts."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from .compose import COMPOSE_SCHEMA_VERSION, ComposeMember, compose_lock, load_compose_draft
from .import_notes import parse_body_from_html
from .paths import compose_member_path
from .schema import ResearchArtifactBody

INTERROGATION_PREVIEW_SCHEMA_VERSION = 1
MAX_INTERROGATION_PROMPT_CHARS = 4000
MAX_INTERROGATION_CONTEXT_CHARS = 48000
MIN_MEMBER_CONTEXT_CHARS = 900


class ComposeInterrogationError(ValueError):
    """Base class for compose interrogation preview failures."""


class ComposeInterrogationIntegrityError(ComposeInterrogationError):
    """The immutable compose manifest or member snapshots no longer match."""


class InvalidInterrogationPrompt(ComposeInterrogationError):
    """The operator prompt is empty or exceeds the strict preview bound."""


@dataclass(frozen=True)
class InterrogationMemberReceipt:
    index: int
    investigation_id: str
    content_hash: str
    included_chars: int
    omitted_chars: int
    truncated_fields: int
    omitted_fields: int


@dataclass(frozen=True)
class InterrogationPreviewPacket:
    schema_version: int
    compose_id: str
    selection_fingerprint: str
    prompt: str
    prompt_hash: str
    context: str
    member_receipts: list[InterrogationMemberReceipt]
    prompt_chars: int
    context_chars: int
    max_prompt_chars: int
    max_context_chars: int
    truncated_fields: int
    omitted_fields: int
    omitted_chars: int
    provider_called: bool = False


def build_interrogation_preview(
    compose_id: str,
    prompt: str,
    *,
    expected_fingerprint: str | None = None,
) -> InterrogationPreviewPacket:
    """Return a stable preview while sharing the compose lifecycle lock."""
    with compose_lock():
        return _build_interrogation_preview_locked(
            compose_id,
            prompt,
            expected_fingerprint=expected_fingerprint,
        )


def _build_interrogation_preview_locked(
    compose_id: str,
    prompt: str,
    *,
    expected_fingerprint: str | None,
) -> InterrogationPreviewPacket:
    clean_prompt = _validate_prompt(prompt)
    try:
        draft = load_compose_draft(compose_id)
    except ValueError as exc:
        if str(exc) == "invalid compose id":
            raise
        raise ComposeInterrogationIntegrityError(str(exc)) from exc
    if draft.compose_id != compose_id or not draft.selection_fingerprint:
        raise ComposeInterrogationIntegrityError("invalid compose identity")
    if expected_fingerprint is not None and expected_fingerprint != draft.selection_fingerprint:
        raise ComposeInterrogationIntegrityError("compose fingerprint mismatch")
    if _fingerprint(draft.members) != draft.selection_fingerprint:
        raise ComposeInterrogationIntegrityError("compose manifest fingerprint mismatch")
    if not 2 <= len(draft.members) <= 32:
        raise ComposeInterrogationIntegrityError("compose must contain 2-32 members")
    if len({m.investigation_id for m in draft.members}) != len(draft.members):
        raise ComposeInterrogationIntegrityError("compose contains duplicate members")

    bodies = [_load_validated_member(compose_id, index, member) for index, member in enumerate(draft.members)]
    separator_chars = 2 * (len(bodies) - 1)
    per_member_budget = max(
        MIN_MEMBER_CONTEXT_CHARS,
        (MAX_INTERROGATION_CONTEXT_CHARS - separator_chars) // len(bodies),
    )
    # Keep the total hard bound even if constants are changed later.
    per_member_budget = min(per_member_budget, MAX_INTERROGATION_CONTEXT_CHARS // len(bodies))

    sections: list[str] = []
    receipts: list[InterrogationMemberReceipt] = []
    for index, (member, body) in enumerate(zip(draft.members, bodies, strict=True)):
        rendered, receipt = _render_member(index, member, body, per_member_budget)
        sections.append(rendered)
        receipts.append(receipt)

    context = "\n\n".join(sections)
    if len(context) > MAX_INTERROGATION_CONTEXT_CHARS:
        # Equal member budgets should prevent this; fail closed if framing
        # overhead ever invalidates that invariant.
        raise ComposeInterrogationIntegrityError("interrogation context bound exceeded")

    return InterrogationPreviewPacket(
        schema_version=INTERROGATION_PREVIEW_SCHEMA_VERSION,
        compose_id=compose_id,
        selection_fingerprint=draft.selection_fingerprint,
        prompt=clean_prompt,
        prompt_hash=hashlib.sha256(clean_prompt.encode("utf-8")).hexdigest(),
        context=context,
        member_receipts=receipts,
        prompt_chars=len(clean_prompt),
        context_chars=len(context),
        max_prompt_chars=MAX_INTERROGATION_PROMPT_CHARS,
        max_context_chars=MAX_INTERROGATION_CONTEXT_CHARS,
        truncated_fields=sum(r.truncated_fields for r in receipts),
        omitted_fields=sum(r.omitted_fields for r in receipts),
        omitted_chars=sum(r.omitted_chars for r in receipts),
    )


def _validate_prompt(prompt: str) -> str:
    if not isinstance(prompt, str):
        raise InvalidInterrogationPrompt("prompt must be a string")
    clean = prompt.strip()
    if not clean:
        raise InvalidInterrogationPrompt("prompt is required")
    if len(clean) > MAX_INTERROGATION_PROMPT_CHARS:
        raise InvalidInterrogationPrompt(
            f"prompt exceeds {MAX_INTERROGATION_PROMPT_CHARS} characters"
        )
    return clean


def _load_validated_member(
    compose_id: str,
    index: int,
    member: ComposeMember,
) -> ResearchArtifactBody:
    try:
        html_text = compose_member_path(compose_id, index).read_text(encoding="utf-8")
        body = parse_body_from_html(html_text)
    except Exception as exc:
        raise ComposeInterrogationIntegrityError(
            f"compose member {index} HTML is unreadable"
        ) from exc
    if body.investigation_id != member.investigation_id:
        raise ComposeInterrogationIntegrityError(
            f"compose member {index} investigation id mismatch"
        )
    if body.content_hash() != member.content_hash:
        raise ComposeInterrogationIntegrityError(
            f"compose member {index} content hash mismatch"
        )
    return body


def _render_member(
    index: int,
    member: ComposeMember,
    body: ResearchArtifactBody,
    budget: int,
) -> tuple[str, InterrogationMemberReceipt]:
    header = (
        f"[member {index + 1}]\n"
        f"investigation_id: {member.investigation_id}\n"
        f"content_hash: {member.content_hash}\n"
    )
    fields = _member_fields(body)
    remaining = max(0, budget - len(header))
    included: list[str] = []
    omitted_chars = 0
    omitted_fields = 0
    truncated_fields = 0

    for label, value in fields:
        entry = f"{label}: {value.strip()}\n"
        if len(entry) <= remaining:
            included.append(entry)
            remaining -= len(entry)
            continue
        if remaining > len(label) + 18:
            prefix = f"{label}: "
            suffix = "\n[truncated]\n"
            keep = max(0, remaining - len(prefix) - len(suffix))
            included.append(prefix + value.strip()[:keep] + suffix)
            omitted_chars += max(0, len(entry) - remaining)
            truncated_fields += 1
            remaining = 0
        else:
            omitted_chars += len(entry)
            omitted_fields += 1

    rendered = header + "".join(included)
    receipt = InterrogationMemberReceipt(
        index=index,
        investigation_id=member.investigation_id,
        content_hash=member.content_hash,
        included_chars=len(rendered),
        omitted_chars=omitted_chars,
        truncated_fields=truncated_fields,
        omitted_fields=omitted_fields,
    )
    return rendered, receipt


def _member_fields(body: ResearchArtifactBody) -> list[tuple[str, str]]:
    fields: list[tuple[str, str]] = [
        ("problem_question", body.problem_question),
    ]
    if body.synthesis_excerpt:
        fields.append(("synthesis_excerpt", body.synthesis_excerpt))
    for insight in body.insights:
        fields.append(("insight", insight.text))
    for question in body.open_questions:
        fields.append(("open_question", question.text))
    for note in body.agent_notes:
        fields.append(("agent_note", note))
    if body.synthesis_withheld:
        fields.append(("synthesis_withheld", "true"))
    return [(label, value) for label, value in fields if value.strip()]


def _fingerprint(members: list[ComposeMember]) -> str:
    raw = json.dumps(
        {
            "schema_version": COMPOSE_SCHEMA_VERSION,
            "members": [[m.investigation_id, m.content_hash] for m in members],
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
