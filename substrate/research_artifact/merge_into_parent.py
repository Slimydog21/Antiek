"""Merge a research instance's findings back into its parent reading asset.

The 1:1 research→read back-merge (operator ask #3): *"I can choose to merge it
into the asset I am reading (or even create a draft version with the combined
document before fully merging)."*

**Distinct from the N-way collective merge** (#1833 draft / #1835 full): those
merge MANY instances into one fresh analysis. THIS weaves ONE completed
instance's structured findings back into its PARENT reading asset — enriching
the document the operator is already reading with the research that a highlight
spawned from it. It is the functional WRITE layer that the intent-only
``floating_research_draft_combined_document`` (#925) defers to.

**Non-destructive by default (draft).** The module NEVER mutates the source
parent HTML — it returns a NEW enriched document. ``merge_executed`` is always
``False`` from this pure module (the authority flip that commits the enriched
version as the asset's new body happens in the authorized routes layer, gated on
``operator_ack``). ``draft=True`` means "here is the combined document to review
before fully merging" — exactly the operator's draft-before-merge ask.

**The escaping boundary is the keystone.** The parent asset HTML is already-
trusted content (sanitized on write per #729) — re-escaping it would double-
escape and break the reading experience. Only the instance's LLM-produced
findings (insights, questions, synthesis) are escaped, because that is
untrusted model output. The boundary is explicit and tested: trusted passthrough
for the parent, ``html.escape`` for every interpolated finding.

**Provenance is real, never fabricated.** Every woven finding is attributed to
the instance via ``data-source-investigation`` and its node id; the enriched
document carries a provenance footer naming the instance + its source events.
Nothing is invented — an instance with no findings produces an honest empty
section, never fabricated prose.

**Output** is a single self-contained HTML document (ask #6) — the parent body
with a woven ``<section id="research-findings">`` block appended, clearly
attributed, so the operator can review the draft before the authority layer
commits it.
"""

from __future__ import annotations

import hashlib
import html
from dataclasses import dataclass

from substrate.research_artifact.schema import ResearchArtifactBody

# The authority tag — this module produces a DRAFT; it never commits the merge.
MERGE_AUTHORITY = "research_into_parent_draft_advisory"

# Sensible floors so the merge is never built from nothing.
MIN_PARENT_HTML_CHARS = 16


class ResearchIntoParentMergeError(ValueError):
    """Fail-closed: input that cannot produce an honest enriched document."""


@dataclass(frozen=True)
class EnrichedAssetDraft:
    """The enriched document: parent + woven instance findings (a DRAFT).

    ``merge_executed`` is ALWAYS ``False`` — this pure module produces a review-
    ready draft; the authority layer commits it. ``draft`` is ALWAYS ``True``.
    """

    parent_asset_id: str
    instance_investigation_id: str
    enriched_html: str
    findings_woven: int
    synthesis_woven: bool
    draft: bool
    merge_executed: bool
    authority: str
    draft_hash: str  # sha256 over canonical inputs (idempotency)


def _esc(s: str) -> str:
    """Escape ONE untrusted (LLM-produced) string for safe HTML interpolation."""
    return html.escape(s, quote=True)


