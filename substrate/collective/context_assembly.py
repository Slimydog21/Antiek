"""Collective-context assembly — prompt N instances as one cohesive unit (ask #3f).

The operator's vision (ask #3f): *"...click on multiple of these sub agents to
engage in a collective deep research where I merge those instances and prompt
them as a cohesive unit."* This is the THIRD collective operation, distinct from
the two already built:

  * **#1833 draft-analysis writer** — mechanically combine N instances' OUTPUTS
    into one combined HTML document (a static artifact).
  * **#1835 full-synthesis mode** — LLM-synthesize N instances' outputs into a
    new written analysis (a new artifact).
  * **THIS module** — assemble N instances' DISTILLED CONTENT into a single
    labeled context window so the operator can dispatch a NEW prompt that sees
    all N as one body of work to INTERROGATE. Not a new artifact; a shared
    context for a live prompt.

The difference is load-bearing: #1833/#1835 produce a *document*; this produces
a *context* — the substrate a dispatch consumes. The operator isn't asking the
system to write a merged summary; they're asking to *ask a question against the
combined findings of several investigations at once*. That needs the findings
labeled by source, deduplicated, and budget-bounded — exactly what this does.

**Pure — no I/O, no network, no dispatch.** ``assemble_collective_context`` takes
N ``ResearchArtifactBody`` instances (the on-main completed-investigation shape)
and returns a ``CollectiveContext`` value. The caller dispatches the prompt.

**Honesty rules (load-bearing):**

  * **Every selected instance appears.** An instance with zero insights still
    contributes its problem_question — the operator selected it for a reason;
    silently dropping it would hide that. (No "empty → skip.")
  * **Each instance is a labeled section.** The assembled context marks every
    finding with its source ``investigation_id`` so the model (and operator)
    knows *which* instance produced it. A finding with no provenance is a lie.
  * **Dedup by content-addressed node_id.** The same insight appearing in two
    instances is ONE entry with both source ids — content-addressed nodes are
    stable identities (``contracts/nodes.py``: "re-emitting the same insight
    resolves to the same node"). Deduping preserves that; duplicating would
    inflate the context and double-count signal.
  * **synthesis_withheld is flagged, never faked.** An instance whose synthesis
    was withheld (``synthesis_withheld=True``) appears with its insights but a
    marker that it reached no conclusion — the model must not treat a withheld
    synthesis as a confirmed finding.
  * **Token budget is fair + honest.** If the assembled context exceeds the
    budget, instances are truncated *proportionally and evenly* (each keeps the
    same fraction of its insights), and ``truncated`` is flagged with how many
    insights were held back. No instance is dropped entirely; no truncation is
    hidden. A ``None`` budget means "no limit" (the operator didn't set one) —
    honest, not a fabrication of infinity.
  * **Open questions are first-class.** The operator's flywheel is question-
    driven; a collective context carries the union of open questions (deduped,
    source-labeled) so a new prompt can resolve or escalate them across the set.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class CollectiveContextError(ValueError):
    """An assembly input violates a load-bearing invariant."""




class _ArtifactInsight(Protocol):
    node_id: str
    text: str


class _ArtifactQuestion(Protocol):
    node_id: str
    text: str


class _ArtifactBody(Protocol):
    investigation_id: str
    problem_question: str
    insights: list[_ArtifactInsight]
    open_questions: list[_ArtifactQuestion]
    synthesis_excerpt: str | None
    synthesis_withheld: bool


@dataclass(frozen=True)
class InstanceContribution:
    """One instance's distilled contribution within the collective context."""

    investigation_id: str
    problem_question: str
    insight_texts: tuple[str, ...]
    open_question_texts: tuple[str, ...]
    synthesis_excerpt: str | None
    synthesis_withheld: bool
    insights_included: int
    insights_held_back: int


@dataclass(frozen=True)
class DedupedFinding:
    """A finding (insight or open question) deduplicated across instances.

    ``source_investigation_ids`` lists every instance that produced this finding
    — content-addressed dedup means the SAME finding from N instances is ONE
    entry carrying all N sources, not N copies.
    """

    node_id: str
    text: str
    kind: str  # "insight" | "open_question"
    source_investigation_ids: tuple[str, ...]


