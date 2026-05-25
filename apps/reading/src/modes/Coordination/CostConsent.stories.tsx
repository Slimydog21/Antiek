import type { Meta, StoryObj } from "@storybook/react";

import { CostSection, ConsentSection } from "./CostConsent";
import type { CostView, ConsentView } from "./CostConsent";

/**
 * CostConsent — unified cost + escrow/consent surface (antiek-unified SPR-07).
 *
 * The fixtures below mirror the canonical wire shapes the coordination API
 * returns. They render the GATED REALITY the spec mandates:
 *   - cost is real, summed from the dispatch event log, with remote-exec
 *     surfaced and margins honestly stubbed where the matrix isn't applicable;
 *   - escrow accrues but is NOT disbursable while G2/G3 are open (the default
 *     fixture), a zero-buyer holder shows $0, and nothing presents as
 *     disbursable.
 *
 * There is no "disburse" control in any story — the surface cannot pay anyone.
 * The backend no-disbursement test greps this file for a payout path.
 */

// ── Cost fixture: research + read + speak + remote-exec + unmapped ───────────

export const COST_FIXTURE: CostView = {
  per_workflow: [
    {
      workflow: "research",
      raw_cost_usd: "0.45",
      call_count: 3,
      remote_exec_cost_usd: "0.15", // a daytona fan-out leaf — surfaced
      margin_status: "applied",
      margin_rate: "0",
      margined_cost_usd: "0.45",
      margin_note: "No economics-matrix margin (internal spend) — raw is actual.",
    },
    {
      workflow: "read",
      raw_cost_usd: "0.05",
      call_count: 1,
      remote_exec_cost_usd: "0",
      margin_status: "stubbed",
      margin_rate: null,
      margined_cost_usd: null,
      margin_note: "Read ad-economics margin ships in the Read product sprint.",
    },
    {
      workflow: "write",
      raw_cost_usd: "0",
      call_count: 0,
      remote_exec_cost_usd: "0",
      margin_status: "applied",
      margin_rate: "0",
      margined_cost_usd: "0",
      margin_note: "No economics-matrix margin (internal spend).",
    },
    {
      workflow: "speak",
      raw_cost_usd: "0.40",
      call_count: 1,
      remote_exec_cost_usd: "0",
      margin_status: "stubbed",
      margin_rate: null,
      margined_cost_usd: null,
      margin_note:
        "Speak economics matrix is per-project (public 10% / private-published 50%); a margined total needs a project context — raw cost shown, margin not fabricated.",
    },
    {
      workflow: "unmapped",
      raw_cost_usd: "0.07",
      call_count: 1,
      remote_exec_cost_usd: "0",
      margin_status: "stubbed",
      margin_rate: null,
      margined_cost_usd: null,
      margin_note: "Unclassified dispatch role — counted in aggregate.",
    },
  ],
  aggregate_raw_cost_usd: "0.97",
  aggregate_call_count: 6,
  aggregate_remote_exec_cost_usd: "0.15",
  has_unmapped_spend: true,
  events_dir: "~/.antiek/research_events",
};

/** Idle instance — every figure $0. Proves the cost-proportional posture. */
export const COST_IDLE: CostView = {
  per_workflow: COST_FIXTURE.per_workflow.map((w) => ({
    ...w,
    raw_cost_usd: "0",
    call_count: 0,
    remote_exec_cost_usd: "0",
    margined_cost_usd: w.margin_status === "applied" ? "0" : null,
  })),
  aggregate_raw_cost_usd: "0",
  aggregate_call_count: 0,
  aggregate_remote_exec_cost_usd: "0",
  has_unmapped_spend: false,
  events_dir: "~/.antiek/research_events",
};

// ── Consent fixture: G2/G3 OPEN — accruing, not disbursing ───────────────────

const GATED_GATE = {
  disbursable: false,
  open_gate_ids: ["G2", "G3"],
  holder_claimed: false,
  fully_unlocked: false,
  label: "accruing — disbursement gated on G2+G3",
};

