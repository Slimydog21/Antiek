/**
 * Forensic inventory of every shipping dispatch role and live extra.
 *
 * Completeness is locked by classify.test.ts against
 * substrate/dispatch/config.yaml role_tiers plus the live extras listed
 * here. Do not drop a found role: classify it or mark it extra.
 */

export const GENERAL_SLOTS = [
  "writer",
  "data miner",
  "data refinement",
  "data verification",
] as const;

export type GeneralSlot = (typeof GENERAL_SLOTS)[number];

export type Classification = GeneralSlot | "extra";

export type RoleSource =
  | "role_tiers"
  | "live_dispatch"
  | "live_root_role"
  | "live_action_set";

export type RoleRecord = {
  role: string;
  classification: Classification;
  source: RoleSource;
  summary: string;
};

export const ROLE_INVENTORY: readonly RoleRecord[] = [
  {
    role: "synthesizer",
    classification: "writer",
    source: "role_tiers",
    summary: "Human-facing synthesis artifact",
  },
  {
    role: "creative_writer",
    classification: "writer",
    source: "role_tiers",
    summary: "Writing-vertical deliverable prose",
  },
  {
    role: "note_taker",
    classification: "data miner",
    source: "role_tiers",
    summary: "Page-level ingestion and notes",
  },
  {
    role: "evidence_retriever",
    classification: "data miner",
    source: "role_tiers",
    summary: "Retrieve supporting evidence",
  },
  {
    role: "parameter_extractor",
    classification: "data miner",
    source: "role_tiers",
    summary: "Extract structured fields",
  },
  {
    role: "knowledge_extractor",
    classification: "data miner",
    source: "role_tiers",
    summary: "Phase 8 knowledge extraction",
  },
  {
    role: "decomposer",
    classification: "data refinement",
    source: "role_tiers",
    summary: "Break a question into work",
  },
  {
    role: "connector",
    classification: "data refinement",
    source: "role_tiers",
    summary: "Connect evidence across documents",
  },
  {
    role: "challenger",
    classification: "data refinement",
    source: "role_tiers",
    summary: "Challenge and refine a living note",
  },
  {
    role: "verifier",
    classification: "data verification",
    source: "role_tiers",
    summary: "Cross-family verification",
  },
  {
    role: "constraint_checker",
    classification: "data verification",
    source: "role_tiers",
    summary: "Constraint checks",
  },
  {
    role: "grounder",
    classification: "data verification",
    source: "role_tiers",
    summary: "Ground claims to evidence",
  },
  {
    role: "tier_assigner",
    classification: "data verification",
    source: "role_tiers",
    summary: "Source-tier classification",
  },
  {
    role: "user_agent",
    classification: "extra",
    source: "role_tiers",
    summary: "Interactive user agent — not a data-pipeline workhorse",
  },
  {
    role: "thought_partner",
    classification: "extra",
    source: "role_tiers",
    summary: "Conversational thought partner",
  },
  {
    role: "autocomplete",
    classification: "extra",
    source: "role_tiers",
    summary: "Inline writing-surface completion",
  },
  {
    role: "interviewer",
    classification: "extra",
    source: "live_dispatch",
    summary: "Interview conversation (dispatch role missing from role_tiers)",
  },
  {
    role: "wrestler",
    classification: "extra",
    source: "live_root_role",
    summary: "Wrestling session root_role",
  },
  {
    role: "rlm_orchestrator",
    classification: "extra",
    source: "live_root_role",
    summary: "Recursive language-model investigation planner",
  },
  {
    role: "visual",
    classification: "extra",
    source: "live_action_set",
    summary: "Frame/image claims via VisionProvider",
  },
  {
    role: "transcription",
    classification: "extra",
    source: "live_action_set",
    summary: "Whisper-grade audio to text",
  },
  {
    role: "tts",
    classification: "extra",
    source: "live_action_set",
    summary: "Interview and speak text to speech",
  },
];

export const LIVE_DISPATCH_EXTRAS: readonly string[] = ROLE_INVENTORY.filter(
  (record) => record.source !== "role_tiers",
).map((record) => record.role);
