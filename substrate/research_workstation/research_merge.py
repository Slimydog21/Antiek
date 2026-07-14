"""Deep-research instance merge rules (read/research dual workstation).

Operator vision: spin deep research from a highlight into a floating window;
then either open full-screen, merge into the asset, draft-merge (combined
document before full commit), or select multiple completed sub-agents and
merge them as a cohesive collective unit.

Pure planning + document assembly. No DuckDB writes, no cascade launch.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Literal

from .note_twin import NoteTwin, TwinItem, build_note_twin, merge_twins, twin_to_markdown

MergeMode = Literal["into_asset", "draft_merge", "collective"]
InstanceStatus = Literal["pending", "running", "completed", "failed"]

_TERMINAL_OK = frozenset({"completed"})


class MergeError(ValueError):
    """Structural or precondition failure for a research merge."""


@dataclass(frozen=True)
class ResearchInstance:
    """One deep-research sub-agent instance (floating window payload).

    ``findings`` is free-form analysis text produced by the instance.
    ``twin`` is optional note-twin substrate for that instance's output.
    ``parent_asset_id`` is the book/doc/research asset the highlight came from.
    """

    instance_id: str
    status: InstanceStatus
    findings: str = ""
    twin: NoteTwin | None = None
    parent_asset_id: str | None = None
    highlight: str | None = None
    confidence: float = 0.5

    def __post_init__(self) -> None:
        iid = self.instance_id.strip()
        if not iid:
            raise MergeError("instance_id must be non-empty")
        object.__setattr__(self, "instance_id", iid)
        if self.status not in ("pending", "running", "completed", "failed"):
            raise MergeError(f"unknown status {self.status!r}")
        c = float(self.confidence)
        if c < 0.0 or c > 1.0:
            raise MergeError(f"confidence must be in [0,1], got {c}")
        object.__setattr__(self, "confidence", c)


@dataclass(frozen=True)
class MergePlan:
    """Immutable plan produced by ``plan_merge`` before any apply."""

    mode: MergeMode
    selected_instance_ids: tuple[str, ...]
    target_asset_id: str | None
    mutates_source: bool
    requires_operator_confirm: bool
    blocked_reason: str | None = None

    @property
    def is_executable(self) -> bool:
        return self.blocked_reason is None


@dataclass(frozen=True)
class MergedDocument:
    """Result of applying a merge plan (still pure — not persisted)."""

    document_id: str
    mode: MergeMode
    title: str
    body_markdown: str
    body_html: str
    merged_twin: NoteTwin | None
    source_instance_ids: tuple[str, ...]
    is_draft: bool
    metadata: dict[str, object] = field(default_factory=dict)


def plan_merge(
    instances: Sequence[ResearchInstance],
    mode: MergeMode,
    *,
    target_asset_id: str | None = None,
    selected_ids: Sequence[str] | None = None,
) -> MergePlan:
    """Validate and plan a merge. Never mutates instances.

    Rules (hard to vary):
    - ``into_asset``: ≥1 completed instance; requires ``target_asset_id``;
      mutates source → operator confirm required.
    - ``draft_merge``: ≥1 completed instance; never mutates source; produces
      a draft combined document (confirm optional but recommended).
    - ``collective``: ≥2 completed instances selected; merges as one unit;
      mutates source only if ``target_asset_id`` is set.
    - Failed/pending/running instances are never included; if none remain
      completed after filter, plan is blocked.
    """
    if mode not in ("into_asset", "draft_merge", "collective"):
        raise MergeError(
            f"unknown merge mode {mode!r}; "
            f"allowed: into_asset, draft_merge, collective"
        )

    by_id = {i.instance_id: i for i in instances}
    if selected_ids is None:
        chosen = [i for i in instances if i.status in _TERMINAL_OK]
    else:
        missing = [sid for sid in selected_ids if sid not in by_id]
        if missing:
            return MergePlan(
                mode=mode,
                selected_instance_ids=tuple(selected_ids),
                target_asset_id=target_asset_id,
                mutates_source=False,
                requires_operator_confirm=True,
                blocked_reason=f"unknown instance ids: {missing}",
            )
        chosen = [
            by_id[sid] for sid in selected_ids if by_id[sid].status in _TERMINAL_OK
        ]

    ids = tuple(i.instance_id for i in chosen)
    if not ids:
        return MergePlan(
            mode=mode,
            selected_instance_ids=(),
            target_asset_id=target_asset_id,
            mutates_source=False,
            requires_operator_confirm=True,
            blocked_reason="no completed research instances to merge",
        )

    if mode == "collective" and len(ids) < 2:
        return MergePlan(
            mode=mode,
            selected_instance_ids=ids,
            target_asset_id=target_asset_id,
            mutates_source=False,
            requires_operator_confirm=True,
            blocked_reason="collective merge requires at least 2 completed instances",
        )

    if mode == "into_asset":
        if not target_asset_id or not str(target_asset_id).strip():
            return MergePlan(
                mode=mode,
                selected_instance_ids=ids,
                target_asset_id=target_asset_id,
                mutates_source=True,
                requires_operator_confirm=True,
                blocked_reason="into_asset requires target_asset_id",
            )
        return MergePlan(
            mode=mode,
            selected_instance_ids=ids,
            target_asset_id=str(target_asset_id).strip(),
            mutates_source=True,
            requires_operator_confirm=True,
            blocked_reason=None,
        )

    # draft_merge always non-mutating; collective mutates only if target set
    mutates = mode == "collective" and bool(target_asset_id)
    return MergePlan(
        mode=mode,
        selected_instance_ids=ids,
        target_asset_id=(str(target_asset_id).strip() if target_asset_id else None),
        mutates_source=mutates,
        requires_operator_confirm=mutates or mode == "collective",
        blocked_reason=None,
    )


def _instances_for_plan(
    instances: Sequence[ResearchInstance],
    plan: MergePlan,
) -> list[ResearchInstance]:
    by_id = {i.instance_id: i for i in instances}
    return [by_id[iid] for iid in plan.selected_instance_ids]


def _merge_twins_from(chosen: Sequence[ResearchInstance]) -> NoteTwin | None:
    twins = [i.twin for i in chosen if i.twin is not None]
    if not twins:
        # Synthesize a twin from findings text as insights when no twin attached.
        synthetic: list[TwinItem] = []
        for inst in chosen:
            text = (inst.findings or "").strip()
            if text:
                synthetic.append(
                    TwinItem(
                        kind="insight",
                        text=text[:500],
                        confidence=inst.confidence,
                    )
                )
        if not synthetic:
            return None
        asset = chosen[0].parent_asset_id or "merged-research"
        return build_note_twin(asset, insights=synthetic)
    if len(twins) == 1:
        return twins[0]
    return merge_twins(twins)


def _body_markdown(chosen: Sequence[ResearchInstance], plan: MergePlan) -> str:
    lines = [
        f"# Research merge ({plan.mode})",
        "",
        f"Instances: {', '.join(plan.selected_instance_ids)}",
        "",
    ]
    if plan.target_asset_id:
        lines.append(f"Target asset: `{plan.target_asset_id}`")
        lines.append("")
    # Highest confidence first — deterministic secondary key by instance_id.
    ordered = sorted(chosen, key=lambda i: (-i.confidence, i.instance_id))
    for inst in ordered:
        lines.append(f"## Instance `{inst.instance_id}`")
        lines.append("")
        if inst.highlight:
            lines.append(f"**Highlight:** {inst.highlight}")
            lines.append("")
        body = (inst.findings or "").strip() or "_No findings recorded._"
        lines.append(body)
        lines.append("")
    twin = _merge_twins_from(chosen)
    if twin is not None:
        lines.append("---")
        lines.append("")
        lines.append(twin_to_markdown(twin))
    return "\n".join(lines).rstrip() + "\n"


def _body_html(chosen: Sequence[ResearchInstance], plan: MergePlan, md: str) -> str:
    # Minimal HTML projection of the merge (HTML-first vision). Not a full
    # markdown parser — structure is known, so we emit intentional HTML.
    # Every dynamic string (including instance_id) is escaped: untrusted ids
    # must not break out of attributes or inject markup (see regression test
    # test_body_html_escapes_hostile_instance_id).
    mode_esc = _esc_html(plan.mode)
    parts = [
        f'<article class="antiek-research-merge" data-mode="{mode_esc}">',
        f"<header><h1>Research merge ({mode_esc})</h1></header>",
    ]
    ordered = sorted(chosen, key=lambda i: (-i.confidence, i.instance_id))
    for inst in ordered:
        iid_esc = _esc_html(inst.instance_id)
        parts.append(
            f'<section class="instance" data-instance-id="{iid_esc}">'
        )
        parts.append(f"<h2>Instance {iid_esc}</h2>")
        if inst.highlight:
            parts.append(f"<p class=\"highlight\">{_esc_html(inst.highlight)}</p>")
        findings = (inst.findings or "").strip() or "No findings recorded."
        parts.append(f"<div class=\"findings\">{_esc_html(findings)}</div>")
        parts.append("</section>")
    twin = _merge_twins_from(chosen)
    if twin is not None:
        from .note_twin import twin_to_html

        parts.append(twin_to_html(twin))
    parts.append("</article>")
    return "".join(parts)


def _esc_html(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def apply_merge_plan(
    instances: Sequence[ResearchInstance],
    plan: MergePlan,
) -> MergedDocument:
    """Apply an executable merge plan into a ``MergedDocument``.

    Raises ``MergeError`` if the plan is blocked. Does not persist.
    """
    if not plan.is_executable:
        raise MergeError(
            f"cannot apply blocked merge plan: {plan.blocked_reason}"
        )
    chosen = _instances_for_plan(instances, plan)
    if len(chosen) != len(plan.selected_instance_ids):
        raise MergeError("plan instance ids do not match provided instances")

    md = _body_markdown(chosen, plan)
    html = _body_html(chosen, plan, md)
    twin = _merge_twins_from(chosen)
    is_draft = plan.mode == "draft_merge" or not plan.mutates_source
    doc_id_seed = plan.target_asset_id or "draft"
    document_id = f"merge:{plan.mode}:{doc_id_seed}:{'-'.join(plan.selected_instance_ids)}"
    title = {
        "into_asset": f"Merged into {plan.target_asset_id}",
        "draft_merge": "Draft research merge",
        "collective": "Collective multi-agent research merge",
    }[plan.mode]
    return MergedDocument(
        document_id=document_id,
        mode=plan.mode,
        title=title,
        body_markdown=md,
        body_html=html,
        merged_twin=twin,
        source_instance_ids=plan.selected_instance_ids,
        is_draft=is_draft,
        metadata={
            "mutates_source": plan.mutates_source,
            "requires_operator_confirm": plan.requires_operator_confirm,
            "target_asset_id": plan.target_asset_id,
        },
    )