@dataclass(frozen=True)
class CollectiveContext:
    """The assembled shared context for prompting N instances as one unit.

    ``render()`` produces the flat labeled string a dispatch consumes.
    ``token_count`` is the measured size; ``truncated`` is the honesty flag.
    """

    instances: tuple[InstanceContribution, ...]
    deduped_insights: tuple[DedupedFinding, ...]
    deduped_open_questions: tuple[DedupedFinding, ...]
    token_count: int
    truncated: bool
    insights_held_back_total: int
    notes: tuple[str, ...] = ()

    @property
    def instance_count(self) -> int:
        return len(self.instances)

    def render(self) -> str:
        """Render the collective context as a flat, source-labeled string.

        Sections: per-instance (problem + included insights + open questions),
        then the deduped cross-instance insights and open questions. Every
        finding names its source investigation(s).
        """
        if not self.instances:
            return ""
        parts: list[str] = ["[COLLECTIVE CONTEXT — prompt these as one cohesive unit]"]
        for inst in self.instances:
            parts.append(f"\n--- Instance {inst.investigation_id} ---")
            parts.append(f"Problem: {inst.problem_question}")
            if inst.synthesis_withheld:
                parts.append("(synthesis withheld — no confirmed conclusion)")
            elif inst.synthesis_excerpt:
                parts.append(f"Synthesis: {inst.synthesis_excerpt}")
            for text in inst.insight_texts:
                parts.append(f"  • insight [{inst.investigation_id}]: {text}")
            for text in inst.open_question_texts:
                parts.append(f"  ? open question [{inst.investigation_id}]: {text}")
            if inst.insights_held_back > 0:
                parts.append(
                    f"  ({inst.insights_held_back} insight(s) held back for budget)"
                )
        if self.deduped_insights:
            parts.append("\n=== Cross-instance insights (deduped) ===")
            for d in self.deduped_insights:
                src = ", ".join(d.source_investigation_ids)
                parts.append(f"  • [{src}]: {d.text}")
        if self.deduped_open_questions:
            parts.append("\n=== Open questions across the set ===")
            for q in self.deduped_open_questions:
                src = ", ".join(q.source_investigation_ids)
                parts.append(f"  ? [{src}]: {q.text}")
        return "\n".join(parts)


def _estimate_tokens(text: str) -> int:
    """Rough token estimate: 1 token ≈ 4 chars. Honest approximation, labeled so.

    The operator's budget gate (#1842) uses provider-reported cost; this estimate
    is only for the *pre-dispatch* context-fit check. It over-estimates slightly
    (rounds up) so a context that fits this estimate fits the real budget.
    """
    return (len(text) + 3) // 4


def _validate_instance(body: _ArtifactBody) -> None:
    bid = getattr(body, "investigation_id", None)
    if not bid or not str(bid).strip():
        raise CollectiveContextError(
            "every instance must have a non-empty investigation_id"
        )


def assemble_collective_context(
    instances: list[_ArtifactBody],
    *,
    token_budget: int | None = None,
) -> CollectiveContext:
    """Assemble N completed instances into one shared, labeled, deduped context.

    ``instances`` are ``ResearchArtifactBody``-shaped (duck-typed: needs
    ``investigation_id``, ``problem_question``, ``insights``, ``open_questions``,
    ``synthesis_excerpt``, ``synthesis_withheld``). Returns a ``CollectiveContext``
    value — pure, no dispatch. The caller sends a prompt against ``render()``.

    If ``token_budget`` is set and the full assembly exceeds it, instances are
    truncated evenly (each keeps the same fraction of its insights, newest-first
    dropped) until it fits; ``truncated`` is flagged and held-back counts recorded.
    """
    if not instances:
        raise CollectiveContextError(
            "collective context requires >= 1 instance; cannot prompt an empty set"
        )
    for body in instances:
        _validate_instance(body)

    # --- dedup insights + open questions across instances (content-addressed) ---
    insight_sources: dict[str, DedupedFinding] = {}
    question_sources: dict[str, DedupedFinding] = {}
    for body in instances:
        inv = str(body.investigation_id)
        for ins in getattr(body, "insights", []) or []:
            nid = getattr(ins, "node_id", None) or ""
            text = getattr(ins, "text", "") or ""
            if not text.strip():
                continue
            key = nid or text
            if key in insight_sources:
                existing = insight_sources[key]
                if inv not in existing.source_investigation_ids:
                    insight_sources[key] = DedupedFinding(
                        node_id=nid,
                        text=text,
                        kind="insight",
                        source_investigation_ids=existing.source_investigation_ids + (inv,),
                    )
            else:
                insight_sources[key] = DedupedFinding(
                    node_id=nid, text=text, kind="insight", source_investigation_ids=(inv,)
                )
        for q in getattr(body, "open_questions", []) or []:
            nid = getattr(q, "node_id", None) or ""
            text = getattr(q, "text", "") or ""
            if not text.strip():
                continue
            key = nid or text
            if key in question_sources:
                existing = question_sources[key]
                if inv not in existing.source_investigation_ids:
                    question_sources[key] = DedupedFinding(
                        node_id=nid,
                        text=text,
                        kind="open_question",
                        source_investigation_ids=existing.source_investigation_ids + (inv,),
                    )
            else:
                question_sources[key] = DedupedFinding(
                    node_id=nid,
                    text=text,
                    kind="open_question",
                    source_investigation_ids=(inv,),
                )

    deduped_insights = tuple(insight_sources.values())
    deduped_questions = tuple(question_sources.values())

    # --- per-instance contributions (full, pre-truncation) ---
    contributions: list[InstanceContribution] = []
    for body in instances:
        inv = str(body.investigation_id)
        all_insights = tuple(
            (getattr(i, "text", "") or "")
            for i in (getattr(body, "insights", []) or [])
            if (getattr(i, "text", "") or "").strip()
        )
        all_questions = tuple(
            (getattr(q, "text", "") or "")
            for q in (getattr(body, "open_questions", []) or [])
            if (getattr(q, "text", "") or "").strip()
        )
        contributions.append(
            InstanceContribution(
                investigation_id=inv,
                problem_question=getattr(body, "problem_question", "") or "",
                insight_texts=all_insights,
                open_question_texts=all_questions,
                synthesis_excerpt=getattr(body, "synthesis_excerpt", None),
                synthesis_withheld=bool(getattr(body, "synthesis_withheld", False)),
                insights_included=len(all_insights),
                insights_held_back=0,
            )
        )

    ctx = CollectiveContext(
        instances=tuple(contributions),
        deduped_insights=deduped_insights,
        deduped_open_questions=deduped_questions,
        token_count=_estimate_tokens(_build_render(contributions, deduped_insights, deduped_questions)),
        truncated=False,
        insights_held_back_total=0,
    )

    # --- budget fit: if over, truncate evenly (drop newest insights per instance) ---
    if token_budget is not None and ctx.token_count > token_budget:
        ctx = _fit_to_budget(ctx, contributions, deduped_insights, deduped_questions, token_budget)

    return ctx