export const CONSENT_GATED: ConsentView = {
  holders: [
    {
      ip_holder_id: "ipholder-aaa",
      display_name: "MIT Press",
      status: "claimed",
      escrow_balance_usd: "12.340000",
      // even a CLAIMED holder is not disbursable while the legal gate is open.
      gate: { ...GATED_GATE, holder_claimed: true },
      serves_full_text: true,
      servability_note: "publisher_opted_in — serves full text",
    },
    {
      ip_holder_id: "ipholder-bbb",
      display_name: "Cambridge University Press",
      status: "invited",
      escrow_balance_usd: "3.500000",
      gate: GATED_GATE,
      serves_full_text: false,
      servability_note: "gated_metadata_only — full text gated (deny-by-default)",
    },
    {
      // Zero-buyer holder — honestly $0, not omitted, not fabricated.
      ip_holder_id: "ipholder-ccc",
      display_name: "Princeton University Press",
      status: "pre_onboarded",
      escrow_balance_usd: "0",
      gate: GATED_GATE,
      serves_full_text: null,
      servability_note: null,
    },
  ],
  escrow_report: {
    pre_onboarded: 1,
    invited: 1,
    claimed: 1,
    opted_out: 0,
    claim_rate: 0.5,
    total_escrow_accrued_cents: 1584,
    total_escrow_paid_cents: 0, // nothing paid — disbursement gated
    unclaimed_escrow_cents: 350,
    publishers_with_nontrivial_accrual: 1,
  },
  disbursement_gates_open: ["G2", "G3"],
  total_escrow_accruing_usd: "15.840000",
  any_disbursable: false,
  gate_source_path: "docs/operator_gate_actions.md",
};

/** Zero-buyer everywhere — the whole surface honestly reads $0 accruing. */
export const CONSENT_ZERO_BUYER: ConsentView = {
  holders: [
    {
      ip_holder_id: "ipholder-zzz",
      display_name: "Slop Co (gated, earns nothing)",
      status: "pre_onboarded",
      escrow_balance_usd: "0",
      gate: GATED_GATE,
      serves_full_text: null,
      servability_note: null,
    },
  ],
  escrow_report: {
    pre_onboarded: 1,
    invited: 0,
    claimed: 0,
    opted_out: 0,
    claim_rate: 0,
    total_escrow_accrued_cents: 0,
    total_escrow_paid_cents: 0,
    unclaimed_escrow_cents: 0,
    publishers_with_nontrivial_accrual: 0,
  },
  disbursement_gates_open: ["G2", "G3"],
  total_escrow_accruing_usd: "0",
  any_disbursable: false,
  gate_source_path: "docs/operator_gate_actions.md",
};

// ── Stories ──────────────────────────────────────────────────────────────────

const costMeta = {
  title: "Coordination / CostConsent",
  component: CostSection,
  parameters: { layout: "padded" },
  tags: ["autodocs"],
} satisfies Meta<typeof CostSection>;

export default costMeta;
type CostStory = StoryObj<typeof costMeta>;

/** Cost with spend across workflows, remote-exec surfaced, margins stubbed. */
export const Cost: CostStory = {
  args: { cost: COST_FIXTURE },
};

/** Idle instance — cost-proportional posture reads $0 everywhere. */
export const CostIdle: CostStory = {
  args: { cost: COST_IDLE },
};

/** Escrow/consent in the GATED reality: accruing, not disbursing (G2/G3 open). */
export const ConsentGated: StoryObj<typeof ConsentSection> = {
  render: () => <ConsentSection consent={CONSENT_GATED} />,
};

/** Zero-buyer: the whole surface honestly reads $0 accruing, $0 disbursed. */
export const ConsentZeroBuyer: StoryObj<typeof ConsentSection> = {
  render: () => <ConsentSection consent={CONSENT_ZERO_BUYER} />,
};
