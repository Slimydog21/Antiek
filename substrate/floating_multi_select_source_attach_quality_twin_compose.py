"""Floating multi-select + source quality → twin chase feed (pure).

live_dispatched / twin_written / remote_fetched / prompts_injected always False.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from substrate.floating_multi_select_source_attach_quality_compose import (
    FloatingMultiSelectSourceAttachQualityCompose,
    FloatingMultiSelectSourceAttachQualityComposeError,
    compose_floating_multi_select_source_attach_quality,
)
from substrate.twin_chase_analysis_feed_compose import (
    TwinChaseAnalysisFeedCompose,
    TwinChaseAnalysisFeedComposeError,
    compose_twin_chase_analysis_feed,
)


class FloatingMultiSelectSourceAttachQualityTwinComposeError(ValueError):
    """Fail-closed validation for multi-select source twin pack."""


@dataclass(frozen=True)
class FloatingMultiSelectSourceAttachQualityTwinCompose:
    session_id: str
    parent_asset_id: str
    multi_source: FloatingMultiSelectSourceAttachQualityCompose
    twin_feed: TwinChaseAnalysisFeedCompose
    pack_ready: bool
    live_dispatched: bool
    pack_dispatched: bool
    merge_executed: bool
    analysis_written: bool
    remote_fetched: bool
    twin_written: bool
    prompts_injected: bool
    store_mutated: bool
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "parent_asset_id": self.parent_asset_id,
            "multi_source": self.multi_source.to_dict(),
            "twin_feed": self.twin_feed.to_dict(),
            "pack_ready": self.pack_ready,
            "live_dispatched": False,
            "pack_dispatched": False,
            "merge_executed": False,
            "analysis_written": False,
            "remote_fetched": False,
            "twin_written": False,
            "prompts_injected": False,
            "store_mutated": False,
            "notes": list(self.notes),
            "authority": (
                "floating_multi_select_source_attach_quality_twin_compose_advisory"
            ),
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise FloatingMultiSelectSourceAttachQualityTwinComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def _derive_findings(
    sources: object,
    members: object,
    selected_instance_ids: object,
    cohesive_prompt: object,
) -> list[dict[str, Any]]:
    if not isinstance(sources, list):
        raise FloatingMultiSelectSourceAttachQualityTwinComposeError(
            "sources must be an array"
        )
    if not isinstance(members, list):
        raise FloatingMultiSelectSourceAttachQualityTwinComposeError(
            "members must be an array"
        )
    if not isinstance(selected_instance_ids, list):
        raise FloatingMultiSelectSourceAttachQualityTwinComposeError(
            "selected_instance_ids must be an array"
        )
    selected = {str(x) for x in selected_instance_ids}
    findings: list[dict[str, Any]] = []
    for s in sources:
        if not isinstance(s, dict):
            raise FloatingMultiSelectSourceAttachQualityTwinComposeError(
                "sources items must be objects"
            )
        sid = str(s.get("source_id", "")).strip()
        title = str(s.get("title", "")).strip()
        if not sid or not title:
            raise FloatingMultiSelectSourceAttachQualityTwinComposeError(
                "sources items need source_id and title"
            )
        findings.append(
            {"source_id": f"src-{sid}", "body": title, "kind": "data"}
        )
    for m in members:
        if not isinstance(m, dict):
            continue
        iid = str(m.get("instance_id", "")).strip()
        if iid not in selected:
            continue
        hl = str(m.get("highlight") or "").strip()
        prior = str(m.get("prior_prompt") or "").strip()
        findings_list = m.get("findings")
        first_finding = ""
        if isinstance(findings_list, list) and findings_list:
            first_finding = str(findings_list[0]).strip()
        body = hl or prior or first_finding or iid
        kind = "insight" if first_finding else "question"
        findings.append(
            {"source_id": f"inst-{iid}", "body": body, "kind": kind}
        )
    prompt = str(cohesive_prompt or "").strip()
    if prompt:
        findings.append(
            {
                "source_id": "cohesive-prompt",
                "body": prompt,
                "kind": "question",
            }
        )
    return findings


def compose_floating_multi_select_source_attach_quality_twin(
    *,
    session_id: object,
    parent_asset_id: object,
    members: object,
    selected_instance_ids: object,
    pack_mode: object,
    cohesive_prompt: object,
    operator_ack: object,
    requested_families: object,
    sources: object,
    quality_overall: object,
    would_exceed: object,
    extra_context: object | None = None,
    analysis_kind: object | None = None,
    extra_findings: object | None = None,
    citations: object | None = None,
    derive_citations_from_sources: object | None = None,
    quality_floor: object | None = None,
    operator_override: object | None = None,
    require_both: object | None = None,
    existing_twin_asset_id: object | None = None,
    analysis_excerpt: object | None = None,
    mark_for_prompt_context: object | None = None,
    twin_findings: object | None = None,
    require_both_with_twin: object | None = None,
) -> FloatingMultiSelectSourceAttachQualityTwinCompose:
    """Multi-select+sources + twin feed. Never dispatches/writes twin."""
    if not isinstance(operator_ack, bool):
        raise FloatingMultiSelectSourceAttachQualityTwinComposeError(
            "operator_ack must be an explicit boolean"
        )
    session = _require_nonempty(session_id, field="session_id")
    parent = _require_nonempty(parent_asset_id, field="parent_asset_id")

    require_twin = (
        True if require_both_with_twin is None else require_both_with_twin
    )
    if not isinstance(require_twin, bool):
        raise FloatingMultiSelectSourceAttachQualityTwinComposeError(
            "require_both_with_twin must be boolean when set"
        )

    mark_prompt = (
        True if mark_for_prompt_context is None else mark_for_prompt_context
    )
    if not isinstance(mark_prompt, bool):
        raise FloatingMultiSelectSourceAttachQualityTwinComposeError(
            "mark_for_prompt_context must be boolean when set"
        )

    notes: list[str] = [
        "live_dispatched=false · pack_dispatched=false · merge_executed=false",
        "remote_fetched=false · twin_written=false · prompts_injected=false",
    ]

    try:
        multi_source = compose_floating_multi_select_source_attach_quality(
            session_id=session,
            parent_asset_id=parent,
            members=members,
            selected_instance_ids=selected_instance_ids,
            pack_mode=pack_mode,
            cohesive_prompt=cohesive_prompt,
            operator_ack=operator_ack,
            requested_families=requested_families,
            sources=sources,
            quality_overall=quality_overall,
            would_exceed=would_exceed,
            extra_context=extra_context,
            analysis_kind=analysis_kind,
            extra_findings=extra_findings,
            citations=citations,
            derive_citations_from_sources=derive_citations_from_sources,
            quality_floor=quality_floor,
            operator_override=operator_override,
            require_both=require_both,
        )
    except FloatingMultiSelectSourceAttachQualityComposeError as e:
        raise FloatingMultiSelectSourceAttachQualityTwinComposeError(
            str(e)
        ) from e
    notes.extend(f"[multi_source] {n}" for n in multi_source.notes)

    if twin_findings is not None:
        if not isinstance(twin_findings, list):
            raise FloatingMultiSelectSourceAttachQualityTwinComposeError(
                "twin_findings must be an array when set"
            )
        findings = twin_findings
        notes.append(f"twin_findings={len(findings)} caller-supplied")
    else:
        findings = _derive_findings(
            sources, members, selected_instance_ids, cohesive_prompt
        )
        notes.append(
            f"twin_findings={len(findings)} derived from "
            "sources+selected members+prompt"
        )

    try:
        twin_feed = compose_twin_chase_analysis_feed(
            session_id=session,
            parent_asset_id=parent,
            findings=findings,
            operator_ack=operator_ack,
            analysis_excerpt=analysis_excerpt,
            existing_twin_asset_id=existing_twin_asset_id,
            mark_for_prompt_context=mark_prompt,
        )
    except TwinChaseAnalysisFeedComposeError as e:
        raise FloatingMultiSelectSourceAttachQualityTwinComposeError(
            str(e)
        ) from e
    notes.extend(f"[twin_feed] {n}" for n in twin_feed.notes)

    if require_twin:
        pack_ready = (
            multi_source.pack_ready is True
            and twin_feed.feed_ready is True
            and operator_ack is True
        )
    else:
        pack_ready = operator_ack is True and (
            multi_source.pack_ready is True or twin_feed.feed_ready is True
        )

    if pack_ready:
        notes.append(
            "pack_ready=true — multi-select+sources + twin feed ready; still pure"
        )
    else:
        notes.append(
            "pack_ready=false — multi-source, twin feed, or operator_ack gate open"
        )

    if (
        multi_source.live_dispatched is not False
        or multi_source.remote_fetched is not False
        or twin_feed.twin_written is not False
        or twin_feed.prompts_injected is not False
    ):
        raise FloatingMultiSelectSourceAttachQualityTwinComposeError(
            "invariant: honesty flags must remain false"
        )

    notes.extend(
        (
            "live_dispatched=false",
            "pack_dispatched=false",
            "merge_executed=false",
            "analysis_written=false",
            "remote_fetched=false",
            "twin_written=false",
            "prompts_injected=false",
            "store_mutated=false",
        )
    )

    return FloatingMultiSelectSourceAttachQualityTwinCompose(
        session_id=session,
        parent_asset_id=parent,
        multi_source=multi_source,
        twin_feed=twin_feed,
        pack_ready=pack_ready,
        live_dispatched=False,
        pack_dispatched=False,
        merge_executed=False,
        analysis_written=False,
        remote_fetched=False,
        twin_written=False,
        prompts_injected=False,
        store_mutated=False,
        notes=tuple(notes),
        authority=(
            "floating_multi_select_source_attach_quality_twin_compose_advisory"
        ),
    )


def format_floating_multi_select_source_attach_quality_twin_summary(
    c: FloatingMultiSelectSourceAttachQualityTwinCompose,
) -> str:
    return (
        f"pack_ready={c.pack_ready} · "
        f"multi_source_ready={c.multi_source.pack_ready} · "
        f"twin_feed_ready={c.twin_feed.feed_ready} · "
        f"findings={c.twin_feed.finding_count} · "
        f"live_dispatched=false · twin_written=false · remote_fetched=false"
    )


__all__ = [
    "FloatingMultiSelectSourceAttachQualityTwinCompose",
    "FloatingMultiSelectSourceAttachQualityTwinComposeError",
    "compose_floating_multi_select_source_attach_quality_twin",
    "format_floating_multi_select_source_attach_quality_twin_summary",
]