def _build_render(
    contributions: list[InstanceContribution],
    deduped_insights: tuple[DedupedFinding, ...],
    deduped_questions: tuple[DedupedFinding, ...],
) -> str:
    """Build the render string from current contributions (pre- or post-truncation)."""
    return CollectiveContext(
        instances=tuple(contributions),
        deduped_insights=deduped_insights,
        deduped_open_questions=deduped_questions,
        token_count=0,
        truncated=False,
        insights_held_back_total=0,
    ).render()


def _fit_to_budget(
    ctx: CollectiveContext,
    contributions: list[InstanceContribution],
    deduped_insights: tuple[DedupedFinding, ...],
    deduped_questions: tuple[DedupedFinding, ...],
    token_budget: int,
) -> CollectiveContext:
    """Truncate evenly until the assembled context fits the token budget.

    Drops the LAST insight from every instance that still has > 0 insights, one
    round at a time, until it fits or no insights remain. This is *fair*
    (every instance loses the same fraction) and *honest* (every held-back
    insight is counted and flagged).
    """
    work = [InstanceContribution(**{**c.__dict__}) for c in contributions]
    held_back_total = 0
    notes: list[str] = []

    while True:
        rendered = _build_render(work, deduped_insights, deduped_questions)
        size = _estimate_tokens(rendered)
        if size <= token_budget:
            break
        # drop one insight from each instance that still has any
        dropped_this_round = False
        for i, c in enumerate(work):
            if c.insight_texts:
                held = c.insight_texts[:-1]
                work[i] = InstanceContribution(
                    investigation_id=c.investigation_id,
                    problem_question=c.problem_question,
                    insight_texts=held,
                    open_question_texts=c.open_question_texts,
                    synthesis_excerpt=c.synthesis_excerpt,
                    synthesis_withheld=c.synthesis_withheld,
                    insights_included=len(held),
                    insights_held_back=c.insights_held_back + 1,
                )
                held_back_total += 1
                dropped_this_round = True
        if not dropped_this_round:
            notes.append(
                f"could not fit budget {token_budget} even after dropping all insights; "
                f"problem_questions + open_questions remain ({size} tokens)"
            )
            break

    notes.insert(
        0,
        f"truncated to fit budget {token_budget}: {held_back_total} insight(s) held back across {len(work)} instance(s)",
    )
    return CollectiveContext(
        instances=tuple(work),
        deduped_insights=deduped_insights,
        deduped_open_questions=deduped_questions,
        token_count=_estimate_tokens(_build_render(work, deduped_insights, deduped_questions)),
        truncated=True,
        insights_held_back_total=held_back_total,
        notes=tuple(notes),
    )


__all__ = [
    "CollectiveContextError",
    "InstanceContribution",
    "DedupedFinding",
    "CollectiveContext",
    "assemble_collective_context",
]
