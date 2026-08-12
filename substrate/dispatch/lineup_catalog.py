"""AI Role Lineup catalog — the forensic role taxonomy as pure data.

Substrate-owned, API-agnostic: both the settings HTTP surface
(``interfaces/research/api/settings_lineup.py``) and the dispatch binding
(``substrate/dispatch/lineup_override.py``) read this ONE catalog, so the
operator's model taxonomy cannot drift between the selector and the router.

Taxonomy (see docs/specs/ai-role-lineup-2026-08-12.md for the evidence):

  general  — the formation. The operator's four roles (writer / data miner /
             data refinement / data verification) plus five roles the
             forensic inventory found MISSING: orchestrator (planning),
             critic (deliverable review), media creator (Krea), voice (TTS),
             indexer (embeddings).
  advanced — every concrete AI action/behavior in the product, bucketed
             under exactly one general role, carrying its real dispatch
             role (where one exists) + default tier from config.yaml.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

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
