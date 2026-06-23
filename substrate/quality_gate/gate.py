"""Quality-gate primitives + composition."""

from __future__ import annotations

import enum
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class CandidateNote:
    """The shape a public-notes ingest pipeline candidate takes."""

    note_id: str
    user_id: str
    prose: str  # the human-readable body
    claims: tuple[str, ...]  # claim_ids referenced in the note
    claim_evidence: dict[str, tuple[str, ...]]  # claim_id → chunk_ids
    cited_source_tiers: tuple[int, ...]  # tier per cited source
    topic_tags: tuple[str, ...] = ()


class CheckResultKind(str, enum.Enum):
    PASS = "pass"
    FAIL = "fail"


@dataclass(frozen=True)
class CheckResult:
    """The verdict of one check (verification, voice-style, or
    source-tier)."""

    check_name: str
    kind: CheckResultKind
    score: float  # in [0, 1]; PASS does not require score == 1
    reasons: tuple[str, ...]


class QualityGateVerdict(str, enum.Enum):
    PASS_PUBLIC = "pass_public"  # eligible for collective graph
    REROUTE_PRIVATE = "reroute_private"  # private-graph only
    REJECT = "reject"  # neither private nor public


@dataclass(frozen=True)
class QualityGateResult:
    """The composite output of the gate."""

    gate_id: str = field(default_factory=lambda: f"qg-{uuid.uuid4().hex[:12]}")
    note_id: str = ""
    verdict: QualityGateVerdict = QualityGateVerdict.REJECT
    checks: tuple[CheckResult, ...] = ()
    decided_at: str = field(default_factory=_now_iso)

    @property
    def passed_checks(self) -> tuple[CheckResult, ...]:
        return tuple(c for c in self.checks if c.kind == CheckResultKind.PASS)

    @property
    def failed_checks(self) -> tuple[CheckResult, ...]:
        return tuple(c for c in self.checks if c.kind == CheckResultKind.FAIL)


Check = Callable[[CandidateNote], CheckResult]


# Policy: which combinations of pass/fail lead to which verdict.
# - verification PASS + voice-style PASS + source-tier PASS → PASS_PUBLIC
# - verification FAIL → REJECT (no evidence = not a note)
# - extraction_quality FAIL → REJECT (OCR garbage / near-empty is not a
#   document at all — a quality REJECT, never a reroute; SPR-03 M6)
# - voice-style FAIL OR source-tier FAIL → REROUTE_PRIVATE
#   (the user can still keep it in their private graph)


def _verdict_from_checks(
    checks: tuple[CheckResult, ...],
) -> QualityGateVerdict:
    by_name = {c.check_name: c for c in checks}
    verification = by_name.get("verification")
    voice_style = by_name.get("voice_style")
    source_tier = by_name.get("source_tier")
    extraction = by_name.get("extraction_quality")

    if verification is None or verification.kind == CheckResultKind.FAIL:
        return QualityGateVerdict.REJECT

    # A failed extraction is garbage, not a note that could live privately —
    # it is rejected outright (M6: failing items are rejected, not warned),
    # NOT rerouted. It never alters content_class/servability; this is the
    # ingest-eligibility verdict only.
    if extraction is not None and extraction.kind == CheckResultKind.FAIL:
        return QualityGateVerdict.REJECT

    voice_pass = voice_style is None or voice_style.kind == CheckResultKind.PASS
    tier_pass = source_tier is None or source_tier.kind == CheckResultKind.PASS
    if voice_pass and tier_pass:
        return QualityGateVerdict.PASS_PUBLIC
    return QualityGateVerdict.REROUTE_PRIVATE


def run_quality_gate(
    note: CandidateNote,
    *,
    verification_check: Check,
    voice_style_check: Check | None = None,
    source_tier_check: Check | None = None,
    extraction_quality_check: Check | None = None,
) -> QualityGateResult:
    """Compose the checks. verification is REQUIRED; the others are
    optional — when omitted they're treated as PASS so callers can ship a
    minimal gate first and tighten over time. A failing
    ``extraction_quality_check`` rejects the candidate (it is not a document),
    so callers ingesting extracted bodies pass it to reject OCR garbage /
    near-empty extracts before they reach the corpus.
    """
    checks: list[CheckResult] = [verification_check(note)]
    if voice_style_check is not None:
        checks.append(voice_style_check(note))
    if source_tier_check is not None:
        checks.append(source_tier_check(note))
    if extraction_quality_check is not None:
        checks.append(extraction_quality_check(note))
    verdict = _verdict_from_checks(tuple(checks))
    return QualityGateResult(
        note_id=note.note_id,
        verdict=verdict,
        checks=tuple(checks),
    )
