/**
 * Story fixtures — mock data for Storybook only.
 *
 * Use these in *.stories.tsx so stories can render without the live
 * substrate / API. Each export is a synthetic but realistically-shaped
 * value for the matching type from `generated/types.ts` or
 * `hooks/*.ts` / `lib/api.ts`.
 *
 * Rules:
 *   - These are FOR STORIES ONLY. Never import from non-story code.
 *   - Shapes mirror the real types so a schema change here surfaces
 *     immediately in CI via strict-TS.
 *   - Keep payloads small but representative; do not paste real
 *     investigation transcripts.
 */

import type { Event } from "../../generated/types";
import type { InvestigationState } from "../../hooks/useInvestigation";

const NOW = "2026-05-21T17:00:00Z";

/** A single, minimal phase.enter event (used for layout smoke-tests). */
export const mockPhaseEnterEvent: Event = {
  event_id: "evt-001",
  investigation_id: "inv-storybook-demo",
  action_type: "phase.enter" as Event["action_type"],
  phase: 1,
  role: null,
  payload: { phase_id: 1, phase_name: "decompose" } as never,
  param_version: "0.1.0",
  schema_version: 6,
  emitted_at: NOW,
};

/** decompose.delivered — sub-questions list. */
export const mockDecomposeDeliveredEvent: Event = {
  event_id: "evt-002",
  investigation_id: "inv-storybook-demo",
  action_type: "decompose.delivered" as Event["action_type"],
  phase: 1,
  role: "decomposer",
  payload: {
    sub_questions: [
      "What is the published gate error rate on Lukin's neutral-atom array?",
      "How does the QuEra production system compare on the same metric?",
      "Is there a peer-reviewed cross-comparison from 2024 onward?",
    ],
  } as never,
  param_version: "0.1.0",
  schema_version: 6,
  emitted_at: NOW,
};

/** evidence.retrieve.delivered — insights + open questions columns. */
export const mockEvidenceDeliveredEvent: Event = {
  event_id: "evt-003",
  investigation_id: "inv-storybook-demo",
  action_type: "evidence.retrieve.delivered" as Event["action_type"],
  phase: 2,
  role: "evidence_retriever",
  payload: {
    insights: [
      "Lukin lab reports 1.2e-3 single-qubit gate error at 100 qubits (2024).",
      "QuEra Aquila production system reports 8e-4 (2025 preprint).",
      "Vuletic preprint uses a different decomposition; numbers not comparable.",
    ],
    open_questions: [
      "What is the cross-platform normalization for these numbers?",
      "Has anyone published a head-to-head benchmark?",
    ],
  } as never,
  param_version: "0.1.0",
  schema_version: 6,
  emitted_at: NOW,
};

/** synthesize.delivered — final thesis preview. */
export const mockSynthesizeDeliveredEvent: Event = {
  event_id: "evt-004",
  investigation_id: "inv-storybook-demo",
  action_type: "synthesize.delivered" as Event["action_type"],
  phase: 5,
  role: "synthesizer",
  payload: {
    synthesis_id: "syn-storybook-demo",
    thesis: "Neutral-atom platforms cluster at error rates within an order of magnitude, but cross-comparison is hampered by gate-set choice.",
    summary_markdown: "## Insights\n\nNeutral-atom platforms have published single-qubit gate error rates clustering between 8×10⁻⁴ and 1.5×10⁻³…\n\n## Open questions\n\nThe remaining question worth chasing…",
  } as never,
  param_version: "0.1.0",
  schema_version: 6,
  emitted_at: NOW,
};

/** dispatch.call — single LLM call, used by collapsible cost row. */
export const mockDispatchCallEvent: Event = {
  event_id: "evt-005",
  investigation_id: "inv-storybook-demo",
  action_type: "dispatch.call" as Event["action_type"],
  phase: 2,
  role: null,
  payload: {
    provider: "anthropic",
    model: "claude-3-5-sonnet",
    tokens_in: 1834,
    tokens_out: 412,
    cost_usd: 0.0094,
    latency_ms: 1283,
  } as never,
  param_version: "0.1.0",
  schema_version: 6,
  emitted_at: NOW,
};

/** Convenience: a small, ordered trajectory for TrajectoryView stories. */
export const mockEventStream: Event[] = [
  mockPhaseEnterEvent,
  mockDecomposeDeliveredEvent,
  mockEvidenceDeliveredEvent,
  mockDispatchCallEvent,
  mockSynthesizeDeliveredEvent,
];

/** Mock InvestigationState in various lifecycle stages. */
export const mockInvestigationInProgress: InvestigationState = {
  id: "inv-storybook-demo",
  status: "in_progress",
  question: "Are neutral-atom error rates competitive at 100-qubit scale?",
  events: mockEventStream.slice(0, 3),
  terminalPayload: null,
  costTotal: 0.0094,
  completedAt: null,
  streamStatus: "open",
  reconnects: 0,
  sourcePolicy: ["operator_corpus", "web"],
};

export const mockInvestigationCompleted: InvestigationState = {
  id: "inv-storybook-demo",
  status: "completed",
  question: "Are neutral-atom error rates competitive at 100-qubit scale?",
  events: mockEventStream,
  terminalPayload: {
    synthesis_id: "syn-storybook-demo",
    summary_markdown: "## Insights\n\nNeutral-atom platforms have published single-qubit gate error rates clustering between 8×10⁻⁴ and 1.5×10⁻³…",
  },
  costTotal: 0.0094,
  completedAt: "2026-05-21T17:42:00Z",
  streamStatus: "closed",
  reconnects: 0,
  sourcePolicy: ["operator_corpus", "web"],
};

export const mockInvestigationLoading: InvestigationState = {
  id: "inv-storybook-demo",
  status: "loading",
  question: null,
  events: [],
  terminalPayload: null,
  costTotal: 0,
  completedAt: null,
  streamStatus: "connecting",
  reconnects: 0,
  sourcePolicy: [],
};
