"""Collective deep-research → draft analysis writer (pure mechanical combination).

The functional WRITE layer the operator's ask #3 names: merge multiple completed
deep-research instances into a single combined document ("create a draft version
with the combined document before fully merging").

This is the **DRAFT** mode — pure mechanical combination, NO LLM dispatch.
It concatenates the instances' insights + open_questions + synthesis_excerpt +
caller findings into a structured HTML scaffold, grouped by source instance with
attribution headers. Deterministic, free, fast, and idempotent.

Hard-to-vary invariants (each is a test):

1. **No invented content.** Only real instance fields + caller findings. Missing
   synthesis → honest placeholder ("instance X synthesis pending"), never fabricated.
2. **Provenance completeness.** Every output carries ``source_instance_ids`` linking
   to all inputs; the hash is deterministic over the canonical input (idempotency).
3. **HTML-native + escaped.** All interpolated content is HTML-escaped (``_esc``,
   the render.py convention). The combined document is self-contained HTML.
4. **Same-parent cohesion.** ``ResearchArtifactBody`` carries no parent field, so
   the pure layer cannot infer per-instance parents. Cohesion is therefore the
   caller's contract: the instances arrive as an already-curated same-parent set
   (the intent layer upstream guarantees this). When the caller supplies
   ``instance_parent_asset_ids``, cohesion IS enforced — any instance attesting
   a different parent raises ``CollectiveAnalysisError`` and no merged document is
   produced. The pure layer never silently merges instances from different parents.
5. **Empty-instance honesty.** An instance with no insights/questions/synthesis is
   represented honestly (empty placeholders), not silently dropped.

The FULL-analysis mode (LLM-synthesized prose, budget-gated) lives in a future
authorized layer behind the budget gate + operator spend-consent. This draft layer
is the deterministic substrate it composes onto.
"""

from __future__ import annotations

import hashlib
import html
from dataclasses import dataclass, field

from substrate.research_artifact.schema import ResearchArtifactBody


class CollectiveAnalysisError(ValueError):
    """Fail-closed validation: parent mismatch, empty instance set, or invalid input."""


@dataclass(frozen=True)
class InstanceContribution:
    """One source instance's contribution to the merged draft."""

    investigation_id: str
    problem_question: str
    insights: list[str]
    open_questions: list[str]
    synthesis_excerpt: str | None
    complete: bool  # whether the instance passed DeepResearchComplete (honest flag)


@dataclass(frozen=True)
class CollectiveDraftAnalysis:
    """The merged draft: combined HTML + provenance + deterministic hash."""

    parent_asset_id: str
    analysis_id: str
    source_instance_ids: tuple[str, ...]
    combined_html: str
    draft: bool = True  # always True for the draft writer
    findings_hash: str = ""  # sha256 over canonical input (idempotency)
    instance_contributions: tuple[InstanceContribution, ...] = field(default_factory=tuple)


def _esc(s: str) -> str:
    return html.escape(s, quote=True)


def _instance_from_body(body: ResearchArtifactBody, *, complete: bool = True) -> InstanceContribution:
    return InstanceContribution(
        investigation_id=body.investigation_id,
        problem_question=body.problem_question,
        insights=[ins.text for ins in body.insights],
        open_questions=[q.text for q in body.open_questions],
        synthesis_excerpt=body.synthesis_excerpt if not body.synthesis_withheld else None,
        complete=complete,
    )


def compose_draft_analysis(
    *,
    parent_asset_id: str,
    instances: list[ResearchArtifactBody],
    findings: list[str] | None = None,
    instance_complete_flags: dict[str, bool] | None = None,
    instance_parent_asset_ids: dict[str, str] | None = None,
) -> CollectiveDraftAnalysis:
    """Merge completed research instances into a combined draft HTML document.

    Pure mechanical combination — no LLM dispatch, no network, no budget gate.
    Deterministic: the same inputs always produce the same output (idempotent).
    """

    if not instances:
        raise CollectiveAnalysisError("at least one source instance is required")
    if not parent_asset_id.strip():
        raise CollectiveAnalysisError("parent_asset_id must be non-empty")

    # Same-parent cohesion: enforced when the caller attests per-instance parents.
    # ResearchArtifactBody carries no parent field, so the pure layer can only
    # verify cohesion when given the data — it never silently mis-attributes.
    parent_map = instance_parent_asset_ids or {}
    for body in instances:
        attested = parent_map.get(body.investigation_id)
        if attested is not None and attested != parent_asset_id:
            raise CollectiveAnalysisError(
                f"instance {body.investigation_id} attests parent "
                f"{attested!r} which differs from requested {parent_asset_id!r}"
            )

    complete_flags = instance_complete_flags or {}
    contributions: list[InstanceContribution] = []
    for body in instances:
        contributions.append(
            _instance_from_body(body, complete=complete_flags.get(body.investigation_id, True))
        )

    # Provenance: all instances under the same parent.
    source_ids = tuple(c.investigation_id for c in contributions)
    caller_findings = findings or []

    findings_hash = _canonical_hash(parent_asset_id, source_ids, caller_findings, contributions)
    analysis_id = f"collective-draft-{findings_hash[:16]}"
    combined_html = _render_combined_html(
        parent_asset_id=parent_asset_id,
        contributions=contributions,
        findings=caller_findings,
        analysis_id=analysis_id,
        findings_hash=findings_hash,
    )

    return CollectiveDraftAnalysis(
        parent_asset_id=parent_asset_id,
        analysis_id=analysis_id,
        source_instance_ids=source_ids,
        combined_html=combined_html,
        draft=True,
        findings_hash=findings_hash,
        instance_contributions=tuple(contributions),
    )


