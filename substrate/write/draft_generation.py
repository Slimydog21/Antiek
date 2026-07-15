"""Draft generation from OutlineBlocks (specs/write/ SPR-06).

Wires the existing ``roles/creative_writer`` role to generate prose from
attached OutlineBlocks (SPR-01) at section/paragraph granularity, steered
by per-unit style prompts, with **every claim cited** and the output
passing the ``voice_style`` anti-slop gate.

This module owns the deterministic substrate around generation — the part
that makes "provenance is the moat" structural rather than hopeful:

- ``build_creative_writer_context`` — OutlineBlocks → ``CreativeWriterContext``
  (resolves each block's text: the node label for graph-node blocks, the
  inline content for user-originated ones).
- ``validate_generated_citations`` — extracts inline ``[b: <id>]`` citations
  + the ``prose_provenance`` map, then flags: paragraphs with NO citation
  (``unsupported`` — surfaced to the writer, never asserted as fact) and
  citations to blocks that were never attached (``fabricated`` — the
  failure the parser alone can't catch).
- ``enforce_voice_gate`` — scores prose with ``voice_style`` (§5.5). The
  gate WINS: a style prompt can never push output below it.
- ``generate_section`` — the orchestration. A section with NO blocks
  returns a GAP (never fabricated prose). The LLM call is injected
  (``dispatch_fn``) so the citation/gate/gap logic is testable without a
  live model; the default adapter routes through ``substrate/dispatch``.

What needs a live model (and is therefore not unit-tested here): the
actual prose the model returns. The deterministic contracts above are
what protect the moat regardless of which model runs.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

try:
    from ..voice_style.rubric import score_voice_style
except ImportError:  # pragma: no cover — direct-script fallback
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(_here)))
    from substrate.voice_style.rubric import score_voice_style  # type: ignore[no-redef]

from roles.creative_writer.parser import (
    CreativeWriterResult,
    parse_creative_writer_response,
)
from roles.creative_writer.prompt import (
    AdjacentSection,
    CreativeWriterBlock,
    CreativeWriterContext,
    render_full_prompt,
)

from .outline_block import OutlineBlock

# The §5.5 anti-slop gate (mirrors quality_gate.check_voice_style and
# style_profile.VOICE_STYLE_GATE). The gate wins over any style prompt.
VOICE_STYLE_GATE = 0.70

# Inline citation token the creative_writer system prompt mandates:
#   "The hypothesis holds [b: node-abc-123]."
_CITATION_RE = re.compile(r"\[b:\s*([^\]]+?)\s*\]")

# A "DispatchFn" takes (system_prompt, user_prompt) and returns the raw
# model response (expected to contain the role's JSON). Injectable so the
# orchestration is testable without a live model.
DispatchFn = Callable[[str, str], str]


# ---------------------------------------------------------------------------
# Block → context
# ---------------------------------------------------------------------------


def _block_text(block: OutlineBlock, *, node_label_resolver: Callable[[str], str] | None = None) -> str:
    """Resolve a block's renderable text. graph-node blocks resolve their
    label via the resolver (the node is the content of record);
    user-originated blocks carry inline content."""
    if block.provenance_kind == "graph_node":
        from .composition_draft import composition_snapshot_text
        snapshot_text = composition_snapshot_text(block.metadata, node_id=block.node_id)
        if snapshot_text is not None:
            return snapshot_text
        if node_label_resolver and block.node_id:
            return node_label_resolver(block.node_id)
        return block.node_id or ""
    return block.content or ""


def build_creative_writer_context(
    *,
    deliverable_title: str,
    deliverable_kind: str,
    section_title: str,
    section_index: int,
    section_count: int,
    blocks: Sequence[OutlineBlock],
    style_guide: str = "",
    adjacent_sections: Sequence[AdjacentSection] = (),
    node_label_resolver: Callable[[str], str] | None = None,
) -> CreativeWriterContext:
    """Build the creative_writer context from OutlineBlocks. The block_id
    carried into the prompt is the OutlineBlock's node_id (graph-node) or
    outline_block_id (user-originated) — the id the citation must name.

    ``adjacent_sections`` carries the deliverable's other sections so the
    role can keep a multi-section deliverable coherent — prior sections
    supply their prose (so the model does not repeat them), upcoming
    sections supply only a title (so the model can hand off to them).
    Empty for a single-section deliverable."""
    cw_blocks: list[CreativeWriterBlock] = []
    for b in blocks:
        cite_id = b.node_id if (b.provenance_kind == "graph_node" and b.node_id) else b.outline_block_id  # noqa: E501
        body = _block_text(b, node_label_resolver=node_label_resolver)
        cw_blocks.append(CreativeWriterBlock(
            block_id=cite_id, block_kind=b.block_kind,
            label=(body[:60] if body else b.block_kind), body=body,
        ))
    return CreativeWriterContext(
        deliverable_title=deliverable_title, deliverable_kind=deliverable_kind,
        section_title=section_title, section_index=section_index,
        section_count=section_count, blocks=cw_blocks, style_guide=style_guide,
        adjacent_sections=list(adjacent_sections),
    )


# ---------------------------------------------------------------------------
# Citation validation — the moat
# ---------------------------------------------------------------------------


def extract_inline_citations(prose_text: str) -> list[str]:
    """Extract block ids from inline ``[b: <id>]`` citations, in order."""
    return [m.strip() for m in _CITATION_RE.findall(prose_text)]


def _paragraphs(prose_text: str) -> list[str]:
    return [p.strip() for p in re.split(r"\n\s*\n", prose_text.strip()) if p.strip()]


# A paragraph this short (after stripping citations) is treated as
# structural (heading, transition) and not required to carry a citation.
_MIN_CLAIM_CHARS = 40


@dataclass(frozen=True)
class CitationReport:
    """Which paragraphs are supported, which claims are unsupported, and
    which citations were fabricated. The moat made legible."""

    supported_paragraphs: list[int]
    unsupported_paragraphs: list[int]
    fabricated_citations: list[str]
    uncited_blocks: list[str]
    cited_block_ids: list[str]

    @property
    def all_claims_cited(self) -> bool:
        return not self.unsupported_paragraphs and not self.fabricated_citations


def validate_generated_citations(
    result: CreativeWriterResult,
    *,
    attached_block_ids: set[str],
) -> CitationReport:
    """Validate that every claim cites an attached block. Paragraphs with
    a substantive claim and no citation are flagged ``unsupported``;
    citations to non-attached blocks are flagged ``fabricated``."""
    supported: list[int] = []
    unsupported: list[int] = []
    fabricated: set[str] = set()
    all_cited: set[str] = set()

    paras = _paragraphs(result.prose_text)
    for idx, para in enumerate(paras):
        inline = extract_inline_citations(para)
        prov = result.prose_provenance.get(idx, [])
        cited_here = set(inline) | set(prov)
        all_cited |= cited_here
        for cid in cited_here:
            if cid not in attached_block_ids:
                fabricated.add(cid)
        # Substantive paragraph with no citation → unsupported claim.
        stripped = _CITATION_RE.sub("", para).strip()
        if not cited_here and len(stripped) >= _MIN_CLAIM_CHARS:
            unsupported.append(idx)
        elif cited_here:
            supported.append(idx)

    uncited_blocks = sorted(attached_block_ids - {c for c in all_cited if c in attached_block_ids})
    return CitationReport(
        supported_paragraphs=supported,
        unsupported_paragraphs=unsupported,
        fabricated_citations=sorted(fabricated),
        uncited_blocks=uncited_blocks,
        cited_block_ids=sorted(c for c in all_cited if c in attached_block_ids),
    )


# ---------------------------------------------------------------------------
# Voice/style gate — the gate wins
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GateResult:
    score: float
    passed: bool
    violations: list[str]


def enforce_voice_gate(prose_text: str) -> GateResult:
    """Score prose against the §5.5 anti-slop gate. ``passed`` is the
    authoritative signal — a style prompt can never override it."""
    score, violations = score_voice_style(prose_text)
    return GateResult(score=round(score, 4), passed=score >= VOICE_STYLE_GATE, violations=violations)


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GenerationResult:
    status: str  # 'generated' | 'gap' | 'gate_failed' | 'invalid'
    section_id: str | None
    prose_text: str
    citation_report: CitationReport | None
    gate: GateResult | None
    detail: str = ""
    # The role's per-paragraph provenance (paragraph_index → [block_ids]).
    # Empty for gap/invalid (nothing parsed). On a 'generated' result this is
    # the map the X-ray persists + reads back (Write SPR-09 M3). Kept here so
    # the caller does not need a second parse of the raw model output.
    prose_provenance: dict[int, list[str]] = field(default_factory=dict)


def generate_section(
    *,
    ctx: CreativeWriterContext,
    dispatch_fn: DispatchFn,
    section_id: str | None = None,
) -> GenerationResult:
    """Generate one section's prose. The LLM call is injected.

    - No blocks → a GAP (never fabricated prose; rigor #3).
    - Otherwise: render → dispatch → parse → validate citations →
      enforce the gate. The gate wins: sub-threshold prose returns
      ``gate_failed`` (caller regenerates), never ships.
    """
    if not ctx.blocks:
        return GenerationResult(
            status="gap", section_id=section_id, prose_text="",
            citation_report=None, gate=None,
            detail="no blocks attached — left as a gap, not fabricated",
        )

    system, user = render_full_prompt(ctx)
    raw = dispatch_fn(system, user)

    attached = {b.block_id for b in ctx.blocks}
    try:
        result = parse_creative_writer_response(raw, known_block_ids=attached)
    except Exception as exc:  # parser raises on malformed/unknown-id output
        return GenerationResult(
            status="invalid", section_id=section_id, prose_text="",
            citation_report=None, gate=None,
            detail=f"generation output failed validation: {exc}",
        )

    report = validate_generated_citations(result, attached_block_ids=attached)
    gate = enforce_voice_gate(result.prose_text)
    if not gate.passed:
        return GenerationResult(
            status="gate_failed", section_id=section_id, prose_text=result.prose_text,
            citation_report=report, gate=gate,
            detail=(
                f"voice_style gate failed (score {gate.score} < {VOICE_STYLE_GATE}) — "
                "the gate wins over the style prompt; regenerate"
            ),
            # No provenance carried out of a gate-failed result: it never ships
            # and never persists, so surfacing its map would be a draft that
            # looks kept when it isn't.
        )
    detail = "generated"
    if report.unsupported_paragraphs:
        detail += (
            f"; {len(report.unsupported_paragraphs)} unsupported paragraph(s) "
            "flagged for the writer (not asserted as fact)"
        )
    if report.fabricated_citations:
        detail += f"; {len(report.fabricated_citations)} fabricated citation(s) flagged"
    return GenerationResult(
        status="generated", section_id=section_id, prose_text=result.prose_text,
        citation_report=report, gate=gate, detail=detail,
        # The per-paragraph provenance the X-ray persists + reads back (M3).
        prose_provenance=dict(result.prose_provenance),
    )


# ---------------------------------------------------------------------------
# Persistence — make the X-ray's paragraph→blocks link durable (SPR-09 M3)
# ---------------------------------------------------------------------------


def persist_section_draft(
    con: Any,
    *,
    section_id: str,
    deliverable_id: str,
    result: GenerationResult,
    report: CitationReport,
    investigation_id: str = "__operator__",
) -> str | None:
    """Persist a successful generation's prose + per-paragraph provenance, then
    emit the audit event — both through the single-writer funnel.

    The X-ray (paragraph → driving blocks → chunks → documents) needs
    ``prose_provenance`` to survive the request that generated it. We write the
    ``deliverable_sections`` row (``update_section_prose`` — already SHIPPED)
    AND append a ``SECTION_DRAFT_GENERATED`` event in the SAME locked
    connection, mirroring ``patch_section_prose`` (Sprint 15). The
    paragraph→blocks link therefore EXISTS in the graph (a persisted row + a
    persisted event), not just on screen — the §9 moat made auditable.

    Only call this for a ``generated`` result: a gate_failed / invalid draft
    never ships, so it must never persist provenance (no half-written draft).

    Returns the emitted event_id (or None when events are disabled). Routes the
    table write through ``con`` (a ``LockedConnection`` from
    ``runtime/db_lock``) — no second writer, single-writer invariant intact.
    """
    if result.status != "generated":
        raise ValueError(
            f"persist_section_draft only persists a 'generated' result; "
            f"got {result.status!r} (a gate_failed/invalid draft never ships)"
        )
    # Lazy imports: keep this module importable without the substrate event log
    # / graph ops on a bare script path (mirrors the module's other fallbacks).
    try:
        from ..graph.ops import update_section_prose
    except ImportError:  # pragma: no cover — direct-script fallback
        from substrate.graph.ops import update_section_prose
    from substrate.schemas.events import SectionDraftGeneratedPayload
    from substrate.write.event_outbox import (
        build_typed_envelope,
        dispatch_pending_best_effort,
        enqueue_event,
        event_for_operation,
        eventful_transaction,
    )

    # JSON object keys are strings — store paragraph indices as string keys so
    # the persisted map round-trips losslessly (the reader parses back to int).
    prov: dict[str, list[str]] = {
        str(idx): list(blocks) for idx, blocks in result.prose_provenance.items()
    }
    operation_digest = hashlib.sha256(
        json.dumps(
            {
                "section_id": section_id,
                "prose_text": result.prose_text,
                "provenance": prov,
                "unsupported": report.unsupported_paragraphs,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    operation_id = f"section.draft:{section_id}:{operation_digest}"
    existing_event = event_for_operation(con, operation_id)
    if existing_event is not None:
        row = con.execute(
            "SELECT prose_text, prose_provenance FROM deliverable_sections WHERE section_id=?",
            [section_id],
        ).fetchone()
        persisted_provenance = json.loads(row[1]) if row and row[1] else None
        if row is None or row[0] != result.prose_text or persisted_provenance != prov:
            raise RuntimeError("stored draft operation disagrees with section state")
        dispatch_pending_best_effort(con, investigation_id)
        return existing_event.event_id
    event = build_typed_envelope(
        investigation_id,
        SectionDraftGeneratedPayload(
            section_id=section_id,
            deliverable_id=deliverable_id,
            prose_provenance=prov,
            paragraph_count=len(_paragraphs(result.prose_text)),
            cited_block_ids=list(report.cited_block_ids),
            all_claims_cited=report.all_claims_cited,
            unsupported_paragraph_count=len(report.unsupported_paragraphs),
            gate_score=result.gate.score if result.gate else None,
        ),
        role="creative_writer",
        policy_id=f"operator/{deliverable_id}",
    )
    with eventful_transaction(con, investigation_id):
        update_section_prose(
            con, section_id=section_id,
            prose_text=result.prose_text, prose_provenance=prov,
            unsupported_paragraphs=set(report.unsupported_paragraphs),
            mutation_origin="generated",
        )
        enqueue_event(
            con,
            operation_id=operation_id,
            aggregate_kind="deliverable_section",
            aggregate_id=section_id,
            event=event,
        )
    dispatch_pending_best_effort(con, investigation_id)
    return event.event_id


def default_dispatch_fn(*, investigation_id: str = "__operator__") -> DispatchFn:
    """The production dispatch adapter: routes the creative_writer prompt
    through ``substrate/dispatch``. Requires ``creative_writer`` in the
    dispatch config's ``role_tiers`` and provider credentials — hence the
    live generation path is not unit-tested here. The prompt combines the
    system + user (the router takes a single prompt string)."""
    def _fn(system: str, user: str) -> str:
        from substrate.dispatch.router import dispatch
        result = dispatch(
            f"{system}\n\n{user}", role="creative_writer",
            investigation_id=investigation_id,
        )
        return getattr(result, "text", "") or getattr(result, "content", "")
    return _fn
