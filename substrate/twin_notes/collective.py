"""Collective twin pack — multi-instance deep-research as one cohesive unit.

Operator vision: select multiple completed (or in-progress) sub-agent twin
documents and engage them as a single prompt context — without dispatching
models from this module.

Unlike ``compose_analysis_html`` (same-parent HTML draft only), a collective
pack **allows cross-parent** twins so researches spun from different assets
can still be prompted together. Each twin retains parent/provenance labels.

Pure: no network, no LLM, no graph writes.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from substrate.twin_notes.store import TwinDocument, TwinNotesError


@dataclass(frozen=True)
class CollectivePack:
    """Plain-text pack ready for an operator- or host-supplied prompt."""

    instruction: str
    twin_ids: list[str]
    parent_asset_ids: list[str]
    pack_text: str
    insight_count: int
    question_count: int
    notes: list[str] = field(default_factory=list)


def _section(doc: TwinDocument, index: int) -> str:
    lines: list[str] = [
        f"### Twin {index + 1}: {doc.twin_id}",
        f"parent_asset_id: {doc.parent_asset_id}",
    ]
    if doc.source_label:
        lines.append(f"source_label: {doc.source_label}")
    if doc.merged_from:
        lines.append("merged_from: " + ", ".join(doc.merged_from))
    if doc.insights:
        lines.append("insights:")
        for i in doc.insights:
            lines.append(f"- {i}")
    else:
        lines.append("insights: (none)")
    if doc.questions:
        lines.append("questions:")
        for q in doc.questions:
            lines.append(f"- {q}")
    else:
        lines.append("questions: (none)")
    return "\n".join(lines)


def build_collective_pack(
    twins: Sequence[TwinDocument],
    *,
    instruction: str = "",
) -> CollectivePack:
    """Build a cohesive prompt pack from one or more twins.

    Raises :class:`TwinNotesError` when ``twins`` is empty.
    """
    docs = list(twins)
    if not docs:
        raise TwinNotesError("collective pack requires at least one twin")

    instr = (instruction or "").strip()
    twin_ids = [d.twin_id for d in docs]
    parents = []
    seen_p: set[str] = set()
    for d in docs:
        if d.parent_asset_id not in seen_p:
            seen_p.add(d.parent_asset_id)
            parents.append(d.parent_asset_id)

    insight_n = sum(len(d.insights) for d in docs)
    question_n = sum(len(d.questions) for d in docs)

    parts: list[str] = [
        "# Collective deep-research pack",
        "",
        "You are engaging multiple twin research notes as one cohesive unit.",
        "Preserve attribution: answers should reference twin_id / parent when relevant.",
        "",
    ]
    if instr:
        parts.extend(["## Operator instruction", instr, ""])
    else:
        parts.extend(
            [
                "## Operator instruction",
                "(none provided — synthesize across the twins below)",
                "",
            ]
        )
    parts.append("## Twins")
    parts.append("")
    for i, doc in enumerate(docs):
        parts.append(_section(doc, i))
        parts.append("")

    notes = [
        "collective pack is advisory context only — this module does not dispatch a model",
        f"twin_count={len(docs)} distinct_parents={len(parents)}",
    ]
    if len(parents) > 1:
        notes.append(
            "cross-parent collective: twins span multiple parent assets; provenance labels retained"
        )

    return CollectivePack(
        instruction=instr,
        twin_ids=twin_ids,
        parent_asset_ids=parents,
        pack_text="\n".join(parts).rstrip() + "\n",
        insight_count=insight_n,
        question_count=question_n,
        notes=notes,
    )


__all__ = ["CollectivePack", "build_collective_pack"]
