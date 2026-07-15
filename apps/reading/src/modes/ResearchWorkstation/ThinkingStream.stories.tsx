import type { Meta, StoryObj } from "@storybook/react";
import { expect, userEvent, within } from "@storybook/test";

import type { Event } from "../../generated/types";
import type { InvestigationState } from "../../hooks/useInvestigation";
import ThinkingStream from "./ThinkingStream";

/**
 * ThinkingStream stories — deterministic field-journal scenarios.
 *
 * Each story fixes the investigation state so visual review and chromatic
 * snapshots are fully reproducible. No live socket, no async fetch.
 */

// ── Helpers ──────────────────────────────────────────────────────────────

function ev(
  id: string,
  actionType: string,
  payload: Record<string, unknown> = {},
  at = "2026-07-15T10:00:00Z",
): Event {
  return {
    event_id: id,
    investigation_id: "inv-story",
    action_type: actionType as Event["action_type"],
    payload: payload as unknown as Event["payload"],
    param_version: "v1",
    emitted_at: at,
  };
}

function state(overrides: Partial<InvestigationState>): InvestigationState {
  return {
    id: "inv-story",
    status: "in_progress",
    question: "What is the strongest counter-thesis?",
    events: [],
    terminalPayload: null,
    costTotal: 0,
    completedAt: null,
    streamStatus: "open",
    reconnects: 0,
    ...overrides,
  };
}

// ── Meta ─────────────────────────────────────────────────────────────────

const meta = {
  title: "Loop 1 / ThinkingStream",
  component: ThinkingStream,
  parameters: { layout: "fullscreen" },
  tags: ["autodocs", "a11y-audit"],
  decorators: [
    (Story) => (
      <main className="min-h-screen bg-ice-2 p-4 dark:bg-space-2 sm:p-8">
        <h1 className="sr-only">Research field journal</h1>
        <div className="mx-auto h-[520px] max-w-[760px] overflow-hidden border border-rule bg-ice-1 dark:border-charcoal-1 dark:bg-charcoal-2">
          <Story />
        </div>
      </main>
    ),
  ],
} satisfies Meta<typeof ThinkingStream>;

export default meta;
type Story = StoryObj<typeof meta>;

// ── Stories ──────────────────────────────────────────────────────────────

/** Starting: empty event list, connecting. */
export const Starting: Story = {
  args: {
    investigation: state({
      status: "in_progress",
      events: [],
      streamStatus: "connecting",
    }),
  },
};

/** InProgress: a mixed set of tones — step, finding, caution, milestone. */
export const InProgress: Story = {
  args: {
    investigation: state({
      status: "in_progress",
      costTotal: 0.0312,
      events: [
        ev("e1", "investigation.start_requested", { question: "Why do empires decline?" }),
        ev("e2", "decompose.requested"),
        ev("e3", "decompose.delivered", { decomposition: [{}, {}, {}] }),
        ev("e4", "evidence.retrieve.requested", { sub_question: "Roman fiscal strain" }),
        ev("e5", "evidence.retrieve.delivered", { supporting_claims: [{}, {}], evidentiary_gaps: [{}] }),
        ev("e6", "evidence.retrieve.requested", { sub_question: "Ottoman institutional ossification" }),
        ev("e7", "evidence.retrieve.delivered", { insufficient_evidence: true, supporting_claims: [], evidentiary_gaps: [{}] }),
        ev("e8", "decomposer.paraphrase.flagged"),
      ],
    }),
  },
};

/** Reconnecting: mid-run socket drop, some lines already shown. */
export const Reconnecting: Story = {
  args: {
    investigation: state({
      status: "in_progress",
      streamStatus: "connecting",
      reconnects: 1,
      costTotal: 0.0189,
      events: [
        ev("e1", "investigation.start_requested", { question: "What changed?" }),
        ev("e2", "decompose.requested"),
        ev("e3", "decompose.delivered", { decomposition: [{}, {}] }),
        ev("e4", "evidence.retrieve.requested", { sub_question: "Market signals" }),
      ],
    }),
  },
};

/** SessionBackedStop: an in-progress stream with a wired Stop (busy). */
export const SessionBackedStop: Story = {
  args: {
    investigation: state({
      status: "in_progress",
      costTotal: 0.0451,
      events: [
        ev("e1", "investigation.start_requested", { question: "Why?" }),
        ev("e2", "decompose.requested"),
        ev("e3", "decompose.delivered", { decomposition: [{}, {}] }),
        ev("e4", "evidence.retrieve.requested", { sub_question: "Cost projections" }),
        ev("e5", "evidence.retrieve.delivered", { supporting_claims: [{}], evidentiary_gaps: [] }),
      ],
    }),
    steer: {
      onStop: () => {},
      busy: true,
    },
  },
};

/** Completed: sealed stream with closing folio. */
export const Completed: Story = {
  args: {
    investigation: state({
      status: "completed",
      costTotal: 0.0731,
      events: [
        ev("e1", "investigation.start_requested", { question: "Why do empires decline?" }),
        ev("e2", "decompose.requested"),
        ev("e3", "decompose.delivered", { decomposition: [{}, {}, {}] }),
        ev("e4", "evidence.retrieve.requested", { sub_question: "Fiscal strain" }),
        ev("e5", "evidence.retrieve.delivered", { supporting_claims: [{}, {}, {}], evidentiary_gaps: [] }),
        ev("e6", "synthesize.requested"),
        ev("e7", "synthesize.delivered"),
        ev("e8", "master_md.written"),
        ev("e9", "investigation.completed"),
      ],
    }),
  },
};

/** FailedWithReason: failure surface with an engine reason. */
export const FailedWithReason: Story = {
  args: {
    investigation: state({
      status: "failed",
      terminalPayload: { reason: "retrieval timed out after 30s" },
      events: [
        ev("e1", "investigation.start_requested", { question: "Why?" }),
        ev("e2", "decompose.requested"),
        ev("e3", "investigation.failed"),
      ],
    }),
    onRetry: () => {},
  },
};

/** FailedWithoutReason: failure surface, no engine reason (common keyless case). */
export const FailedWithoutReason: Story = {
  args: {
    investigation: state({
      status: "failed",
      terminalPayload: null,
      events: [
        ev("e1", "investigation.start_requested", { question: "Why?" }),
        ev("e2", "investigation.failed"),
      ],
    }),
    onRetry: () => {},
  },
};

/** LongEntry: a single long prose line that tests the 72ch wrapping. */
export const LongEntry: Story = {
  args: {
    investigation: state({
      status: "in_progress",
      costTotal: 0.0041,
      events: [
        ev("e1", "investigation.start_requested", {
          question:
            "What is the single strongest counter-thesis to the claim that " +
            "renewable energy grid integration costs will exceed fossil fuel " +
            "externalities within the next decade, given current battery technology " +
            "trajectories and regulatory frameworks across major economies?",
        }),
      ],
    }),
  },
};

/** RawAudit: explicit operator disclosure, opened through the real control. */
export const RawAudit: Story = {
  args: InProgress.args,
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    const toggle = canvas.getByRole("button", { name: /show raw activity/i });
    await userEvent.click(toggle);
    await expect(toggle).toHaveAttribute("aria-expanded", "true");
  },
};
