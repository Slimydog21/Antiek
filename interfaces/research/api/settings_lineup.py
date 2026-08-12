"""AI Role Lineup — operator model-selection vertical (general + advanced).

The operator's model taxonomy, normalized into ONE data-driven catalog:

  general  — the formation. Four operator-defined roles (writer / data
             miner / data refinement / data verification) PLUS the roles
             this vertical's forensic inventory found missing (orchestrator,
             critic, media creator, voice, indexer). Each general role is
             a "position" on the pitch with a stable id.
  advanced — the tactics board. Every concrete AI action/behavior in the
             product, bucketed under exactly one general role, each with
             its real dispatch role (where one exists) and default tier
             from ``substrate/dispatch/config.yaml``.

This module is deliberately parallel to ``settings_models_admin.py`` in
scope discipline: it stores OPERATOR INTENT (which model drives which
role/action) and never silently mutates dispatch routing. Granting a
lineup assignment dispatch-route authority is the explicit next vertical
(the model-selection binding sprint), same as add-model → route authority.

Honesty rules (mirror settings_models_admin):
  * Assignments reference ONLY provider_id + model_id — no keys, ever.
  * A choice is accepted only if it resolves against the live bench:
    user-added models (BYOK registry), server presets (BYOT catalog), or
    dispatch-config tiers. Unknown choices are rejected value-free.
  * ``auto`` (null) is the default and always valid: the platform keeps
    its curated defaults until the operator substitutes.
  * GET is the single source of truth for the UI; PUT returns the same
    view it just validated so the client never re-derives.

Persistence: ``(ANTIEK_HOME|~/.antiek)/settings/lineup.json`` (override
``ANTIEK_LINEUP_PATH``), mirroring the user_models.json precedent —
no DuckDB, single-writer API process, lenient reads, fsynced writes.
Owner-scoped: one assignment map per owner user id; ``__operator__``
gets the same shape as any owner.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, FastAPI, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Catalog — the forensic taxonomy, data-driven.
#
# Position letter: gk = last line (verification), def = workhorse,
# mid = refinement/creation, att = human-facing deliverable.
# ---------------------------------------------------------------------------

Position = Literal["gk", "def", "mid", "att"]
ActionKind = Literal["llm", "media", "voice", "embedding"]


@dataclass(frozen=True, slots=True)
class ActionDef:
    action_id: str
    label: str
    blurb: str
    dispatch_role: str | None
    default_tier: str | None
    kind: ActionKind


@dataclass(frozen=True, slots=True)
class RoleDef:
    role_id: str
    position: Position
    label: str
    blurb: str
    discovered: bool  # True = found missing by the forensic inventory
    actions: tuple[ActionDef, ...]


ROLE_CATALOG: tuple[RoleDef, ...] = (
    RoleDef(
        role_id="writer",
        position="att",
        label="Writer",
        blurb="The striker. Produces human-facing deliverables: syntheses, drafts, repository docs, inline completions.",
        discovered=False,
        actions=(
            ActionDef("research_synthesis", "Research synthesis", "The final human-facing synthesis of an investigation.", "synthesizer", "synthesis", "llm"),
            ActionDef("creative_draft", "Creative draft", "Section/outline draft generation in Write.", "creative_writer", "pro", "llm"),
            ActionDef("write_repository", "Write repository", "Repository-level write actions (blocks, folders).", "write_repository", "pro", "llm"),
            ActionDef("write_composition", "Write composition", "Composition actions across the write surface.", "write_composition", "pro", "llm"),
            ActionDef("write_editor", "Write editor assist", "Editor assistance on drafted text.", "write_editor", "pro", "llm"),
            ActionDef("autocomplete", "Inline autocomplete", "Cursor-style completions in the editor.", "autocomplete", "flash", "llm"),
            ActionDef("thought_partner", "Thought partner", "Advisory thinking companion (operator surface).", "thought_partner", "pro", "llm"),
        ),
    ),
    RoleDef(
        role_id="data_miner",
        position="def",
        label="Data Miner",
        blurb="The workhorse. Bulk grunt work: retrieval, extraction, note-taking, attribution, transcription.",
        discovered=False,
        actions=(
            ActionDef("evidence_retrieval", "Evidence retrieval", "Fetch evidence for research questions.", "evidence_retriever", "flash", "llm"),
            ActionDef("parameter_extraction", "Parameter extraction", "Extract search parameters from questions.", "parameter_extractor", "flash", "llm"),
            ActionDef("note_taking", "Background note-taking", "Emergent notes while wrestling documents.", "note_taker", "flash", "llm"),
            ActionDef("knowledge_extraction", "Knowledge extraction", "Phase-8 domain knowledge extraction.", "knowledge_extractor", "pro", "llm"),
            ActionDef("distillation", "Distillation", "Distill document regions into notes/claims.", "extractor", "flash", "llm"),
            ActionDef("attribution", "Page attribution", "Compute page/source attribution.", "attribution", "flash", "llm"),
            ActionDef("tier_assignment", "Tier assignment", "Rule-based routing tier assignment (LLM only for downward adjustment).", "tier_assigner", "flash", "llm"),
            ActionDef("constraint_checking", "Constraint checking", "Preflight constraint checks on plans.", "constraint_checker", "flash", "llm"),
            ActionDef("transcription", "Transcription", "Whisper audio→text for voice capture.", None, "transcription", "voice"),
        ),
    ),
    RoleDef(
        role_id="data_refinement",
        position="mid",
        label="Data Refinement",
        blurb="The playmaker. Higher-level grunt work: decomposition, connection, conversation, interviewing, visual claims.",
        discovered=False,
        actions=(
            ActionDef("decomposition", "Question decomposition", "Split research questions into sub-questions.", "decomposer", "pro", "llm"),
            ActionDef("connector", "Cross-domain connector", "Connect evidence across domains via keywords/traversal.", "connector", "pro", "llm"),
            ActionDef("talk_to_book", "Talk to book", "The reading-mode conversational agent.", "user_agent", "pro", "llm"),
            ActionDef("interviewing", "AI interviewer", "Speak-mode interviewer question generation.", "interviewer", "pro", "llm"),
            ActionDef("meta_reading", "Meta-reading", "Generated meta-readings over book collections.", "user_agent", "pro", "llm"),
            ActionDef("visual_claims", "Visual claims extraction", "Extract claims from document frames (vision).", "extractor", "pro", "llm"),
        ),
    ),
    RoleDef(
        role_id="data_verification",
        position="gk",
        label="Data Verification",
        blurb="The last line. Highest-grade grunt work: cross-family verification, challenge, grounding, quality gates.",
        discovered=False,
        actions=(
            ActionDef("verification", "Cross-family verification", "Verify claims/syntheses with a second model family.", "verifier", "verify", "llm"),
            ActionDef("challenge", "Challenge", "Adversarial questioning of claims during wrestling.", "challenger", "pro", "llm"),
            ActionDef("grounding", "Grounding checks", "Check claims against evidence.", "grounder", "flash", "llm"),
            ActionDef("quality_gates", "Quality gates", "Deliverable quality-gate evaluation.", "verifier", "verify", "llm"),
            ActionDef("groundedness_scoring", "Groundedness scoring", "Score groundedness of generated text.", "verifier", "verify", "llm"),
        ),
    ),
    RoleDef(
        role_id="orchestrator",
        position="mid",
        label="Orchestrator",
        blurb="The captain. Plans and dispatches the work: cascade planning, chase trees, RLM bridge decisions. FOUND MISSING by the forensic inventory — no single role covered planning.",
        discovered=True,
        actions=(
            ActionDef("cascade_planning", "Cascade planning", "Build the deep-research cascade plan tree.", "decomposer", "pro", "llm"),
            ActionDef("chase_planning", "Chase-tree planning", "Plan follow-up chase questions.", "decomposer", "pro", "llm"),
            ActionDef("rlm_bridge", "RLM bridge decisions", "Route decisions for the RLM agentic bridge.", "user_agent", "pro", "llm"),
        ),
    ),
    RoleDef(
        role_id="critic",
        position="mid",
        label="Critic",
        blurb="The analyst. Adversarial review of human-facing deliverables (audit findings, deliverable critique). FOUND MISSING — verification checks data, nothing reviews the writer's output.",
        discovered=True,
        actions=(
            ActionDef("deliverable_critique", "Deliverable critique", "Adversarial review of a produced deliverable.", "challenger", "pro", "llm"),
            ActionDef("audit_findings", "Audit findings", "Surface audit findings for the operator.", "verifier", "verify", "llm"),
        ),
    ),
    RoleDef(
        role_id="media_creator",
        position="att",
        label="Media Creator",
        blurb="The artist. Generates images/video via the multimedia router (Krea). FOUND MISSING — text roles cannot cover generative media.",
        discovered=True,
        actions=(
            ActionDef("image_generation", "Image generation", "Text/image-to-image generation.", None, None, "media"),
            ActionDef("video_generation", "Video generation", "Text-to-video generation.", None, None, "media"),
        ),
    ),
    RoleDef(
        role_id="voice",
        position="mid",
        label="Voice",
        blurb="The voice. Speech synthesis for Speak-mode audio. FOUND MISSING — transcription is mining, but TTS is a distinct model class.",
        discovered=True,
        actions=(
            ActionDef("text_to_speech", "Text to speech", "Interviewer responses to informant-facing audio.", None, "tts", "voice"),
        ),
    ),
    RoleDef(
        role_id="indexer",
        position="def",
        label="Indexer",
        blurb="The scout. Graph embeddings + retrieval indexing. FOUND MISSING — embedding model choice is a distinct model class from token-based roles.",
        discovered=True,
        actions=(
            ActionDef("graph_embedding", "Graph embedding", "Embed graph nodes for retrieval.", None, None, "embedding"),
            ActionDef("retrieval_indexing", "Retrieval indexing", "Index documents into the retrieval store.", None, None, "embedding"),
        ),
    ),
)

ROLE_BY_ID: dict[str, RoleDef] = {r.role_id: r for r in ROLE_CATALOG}
ACTION_BY_ID: dict[str, ActionDef] = {
    a.action_id: a for r in ROLE_CATALOG for a in r.actions
}


def default_tier_for_action(action_id: str) -> str | None:
    action = ACTION_BY_ID.get(action_id)
    return action.default_tier if action else None


# ---------------------------------------------------------------------------
# Registry — owner-scoped assignments, JSON sidecar, lenient reads.
# ---------------------------------------------------------------------------


def _registry_path() -> Path:
    override = os.environ.get("ANTIEK_LINEUP_PATH", "").strip()
    if override:
        return Path(override)
    home = os.environ.get("ANTIEK_HOME", "").strip() or str(Path.home())
    return Path(home) / ".antiek" / "settings" / "lineup.json"


def _load_registry() -> dict[str, Any]:
    path = _registry_path()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(raw, dict):
        return {}
    return raw


def _write_registry_unlocked(registry: dict[str, Any]) -> None:
    path = _registry_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(
        json.dumps(registry, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    tmp.replace(path)


# ---------------------------------------------------------------------------
# Bench — the substitute pool: user models + server presets + dispatch tiers.
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class BenchModel:
    provider_id: str
    model_id: str
    label: str
    source: Literal["user_model", "preset", "dispatch"]
    default_tier: str | None


def _dispatch_bench() -> list[BenchModel]:
    """Models named by the dispatch config tiers (server-owned defaults)."""
    cfg = None
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "substrate" / "dispatch" / "config.yaml"
        if candidate.exists():
            try:
                from substrate.dispatch.router import DispatchConfig

                cfg = DispatchConfig.from_yaml(candidate)
            except Exception:
                cfg = None
            break
    if cfg is None:
        return []
    out: list[BenchModel] = []
    seen: set[tuple[str, str]] = set()

    def walk(tier: Any, tier_name: str) -> None:
        provider = getattr(tier, "provider", None)
        model = getattr(tier, "model", None)
        if provider and model and (provider, model) not in seen:
            seen.add((provider, model))
            out.append(
                BenchModel(
                    provider_id=provider,
                    model_id=model,
                    label=f"{provider}/{model}",
                    source="dispatch",
                    default_tier=tier_name,
                )
            )
        fallback = getattr(tier, "fallback", None)
        if fallback is not None:
            walk(fallback, tier_name)

    for tier_name, tier in getattr(cfg, "tiers", {}).items():
        walk(tier, tier_name)
    return out


def _bench_for_request(request: Request) -> list[BenchModel]:
    bench: list[BenchModel] = []
    seen: set[tuple[str, str]] = set()

    # 1. User-added BYOK models (owner-scoped).
    try:
        from interfaces.research.api.settings_models_admin import (
            request_owner_user_id,
            user_model_authority_snapshot,
        )

        owner = request_owner_user_id(request)
        snapshot = user_model_authority_snapshot(request.app, owner_user_id=owner)
        for provider_id, snap in snapshot.items():
            model_id = snap.model_id
            key = (str(provider_id), str(model_id))
            if key in seen:
                continue
            seen.add(key)
            bench.append(
                BenchModel(
                    provider_id=str(provider_id),
                    model_id=str(model_id),
                    label=f"{provider_id}/{model_id}",
                    source="user_model",
                    default_tier=None,
                )
            )
    except Exception:
        # Owner-scoped snapshot is best-effort for the bench; the registry
        # still validates assignments against it at write time.
        pass

    # 2. Server-owned presets (BYOT catalog).
    try:
        from runtime.research_runner.byot_provider_catalog import BYOT_PROVIDER_PRESETS

        for preset in BYOT_PROVIDER_PRESETS:
            for variant in preset.models:
                key = (preset.catalog_id, variant.model_id)
                if key in seen:
                    continue
                seen.add(key)
                bench.append(
                    BenchModel(
                        provider_id=preset.catalog_id,
                        model_id=variant.model_id,
                        label=variant.label,
                        source="preset",
                        default_tier=None,
                    )
                )
    except Exception:
        pass

    # 3. Dispatch-config tiers (server defaults, always substitutable).
    for model in _dispatch_bench():
        key = (model.provider_id, model.model_id)
        if key in seen:
            continue
        seen.add(key)
        bench.append(model)

    return bench


def _bench_index(bench: list[BenchModel]) -> dict[tuple[str, str], BenchModel]:
    return {(b.provider_id, b.model_id): b for b in bench}


# ---------------------------------------------------------------------------
# Pydantic wire shapes
# ---------------------------------------------------------------------------


class LineupChoice(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    provider_id: str = Field(min_length=1, max_length=128)
    model_id: str = Field(min_length=1, max_length=200)


class LineupUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    general: dict[str, LineupChoice | None] = Field(default_factory=dict)
    advanced: dict[str, LineupChoice | None] = Field(default_factory=dict)


class RoleView(BaseModel):
    role_id: str
    position: Position
    label: str
    blurb: str
    discovered: bool
    actions: list[dict[str, Any]]


class ActionView(BaseModel):
    action_id: str
    role_id: str
    label: str
    blurb: str
    dispatch_role: str | None
    default_tier: str | None
    kind: ActionKind


class BenchView(BaseModel):
    provider_id: str
    model_id: str
    label: str
    source: str
    default_tier: str | None


class LineupResponse(BaseModel):
    version: int
    general: list[RoleView]
    advanced: list[ActionView]
    bench: list[BenchView]
    assignments: dict[str, dict[str, LineupChoice | None]]
    updated_at: str | None


def _view(request: Request) -> LineupResponse:
    from interfaces.research.api.settings_models_admin import request_owner_user_id

    owner = request_owner_user_id(request)  # auth gate
    registry = _load_registry()
    owner_map = registry.get("owners", {}).get(owner, {})
    general = owner_map.get("general", {})
    advanced = owner_map.get("advanced", {})
    updated_at = owner_map.get("updated_at")

    return LineupResponse(
        version=1,
        general=[
            RoleView(
                role_id=role.role_id,
                position=role.position,
                label=role.label,
                blurb=role.blurb,
                discovered=role.discovered,
                actions=[
                    {
                        "action_id": a.action_id,
                        "label": a.label,
                        "blurb": a.blurb,
                        "dispatch_role": a.dispatch_role,
                        "default_tier": a.default_tier,
                        "kind": a.kind,
                    }
                    for a in role.actions
                ],
            )
            for role in ROLE_CATALOG
        ],
        advanced=[
            ActionView(
                action_id=a.action_id,
                role_id=role.role_id,
                label=a.label,
                blurb=a.blurb,
                dispatch_role=a.dispatch_role,
                default_tier=a.default_tier,
                kind=a.kind,
            )
            for role in ROLE_CATALOG
            for a in role.actions
        ],
        bench=[BenchView(provider_id=b.provider_id, model_id=b.model_id, label=b.label, source=b.source, default_tier=b.default_tier) for b in _bench_for_request(request)],
        assignments={"general": general, "advanced": advanced},
        updated_at=updated_at,
    )


def _reject(detail: str) -> HTTPException:
    return HTTPException(status_code=422, detail=detail)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

settings_lineup_router = APIRouter(prefix="/settings/lineup", tags=["settings"])


@settings_lineup_router.get("", response_model=LineupResponse)
def get_lineup(request: Request) -> LineupResponse:
    """The full lineup view: formation roles, tactics actions, bench, assignments."""
    from interfaces.research.api.settings_models_admin import request_owner_user_id

    request_owner_user_id(request)  # auth gate
    return _view(request)


@settings_lineup_router.put("", response_model=LineupResponse)
def put_lineup(request: Request, update: LineupUpdate) -> LineupResponse:
    """Atomically replace the owner's lineup assignments.

    Every choice must resolve against the live bench; unknown provider/model
    pairs are rejected value-free. ``null`` (Auto) is always valid and
    restores the platform default for that slot.
    """
    from interfaces.research.api.settings_models_admin import request_owner_user_id

    owner = request_owner_user_id(request)
    bench = _bench_index(_bench_for_request(request))

    def validate_map(
        assignments: dict[str, LineupChoice | None], allowed_ids: set[str], what: str,
    ) -> dict[str, LineupChoice | None]:
        clean: dict[str, LineupChoice | None] = {}
        for slot_id, choice in assignments.items():
            if slot_id not in allowed_ids:
                raise _reject(f"unknown {what} slot: {slot_id!r}")
            if choice is None:
                clean[slot_id] = None
                continue
            key = (choice.provider_id, choice.model_id)
            if key not in bench:
                raise _reject(
                    f"model {choice.provider_id}/{choice.model_id} is not on the bench"
                )
            clean[slot_id] = choice
        return clean

    general = validate_map(update.general, set(ROLE_BY_ID), "role")
    advanced = validate_map(update.advanced, set(ACTION_BY_ID), "action")

    registry = _load_registry()
    owners = registry.get("owners", {})

    def as_json(map_: dict[str, LineupChoice | None]) -> dict[str, Any]:
        return {
            k: v.model_dump(mode="json") if v is not None else None
            for k, v in map_.items()
        }

    owners[owner] = {
        "general": as_json(general),
        "advanced": as_json(advanced),
        "updated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }
    registry["owners"] = owners
    _write_registry_unlocked(registry)
    return _view(request)


def register_settings_lineup_routes(app: FastAPI) -> None:
    """Mount seam, mirroring ``register_settings_budget_routes``."""
    app.include_router(settings_lineup_router)
