"""Recursive twin search → prompt context pack (pure).

twin_written, remote_index_queried, record_persisted, prompts_injected,
live_router_authorized always False.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from substrate.recursive_twin_intelligent_search import (
    TwinIntelligentSearchError,
    TwinSearchResult,
    search_twin_substrate,
)
from substrate.recursive_twin_note_taker_compose import (
    RecursiveTwinNoteTakerCompose,
    RecursiveTwinNoteTakerComposeError,
    compose_recursive_twin_note_taker,
)
from substrate.workstation_record_prompt_model_decision_compose import (
    WorkstationRecordPromptModelDecisionCompose,
    WorkstationRecordPromptModelDecisionComposeError,
    compose_workstation_record_prompt_model_decision,
)


class RecursiveTwinSearchPromptContextComposeError(ValueError):
    """Fail-closed validation for twin search prompt context pack."""


@dataclass(frozen=True)
class RecursiveTwinSearchPromptContextCompose:
    session_id: str
    parent_asset_id: str
    twin_propose: RecursiveTwinNoteTakerCompose
    search: TwinSearchResult
    prompt_pack: WorkstationRecordPromptModelDecisionCompose
    pack_ready: bool
    twin_written: bool
    remote_index_queried: bool
    record_persisted: bool
    prompts_injected: bool
    live_router_authorized: bool
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "parent_asset_id": self.parent_asset_id,
            "twin_propose": self.twin_propose.to_dict(),
            "search": self.search.to_dict(),
            "prompt_pack": self.prompt_pack.to_dict(),
            "pack_ready": self.pack_ready,
            "twin_written": False,
            "remote_index_queried": False,
            "record_persisted": False,
            "prompts_injected": False,
            "live_router_authorized": False,
            "notes": list(self.notes),
            "authority": (
                "recursive_twin_search_prompt_context_compose_advisory"
            ),
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RecursiveTwinSearchPromptContextComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def _hits_to_session_records(search: TwinSearchResult) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for hit in search.hits:
        for i, snip in enumerate(hit.snippets):
            is_question = (
                "questions" in hit.matched_fields
                and ("?" in snip or hit.matched_fields[0] == "questions")
            )
            records.append(
                {
                    "record_id": f"{hit.twin_id}-s{i}",
                    "kind": "question" if is_question else "insight",
                    "body": snip,
                    "source_ref": hit.parent_asset_id,
                }
            )
    return records


def compose_recursive_twin_search_prompt_context(
    *,
    session_id: object,
    parent_asset_id: object,
    source_excerpt: object,
    twin_records: object,
    search_query: object,
    user_prompt: object,
    selected_model_id: object,
    models: object,
    daily_cap_usd: object,
    spent_usd: object,
    operator_ack: object,
    existing_twin_asset_id: object | None = None,
    focus_questions: object | None = None,
    search_limit: object | None = None,
    projected_cost_usd_high: object | None = None,
    projected_cost_usd_low: object | None = None,
    bench_bests: object | None = None,
    focus_task: object | None = None,
    nd_shadow: object | None = None,
) -> RecursiveTwinSearchPromptContextCompose:
    """Twin propose + search + prompt pack. Never writes/injects/routes."""
    if not isinstance(operator_ack, bool):
        raise RecursiveTwinSearchPromptContextComposeError(
            "operator_ack must be an explicit boolean"
        )
    session = _require_nonempty(session_id, field="session_id")
    parent = _require_nonempty(parent_asset_id, field="parent_asset_id")

    notes: list[str] = [
        "twin_written=false — twin note-taker is propose/scaffold only",
        "remote_index_queried=false — twin search is pure local corpus",
        "record_persisted=false · prompts_injected=false · live_router_authorized=false",
    ]

    try:
        twin_propose = compose_recursive_twin_note_taker(
            parent_asset_id=parent,
            source_excerpt=source_excerpt,
            operator_ack=operator_ack,
            existing_twin_asset_id=existing_twin_asset_id,
            focus_questions=focus_questions,
        )
    except RecursiveTwinNoteTakerComposeError as e:
        raise RecursiveTwinSearchPromptContextComposeError(str(e)) from e
    notes.extend(f"[twin] {n}" for n in twin_propose.notes)

    if not isinstance(twin_records, list):
        raise RecursiveTwinSearchPromptContextComposeError(
            "twin_records must be an array"
        )
    lim = 20 if search_limit is None else search_limit
    try:
        search = search_twin_substrate(
            query=search_query,
            records=twin_records,
            limit=lim,
        )
    except TwinIntelligentSearchError as e:
        raise RecursiveTwinSearchPromptContextComposeError(str(e)) from e
    notes.extend(f"[search] {n}" for n in search.notes)
    notes.append(f"search_hits={len(search.hits)}")

    session_records = _hits_to_session_records(search)
    if len(session_records) == 0 and operator_ack:
        notes.append(
            "no twin search hits — seed scaffold insight from source_excerpt "
            "(caller text only)"
        )
        excerpt = _require_nonempty(source_excerpt, field="source_excerpt")
        session_records.append(
            {
                "record_id": "scaffold-excerpt",
                "kind": "insight",
                "body": excerpt[:500],
                "source_ref": parent,
            }
        )

    try:
        prompt_pack = compose_workstation_record_prompt_model_decision(
            session_id=session,
            parent_asset_id=parent,
            records=session_records,
            user_prompt=user_prompt,
            selected_model_id=selected_model_id,
            models=models,
            daily_cap_usd=daily_cap_usd,
            spent_usd=spent_usd,
            operator_ack=operator_ack,
            projected_cost_usd_high=projected_cost_usd_high,
            projected_cost_usd_low=projected_cost_usd_low,
            bench_bests=bench_bests,
            focus_task=focus_task,
            nd_shadow=nd_shadow,
        )
    except WorkstationRecordPromptModelDecisionComposeError as e:
        raise RecursiveTwinSearchPromptContextComposeError(str(e)) from e
    notes.extend(f"[prompt] {n}" for n in prompt_pack.notes)

    pack_ready = (
        twin_propose.twin_propose_ready is True
        and prompt_pack.pack_ready is True
        and operator_ack is True
    )
    if pack_ready:
        notes.append(
            "pack_ready=true — twin propose + search + prompt context advisory pack"
        )
    else:
        notes.append(
            "pack_ready=false — twin, search, prompt pack, or operator_ack gate open"
        )

    if (
        twin_propose.twin_written is not False
        or twin_propose.prompts_injected is not False
        or search.remote_index_queried is not False
        or prompt_pack.record_persisted is not False
        or prompt_pack.prompts_injected is not False
        or prompt_pack.live_router_authorized is not False
    ):
        raise RecursiveTwinSearchPromptContextComposeError(
            "invariant: honesty flags must remain false"
        )

    notes.extend(
        (
            "twin_written=false",
            "remote_index_queried=false",
            "record_persisted=false",
            "prompts_injected=false",
            "live_router_authorized=false",
        )
    )

    return RecursiveTwinSearchPromptContextCompose(
        session_id=session,
        parent_asset_id=parent,
        twin_propose=twin_propose,
        search=search,
        prompt_pack=prompt_pack,
        pack_ready=pack_ready,
        twin_written=False,
        remote_index_queried=False,
        record_persisted=False,
        prompts_injected=False,
        live_router_authorized=False,
        notes=tuple(notes),
        authority="recursive_twin_search_prompt_context_compose_advisory",
    )


def format_recursive_twin_search_prompt_context_summary(
    c: RecursiveTwinSearchPromptContextCompose,
) -> str:
    return (
        f"pack_ready={c.pack_ready} · hits={len(c.search.hits)} · "
        f"twin_propose_ready={c.twin_propose.twin_propose_ready} · "
        f"would_exceed={c.prompt_pack.would_exceed} · "
        f"twin_written=false · remote_index_queried=false · prompts_injected=false"
    )


__all__ = [
    "RecursiveTwinSearchPromptContextCompose",
    "RecursiveTwinSearchPromptContextComposeError",
    "compose_recursive_twin_search_prompt_context",
    "format_recursive_twin_search_prompt_context_summary",
]