def _render_combined_html(
    *,
    parent_asset_id: str,
    contributions: list[InstanceContribution],
    findings: list[str],
    analysis_id: str,
    findings_hash: str,
) -> str:
    """Render the merged draft as self-contained, fully-escaped HTML."""

    parts: list[str] = [
        "<!doctype html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>Collective draft — {_esc(parent_asset_id)}</title>",
        "<style>",
        "body { font-family: -apple-system, BlinkMacSystemFont, sans-serif; "
        "line-height: 1.55; color: #1c1917; background: #fafaf9; margin: 0; padding: 24px; }",
        "main { max-width: 760px; margin: 0 auto; }",
        "h1 { font-family: Charter, Georgia, serif; font-size: 1.7rem; }",
        ".kicker { color: #57534e; font-size: 0.85rem; }",
        "section { border: 1px solid #e7e5e4; background: #fff; padding: 16px 20px; "
        "margin: 16px 0; border-radius: 6px; }",
        ".card { margin: 8px 0; padding: 8px 12px; border-left: 3px solid #1d4ed8; "
        "background: #fafaf9; }",
        ".tag { font-size: 0.75rem; color: #57534e; }",
        ".empty { color: #57534e; font-style: italic; }",
        ".pending { color: #b45309; font-style: italic; }",
        "footer { margin-top: 32px; font-size: 0.8rem; color: #57534e; }",
        "</style>",
        "</head>",
        "<body>",
        "<main>",
        f'<p class="kicker">Collective draft analysis · ANT-AHT · {_esc(analysis_id)}</p>',
        f"<h1>Merged analysis of {_esc(parent_asset_id)}</h1>",
        f'<p class="kicker">{len(contributions)} source instance(s): '
        + ", ".join(_esc(c.investigation_id) for c in contributions)
        + "</p>",
    ]

    # Per-instance sections
    for i, c in enumerate(contributions, start=1):
        parts.append("<section>")
        parts.append(
            f'<h2>Instance {i}: {_esc(c.investigation_id)}</h2>'
        )
        parts.append(f'<p class="tag">question: {_esc(c.problem_question)}</p>')
        if not c.complete:
            parts.append('<p class="pending">⚠ instance not DeepResearchComplete — content may be partial</p>')

        # Insights
        parts.append("<h3>Insights</h3>")
        if c.insights:
            for ins in c.insights:
                parts.append(f'<div class="card"><p>{_esc(ins)}</p></div>')
        else:
            parts.append('<p class="empty">No insights from this instance.</p>')

        # Open questions
        parts.append("<h3>Open questions</h3>")
        if c.open_questions:
            for q in c.open_questions:
                parts.append(f'<div class="card"><p>{_esc(q)}</p></div>')
        else:
            parts.append('<p class="empty">No open questions from this instance.</p>')

        # Synthesis
        parts.append("<h3>Synthesis excerpt</h3>")
        if c.synthesis_excerpt:
            parts.append(f"<p>{_esc(c.synthesis_excerpt)}</p>")
        elif c.complete:
            parts.append('<p class="empty">No synthesis from this instance.</p>')
        else:
            parts.append('<p class="pending">Synthesis pending completion.</p>')

        parts.append("</section>")

    # Caller findings (the operator's manual input)
    parts.append("<section>")
    parts.append("<h2>Operator findings</h2>")
    if findings:
        for f in findings:
            parts.append(f'<div class="card"><p>{_esc(f)}</p></div>')
    else:
        parts.append('<p class="empty">No operator findings attached.</p>')
    parts.append("</section>")

    # Provenance footer
    parts.append("<footer>")
    parts.append(f'<p>Provenance: parent={_esc(parent_asset_id)} · '
                 f'instances={len(contributions)} · draft=True</p>')
    parts.append(f'<p class="tag">findings_hash={_esc("sha256:" + findings_hash)}</p>')
    parts.append("</footer>")

    parts.append("</main>")
    parts.append("</body>")
    parts.append("</html>")
    return "\n".join(parts)


def _canonical_hash(
    parent_asset_id: str,
    source_ids: tuple[str, ...],
    findings: list[str],
    contributions: list[InstanceContribution],
) -> str:
    """Deterministic sha256 over the canonical input (idempotency proof)."""
    import json

    payload = {
        "parent_asset_id": parent_asset_id,
        "source_instance_ids": list(source_ids),
        "findings": findings,
        "instances": [
            {
                "investigation_id": c.investigation_id,
                "problem_question": c.problem_question,
                "insights": c.insights,
                "open_questions": c.open_questions,
                "synthesis_excerpt": c.synthesis_excerpt,
                "complete": c.complete,
            }
            for c in contributions
        ],
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


__all__ = [
    "CollectiveAnalysisError",
    "CollectiveDraftAnalysis",
    "InstanceContribution",
    "compose_draft_analysis",
]