def _canonical_draft_hash(
    parent_asset_id: str,
    parent_html: str,
    instance: ResearchArtifactBody,
) -> str:
    payload = (
        f"{parent_asset_id}\n"
        f"{parent_html}\n"
        f"{instance.investigation_id}\n"
        f"{instance.content_hash()}"
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _findings_section(instance: ResearchArtifactBody) -> tuple[str, int, bool]:
    """Render the instance's findings as an escaped, attributed HTML section.

    Returns (section_html, findings_count, synthesis_woven). Every interpolated
    string is escaped — these are LLM-produced, untrusted. Returns honest empty
    placeholders (never fabricated prose) when the instance has no findings.
    """
    inv = _esc(instance.investigation_id)
    parts: list[str] = [
        f'<section id="research-findings" data-source-investigation="{inv}">',
        f'<h2>Research findings &mdash; {_esc(instance.problem_question)}</h2>',
        f'<p class="kicker">Woven from investigation <code>{inv}</code>. '
        "Review this draft before merging into the asset.</p>",
    ]

    findings_count = 0
    if instance.insights:
        parts.append('<section id="merged-insights"><h3>Insights</h3>')
        for ins in instance.insights:
            text = (ins.text or "").strip()
            if not text:
                continue
            node = _esc(ins.node_id)
            source = _esc(ins.source_document_id or instance.investigation_id)
            parts.append(
                f'<div class="card" data-node-id="{node}" data-kind="insight" '
                f'data-source-document="{source}">'
                f"<p>{_esc(text)}</p>"
                f'<p class="tag">node {node} &middot; from {source}</p></div>'
            )
            findings_count += 1
        parts.append("</section>")
    else:
        parts.append('<section id="merged-insights"><h3>Insights</h3>'
                     '<p class="empty">No insights from this instance.</p></section>')

    if instance.open_questions:
        parts.append('<section id="merged-questions"><h3>Open questions</h3>')
        for q in instance.open_questions:
            text = (q.text or "").strip()
            if not text:
                continue
            node = _esc(q.node_id)
            parts.append(
                f'<div class="card" data-node-id="{node}" data-kind="question">'
                f"<p>{_esc(text)}</p>"
                f'<p class="tag">node {node}</p></div>'
            )
            findings_count += 1
        parts.append("</section>")
    else:
        parts.append('<section id="merged-questions"><h3>Open questions</h3>'
                     '<p class="empty">No open questions from this instance.</p></section>')

    synthesis_woven = False
    if instance.synthesis_withheld:
        parts.append('<section id="merged-synthesis"><h3>Synthesis</h3>'
                     '<p class="empty">Synthesis not available (&sect;9.0 guard).</p>'
                     "</section>")
    elif instance.synthesis_excerpt and instance.synthesis_excerpt.strip():
        parts.append('<section id="merged-synthesis"><h3>Synthesis</h3>'
                     f'<pre class="excerpt">{_esc(instance.synthesis_excerpt)}</pre>'
                     "</section>")
        synthesis_woven = True
    else:
        parts.append('<section id="merged-synthesis"><h3>Synthesis</h3>'
                     '<p class="empty">No synthesis from this instance.</p></section>')

    # Provenance footer: the enriched document traces to the instance + its events.
    events = ", ".join(_esc(e) for e in instance.source_event_ids) or "(none recorded)"
    parts.append(
        f'<footer>Enriched draft &middot; authority {MERGE_AUTHORITY} &middot; '
        f"merge_executed=false &middot; source events: {events}</footer>"
    )
    parts.append("</section>")
    return "".join(parts), findings_count, synthesis_woven


def merge_research_into_parent(
    *,
    parent_asset_id: str,
    parent_html: str,
    instance: ResearchArtifactBody,
    operator_ack: bool = False,
) -> EnrichedAssetDraft:
    """Weave a completed research instance's findings into the parent asset HTML.

    Non-destructive: ALWAYS returns a NEW enriched document; the source
    ``parent_html`` is never mutated. ``merge_executed`` is always ``False`` —
    this module produces the review-ready DRAFT; the authorized routes layer
    commits it after ``operator_ack``. The parent HTML is treated as trusted
    (already sanitized per #729); only the instance's LLM-produced findings are
    escaped at the interpolation boundary.
    """
    if not parent_asset_id.strip():
        raise ResearchIntoParentMergeError("parent_asset_id must be non-empty")
    if not instance.investigation_id.strip():
        raise ResearchIntoParentMergeError(
            "instance.investigation_id must be non-empty"
        )
    stripped_parent = parent_html.strip()
    if len(stripped_parent) < MIN_PARENT_HTML_CHARS:
        raise ResearchIntoParentMergeError(
            f"parent_html too short ({len(stripped_parent)} < "
            f"{MIN_PARENT_HTML_CHARS} chars) — no asset to merge into"
        )

    # The parent HTML is TRUSTED (sanitized on write). We pass it through
    # verbatim and append the escaped findings section before </body> (or at
    # the end if no </body> close). We do NOT re-escape the parent.
    section, findings_count, synthesis_woven = _findings_section(instance)

    close = "</body>"
    if close in stripped_parent:
        enriched = stripped_parent.replace(close, f"{section}\n{close}", 1)
    else:
        enriched = stripped_parent + "\n" + section

    draft_hash = _canonical_draft_hash(parent_asset_id, stripped_parent, instance)

    # operator_ack is recorded but NEVER flips merge_executed in this pure module.
    # The authority layer reads operator_ack to commit the draft as the asset's
    # new body; this module only produces the review-ready enriched document.
    _ = operator_ack  # recorded for the authority contract; not acted on here

    return EnrichedAssetDraft(
        parent_asset_id=parent_asset_id.strip(),
        instance_investigation_id=instance.investigation_id,
        enriched_html=enriched,
        findings_woven=findings_count,
        synthesis_woven=synthesis_woven,
        draft=True,
        merge_executed=False,
        authority=MERGE_AUTHORITY,
        draft_hash=draft_hash,
    )


__all__ = [
    "EnrichedAssetDraft",
    "MERGE_AUTHORITY",
    "MIN_PARENT_HTML_CHARS",
    "ResearchIntoParentMergeError",
    "merge_research_into_parent",
]
