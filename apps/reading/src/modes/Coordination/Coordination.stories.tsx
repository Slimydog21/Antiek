import type { Meta, StoryObj } from "@storybook/react";

import { GateLedger } from "./GateLedger";
import type { GateView } from "./GateLedger";
import { Roadmap } from "./Roadmap";
import type { RoadmapView } from "./Roadmap";

/**
 * Coordination — gate ledger + roadmap (antiek-unified SPR-05).
 *
 * The fixtures below mirror the canonical gate states as of the
 * docs/operator_gate_actions.md 2026-05-23 snapshot: G1/G4/G5 closed (G5
 * provisionally), G2/G3/G6 open, G7 calendar (~Nov 2026), G8 data-bound. The
 * ACCURACY_SNAPSHOT constant is the single source these stories render — a
 * parsing/rendering regression that changed a gate's status would change this
 * fixture, which is what the snapshot guards against (M5). The substrate parser
 * is tested against the real file in tests/test_coordination_no_fork.py; this
 * is the rendered-surface counterpart.
 */

// ── The accuracy snapshot: canonical gate states ─────────────────────────────

export const CANONICAL_GATES: GateView[] = [
  {
    gate_id: "G1",
    title: "Retrieval-time legal gating in production",
    status: "closed",
    status_raw: "✅ CLOSED",
    is_provisional: false,
    owner: null,
    blocks: null,
    closure_record: null,
    impacts: [
      { product: "research", effect: "Retrieval-time legal gating on served chunks (closed — no longer blocking)" },
      { product: "read", effect: "Full-text serving passes the gate (closed — no longer blocking)" },
    ],
  },
  {
    gate_id: "G2",
    title: "Lawyer review of Kalshi-pattern publisher notification template",
    status: "open",
    status_raw: "❌ OPEN",
    is_provisional: false,
    owner: "Operator + counsel",
    blocks: "All Stripe payouts; first publisher outreach",
    closure_record: null,
    impacts: [
      { product: "read", effect: "Ad-revenue disbursement (Read SPR-09 escrow) blocked until counsel clears the notification template" },
      { product: "speak", effect: "Contributor disbursement (Speak SPR-06/07 economics) blocked — public publication also gated" },
    ],
  },
  {
    gate_id: "G3",
    title: "At least one publisher affirmatively opted in",
    status: "open",
    status_raw: "❌ OPEN",
    is_provisional: false,
    owner: "Operator (outreach) + publisher (decision)",
    blocks: "All Stripe payouts",
    closure_record: null,
    impacts: [
      { product: "read", effect: "No payout until ≥1 publisher opts in (Read SPR-09 escrow stays accrual-only)" },
      { product: "speak", effect: "Contributor payouts blocked — informant→payee map produces $0 disbursable" },
    ],
  },
  {
    gate_id: "G4",
    title: "Lemon UI operator visual eye-test",
    status: "closed",
    status_raw: "✅ CLOSED 2026-05-23",
    is_provisional: false,
    owner: null,
    blocks: null,
    closure_record: "docs/decisions/g4-lemon-ui-verdict.md",
    impacts: [],
  },
  {
    gate_id: "G5",
    title: "Dispatch tier-differentiation measurement verdict",
    status: "closed",
    status_raw: "✅ CLOSED 2026-05-23 (provisionally, with re-open trigger)",
    is_provisional: true,
    owner: null,
    blocks: null,
    closure_record: "docs/decisions/dispatch-tier-verdict.md",
    impacts: [],
  },
  {
    gate_id: "G6",
    title: "Autoresearch Wedge 1 ratification (the Lutke-gap test)",
    status: "open",
    status_raw: "⏳ AWAITING OPERATOR TEST",
    is_provisional: false,
    owner: "Operator (run the verdict at end of mutation cohort)",
    blocks: "Phase 8 enforcing mode + autoresearch Wedges 2-4",
    closure_record: null,
    impacts: [
      { product: "research", effect: "Phase-8 enforcing mode + autoresearch Wedges 2-4 stay shadow until the Lutke-gap verdict ratifies" },
    ],
  },
  {
    gate_id: "G7",
    title: "Six months of solo-operator compounding demonstration",
    status: "calendar",
    status_raw: "❌ OPEN (earliest closure ~Nov 2026)",
    is_provisional: false,
    owner: "Operator (publish + demonstrate)",
    blocks: "Multi-user pivot (Sprint 22)",
    closure_record: null,
    impacts: [
      { product: "research", effect: "Multi-user pivot (Sprint 22) blocked — single-operator until the compounding curve is demonstrated" },
      { product: "read", effect: "Public/multi-user reading ecosystem blocked until G7 closes" },
      { product: "write", effect: "Multi-user authoring blocked until G7 closes" },
      { product: "speak", effect: "Public interview ecosystem (multi-user) blocked until G7 closes" },
    ],
  },
  {
    gate_id: "G8",
    title: "Loop 3 unlock criteria (five sub-gates)",
    status: "data_bound",
    status_raw: "❌ OPEN (none of the five checked)",
    is_provisional: false,
    owner: "Operator (after substrate accumulation)",
    blocks: "All RLM + SFT + hosted RL work",
    closure_record: null,
    impacts: [
      { product: "write", effect: "Edit-trajectory SFT / RL training blocked until the five Loop-3 criteria pass" },
      { product: "speak", effect: "Interviewer RL training blocked until the five Loop-3 criteria pass" },
    ],
  },
];

