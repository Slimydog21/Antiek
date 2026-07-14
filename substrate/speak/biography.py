"""Speak SPR-08 — biography authoring orchestration (reuse Write).

The operator's original DeepBlu loop: have the AI write an outline from
the insights and questions, recursively chase deeper insights + answer
open questions + harden stories, then produce the biography. This module
ORCHESTRATES that by reusing the Write workflow — it is biography-
specific orchestration, NOT a second authoring engine:

  • outline ← the project's multi-party claims, composed via the
    OutlineComposer contract (Write's composer is the eventual owner;
    the default writes section_blocks directly) (M1);
  • a bounded recursive deepening loop: detect gaps → drive the
    compounding interviewer (SPR-04) to gather more → re-outline, with
    EXPLICIT halt criteria so it can't chase forever (M2);
  • draft ← the creative_writer role (Write SPR-06), claims cited to
    interviewees, voice_style gate (M3);
  • for public output, only multiply-attested (SPR-05) or operator-
    attested (SPR-01) third-party claims; uncorroborated ones are
    EXCLUDED (public) or MARKED unverified (private) — never smoothed
    into a confident, citation-free sentence (M4);
  • each drafted block links to its contributing interviewee(s) so the
    SPR-06 split can compute shares (M5).

Honesty (rigor #1): a thin project yields a thin biography; we don't pad
it with invention, and contradictions are presented honestly, not
resolved away.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from roles.creative_writer import (
    CreativeWriterBlock,
    CreativeWriterContext,
    parse_creative_writer_response,
    render_full_prompt,
)
from substrate.graph.ops import attach_block_to_section, insert_deliverable, insert_section
from substrate.voice_style.rubric import score_voice_style

from .contracts import OutlineBlock, OutlineComposer
from .interviewer_context import SpeakGraphGapSource
from .project import project_claims
from .publish_gate import check_claim_publishable
from .schema import ensure_speak_schema
from .third_party import get_claim

# The existing voice/style quality-gate threshold (substrate/voice_style).
DEFAULT_VOICE_STYLE_THRESHOLD = 0.70


# ---------------------------------------------------------------------------
# M1 — outline from multi-party insights
# ---------------------------------------------------------------------------


class SpeakOutlineComposer:
    """Default ``OutlineComposer``: persists an outline as a deliverable
    section + ``section_blocks`` (the existing Write substrate). Write's
    own composer will replace this and satisfy the same contract."""

    def __init__(self, con: Any):
        self.con = con

    def compose(self, *, deliverable_id: str, section_title: str, blocks: list[OutlineBlock]) -> str:
        section_id = insert_section(
            self.con, deliverable_id=deliverable_id, section_index=0, title=section_title
        )
        for i, b in enumerate(blocks):
            kind = b.block_kind if b.block_kind in (
                "insight", "open_question", "operator_note", "claim"
            ) else "claim"
            attach_block_to_section(
                self.con, section_id=section_id, block_kind=kind,
                block_id=b.block_id, block_index=i,
            )
        return section_id


@dataclass(frozen=True)
class Outline:
    deliverable_id: str
    section_id: str
    blocks: tuple[OutlineBlock, ...]


def assemble_outline(
    con: Any,
    *,
    project_id: str,
    title: str = "Biography",
    deliverable_id: str | None = None,
    composer: OutlineComposer | None = None,
) -> Outline:
    """Compose a biography outline of OutlineBlocks from the project's
    claims, each carrying provenance to its contributing interviewee(s)."""
    ensure_speak_schema(con)
    blocks = [
        OutlineBlock(
            block_id=c.claim_id,
            block_kind="claim",
            label=c.text[:60],
            body=c.text,
            contributor_interview_ids=((c.interview_id,) if c.interview_id else ()),
            source_tier=None,
        )
        for c in project_claims(con, project_id)
    ]
    if composer is None:
        # Write SPR-01 has landed: compose through its canonical outline_blocks
        # layer (which supersedes section_blocks) instead of forking onto the
        # legacy substrate. Lazy import avoids the write_composer ↔ biography
        # cycle. Falls back to SpeakOutlineComposer if Write is unavailable.
        from .write_composer import default_outline_composer
        composer = default_outline_composer(con, investigation_id=f"speak-biography-{project_id}")
    if deliverable_id is None:
        deliverable_id = insert_deliverable(
            con, title=title, deliverable_kind="biography_section"
        )
    section_id = composer.compose(deliverable_id=deliverable_id, section_title=title, blocks=blocks)
    return Outline(deliverable_id=deliverable_id, section_id=section_id, blocks=tuple(blocks))


# ---------------------------------------------------------------------------
# M2 — bounded recursive deepening loop
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DeepeningResult:
    rounds_run: int
    halt_reason: str  # 'no_gaps' | 'diminishing_returns' | 'max_rounds' | 'operator_stop'
    prompts_generated: list[str] = field(default_factory=list)


def run_deepening(
    con: Any,
    *,
    project_id: str,
    gap_source: Any | None = None,
    max_rounds: int = 3,
    gather_fn: Callable[[int], None] | None = None,
    operator_stop: Callable[[int], bool] | None = None,
) -> DeepeningResult:
    """Recursively chase gaps, BOUNDED. Each round detects open questions
    (DRW gaps / SpeakGraphGapSource), emits interview prompts, and lets
    the caller gather more (``gather_fn``). Halts on:

      • no_gaps           — converged (nothing left to chase);
      • diminishing_returns — gaps stopped shrinking;
      • operator_stop     — the operator pulled the cord;
      • max_rounds        — the hard budget.

    It can NEVER run unbounded: even with a static gap source it halts via
    diminishing_returns or max_rounds.
    """
    gap_source = gap_source or SpeakGraphGapSource(con)
    prompts: list[str] = []
    rounds_run = 0
    prev_count: int | None = None

    for r in range(1, max_rounds + 1):
        if operator_stop is not None and operator_stop(r):
            return DeepeningResult(rounds_run, "operator_stop", prompts)
        gaps = gap_source.open_questions(project_id)
        if not gaps:
            return DeepeningResult(rounds_run, "no_gaps", prompts)
        if prev_count is not None and len(gaps) >= prev_count:
            return DeepeningResult(rounds_run, "diminishing_returns", prompts)
        prev_count = len(gaps)
        prompts.extend(g.text for g in gaps)
        rounds_run += 1
        if gather_fn is not None:
            gather_fn(r)  # the caller drives interviews → may reduce gaps

    return DeepeningResult(rounds_run, "max_rounds", prompts)


# ---------------------------------------------------------------------------
# M3–M5 — draft generation (reuse creative_writer), corroborated-only,
#         contributor provenance
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Draft:
    prose_text: str
    # paragraph index → contributing claim block ids; retained for Write X-ray
    # and for defensible Speak→Read provenance.
    prose_provenance: dict[int, list[str]]
    cited_interview_ids: tuple[str, ...]
    excluded_claim_ids: tuple[str, ...]            # uncorroborated 3rd-party, public output
    unverified_marked_claim_ids: tuple[str, ...]   # included-but-marked, private draft
    voice_style_score: float
    voice_style_ok: bool
    # block_id → contributing interviewee ids. Feeds the SPR-06 split.
    block_contributors: dict[str, tuple[str, ...]] = field(default_factory=dict)


def generate_draft(
    con: Any,
    *,
    project_id: str,
    outline: Outline,
    public: bool = False,
    dispatch_fn: Callable[..., Any] | None = None,
    voice_style_threshold: float = DEFAULT_VOICE_STYLE_THRESHOLD,
) -> Draft:
    """Generate the biography draft from the outline.

    For PUBLIC output, an uncorroborated/​un-attested third-party claim is
    EXCLUDED. For a PRIVATE draft it is included but MARKED unverified.
    Either way it is never silently presented as fact. Each block links
    to its contributing interviewee(s) for the SPR-06 split.
    """
    included: list[OutlineBlock] = []
    excluded: list[str] = []
    unverified_marked: list[str] = []
    block_contributors: dict[str, tuple[str, ...]] = {}

    for b in outline.blocks:
        claim = get_claim(con, b.block_id)
        ok, _ = check_claim_publishable(claim)
        if public and not ok:
            excluded.append(b.block_id)
            continue
        if not ok and not public:
            unverified_marked.append(b.block_id)
        included.append(b)
        block_contributors[b.block_id] = b.contributor_interview_ids

    if dispatch_fn is not None:
        cw_blocks = [
            CreativeWriterBlock(block_id=b.block_id, block_kind="claim",
                                label=b.label, body=b.body, source_tier=b.source_tier)
            for b in included
        ]
        ctx = CreativeWriterContext(
            deliverable_title="Biography", deliverable_kind="biography_section",
            section_title="Biography", section_index=0, section_count=1, blocks=cw_blocks,
        )
        system, user = render_full_prompt(ctx)
        raw = dispatch_fn(prompt=user, system=system, role="creative_writer",
                          investigation_id=f"speak-biography-{project_id}")
        result = parse_creative_writer_response(
            raw if isinstance(raw, str) else getattr(raw, "text", str(raw)),
            known_block_ids={b.block_id for b in included},
        )
        prose = result.prose_text
        prose_provenance = result.prose_provenance
    else:
        # Deterministic stub (no live model): assemble cited prose from the
        # block bodies; mark the unverified ones explicitly. Never invent.
        paragraphs = []
        for b in included:
            mark = " [unverified]" if b.block_id in unverified_marked else ""
            paragraphs.append(b.body.strip() + mark)
        prose = "\n\n".join(paragraphs)
        prose_provenance = {index: [block.block_id] for index, block in enumerate(included)}

    score, _violations = score_voice_style(prose) if prose.strip() else (1.0, [])
    cited = tuple(sorted({iv for ivs in block_contributors.values() for iv in ivs}))
    return Draft(
        prose_text=prose,
        prose_provenance=prose_provenance,
        cited_interview_ids=cited,
        excluded_claim_ids=tuple(excluded),
        unverified_marked_claim_ids=tuple(unverified_marked),
        voice_style_score=score,
        voice_style_ok=score >= voice_style_threshold,
        block_contributors=block_contributors,
    )