// ── The roadmap fixture: the reconciled 45-sprint count + DRW critical path ──

const drwSprints = [
  { n: 1, slug: "insight-question-nodes", status: "live" },
  { n: 2, slug: "research-runner", status: "live" },
  { n: 3, slug: "async-note-taker", status: "live" },
  { n: 4, slug: "max-context-pack", status: "live" },
  { n: 5, slug: "cascade-planner", status: "planned" },
  { n: 6, slug: "parallel-orchestration", status: "planned" },
  { n: 7, slug: "structural-gap-detection", status: "planned" },
  { n: 8, slug: "universal-ingest", status: "planned" },
  { n: 9, slug: "glassbox-monitor-ui", status: "planned" },
  { n: 10, slug: "reading-surface", status: "provisional" },
];

const CRITICAL = ["drw:1", "drw:3", "drw:10"];

export const CANONICAL_ROADMAP: RoadmapView = {
  total_sprints: 45,
  superseded_count: 6,
  superseded_note: "five-surface portfolio-shell prototype, superseded by unified's 8",
  reconciliation:
    "Research 10 + Read 9 + Write 9 + Speak 9 + Antiek-Unified 8 = 45; shell's 6 superseded (five-surface portfolio-shell prototype, superseded by unified's 8)",
  critical_path: CRITICAL,
  rosters: [
    {
      spec: "drw",
      label: "Research (DRW)",
      directory: "deep-research-workspace",
      count: 10,
      sprints: drwSprints.map((d) => ({
        spec: "drw",
        spec_label: "Research (DRW)",
        sprint: d.n,
        slug: d.slug,
        node_id: `drw:${d.n}`,
        status: d.status,
        on_critical_path: CRITICAL.includes(`drw:${d.n}`),
        blocked_on: [],
        unblocked: true,
      })),
    },
    {
      spec: "read",
      label: "Read",
      directory: "read",
      count: 9,
      sprints: Array.from({ length: 9 }, (_, i) => ({
        spec: "read",
        spec_label: "Read",
        sprint: i + 1,
        slug: `sprint-${i + 1}`,
        node_id: `read:${i + 1}`,
        status: "unknown",
        on_critical_path: false,
        blocked_on: ["drw:5", "drw:6"],
        unblocked: false,
      })),
    },
    {
      spec: "write",
      label: "Write",
      directory: "write",
      count: 9,
      sprints: Array.from({ length: 9 }, (_, i) => ({
        spec: "write",
        spec_label: "Write",
        sprint: i + 1,
        slug: `sprint-${i + 1}`,
        node_id: `write:${i + 1}`,
        status: "unknown",
        on_critical_path: false,
        blocked_on: [],
        unblocked: true,
      })),
    },
    {
      spec: "speak",
      label: "Speak",
      directory: "speak",
      count: 9,
      sprints: Array.from({ length: 9 }, (_, i) => ({
        spec: "speak",
        spec_label: "Speak",
        sprint: i + 1,
        slug: `sprint-${i + 1}`,
        node_id: `speak:${i + 1}`,
        status: "unknown",
        on_critical_path: false,
        blocked_on: [],
        unblocked: true,
      })),
    },
    {
      spec: "unified",
      label: "Antiek-Unified",
      directory: "antiek-unified",
      count: 8,
      sprints: Array.from({ length: 8 }, (_, i) => ({
        spec: "unified",
        spec_label: "Antiek-Unified",
        sprint: i + 1,
        slug: `sprint-${i + 1}`,
        node_id: `unified:${i + 1}`,
        status: "unknown",
        on_critical_path: false,
        blocked_on: [],
        unblocked: true,
      })),
    },
  ],
  unblocked_now: [],
  substrate_layers: [
    { name: "Write coordination (db_lock)", owner: "runtime/db_lock.py", status: "Hardened (substrate-execution SPR-01)" },
    { name: "Dispatch router + idempotency", owner: "substrate/dispatch/", status: "Hardened (substrate-execution SPR-02/03)" },
    { name: "Structural-integrity lints", owner: "tools/lint/", status: "Landed (substrate-execution SPR-03/05/08)" },
  ],
};

// ── Stories ──────────────────────────────────────────────────────────────────

const gateMeta = {
  title: "Coordination / GateLedger",
  component: GateLedger,
  parameters: { layout: "padded" },
  tags: ["autodocs"],
} satisfies Meta<typeof GateLedger>;

export default gateMeta;
type GateStory = StoryObj<typeof gateMeta>;

/** Accuracy snapshot — the canonical gate states rendered. A regression in
 * parsing or rendering that flipped a gate would change this surface. */
export const CanonicalGates: GateStory = {
  args: {
    gates: CANONICAL_GATES,
    sourcePath: "docs/operator_gate_actions.md",
  },
};

export const RoadmapView_: StoryObj<typeof Roadmap> = {
  render: () => <Roadmap roadmap={CANONICAL_ROADMAP} />,
};
