import type { Meta, StoryObj } from "@storybook/react";
import { fn } from "@storybook/test";

import {
  CoordinationView,
  type CoordinationViewProps,
  type CoordinationGatesState,
  type CoordinationRoadmapState,
  type GateView,
  type RoadmapView,
} from "./index";

/**
 * Coordination Gatehouse Atlas — the distinctive Antarctic gatehouse view
 * of canonical operator gates and the dependency-derived cross-product roadmap.
 *
 * The fixtures below mirror the canonical gate states as of the
 * docs/operator_gate_actions.md 2026-05-23 snapshot: G1/G4/G5 closed (G5
 * provisionally), G2/G3/G6 open, G7 calendar (~Nov 2026), G8 data-bound.
 * Extended to G9-G13 for the full 13-gate register.
 *
 * Every story carries the a11y-audit tag for automated accessibility checks.
 */

// ── Canonical 13 gates ────────────────────────────────────────────────

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
  {
    gate_id: "G9",
    title: "arXiv researcher-payout counsel/KYC gate (SPR-07/08)",
    status: "open",
    status_raw: "❌ OPEN",
    is_provisional: false,
    owner: "Operator + counsel",
    blocks: "The money-moving wave of the arXiv-ingest track — SPR-07 researcher identity and SPR-08 KYC payout",
    closure_record: null,
    impacts: [
      { product: "research", effect: "arXiv SPR-07 researcher identity and SPR-08 KYC + Stripe Connect payout remain blocked at the execution edge" },
    ],
  },
  {
    gate_id: "G10",
    title: "Stripe Press §9.10 publisher opt-in",
    status: "open",
    status_raw: "❌ OPEN",
    is_provisional: false,
    owner: "Operator (BizDev — phone/email Stripe Press / Stripe BizDev)",
    blocks: "Serving any in-copyright Stripe Press title",
    closure_record: null,
    impacts: [
      { product: "read", effect: "No in-copyright Stripe Press title is servable until a §9.10 publisher opt-in is granted and claimed" },
    ],
  },
  {
    gate_id: "G11",
    title: "X (Twitter) no-training constraint",
    status: "closed",
    status_raw: "✅ enforced in code / ⏳ standing operator duty",
    is_provisional: false,
    owner: "Operator / agent (keep it standing — never relax it)",
    blocks: "Nothing today; any future training/RL export must honor the standing constraint",
    closure_record: null,
    impacts: [
      { product: "write", effect: "Edit-trajectory SFT must exclude BYOK X content" },
      { product: "speak", effect: "Interviewer RL training must exclude BYOK X content" },
    ],
  },
  {
    gate_id: "G12",
    title: "Bernays per-title copyright-renewal follow-on",
    status: "open",
    status_raw: "❌ OPEN (per-title, only if the operator wants more Bernays titles servable)",
    is_provisional: false,
    owner: "Operator (per-title US copyright-renewal-records check)",
    blocks: "Making any additional 1927–1930 Bernays title servable",
    closure_record: null,
    impacts: [
      { product: "read", effect: "No additional 1927–1930 Bernays title is servable without a per-title US copyright-renewal-records check" },
    ],
  },
  {
    gate_id: "G13",
    title: "Auth diagnostic matrix for login failure triage",
    status: "closed",
    status_raw: "✅ CLOSED 2026-06-02",
    is_provisional: false,
    owner: null,
    blocks: null,
    closure_record: "docs/diagnostics/auth-failure-mode-matrix.md",
    impacts: [],
  },
];

// ── Roadmap fixture ───────────────────────────────────────────────────

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
  unblocked_now: [
    ...Array.from({ length: 10 }, (_, i) => `drw:${i + 1}`),
    ...Array.from({ length: 9 }, (_, i) => `write:${i + 1}`),
    ...Array.from({ length: 9 }, (_, i) => `speak:${i + 1}`),
    ...Array.from({ length: 8 }, (_, i) => `unified:${i + 1}`),
  ],
  substrate_layers: [
    { name: "Write coordination (db_lock)", owner: "runtime/db_lock.py", status: "Hardened (substrate-execution SPR-01)" },
    { name: "Dispatch router + idempotency", owner: "substrate/dispatch/", status: "Hardened (substrate-execution SPR-02/03)" },
    { name: "Structural-integrity lints", owner: "tools/lint/", status: "Landed (substrate-execution SPR-03/05/08)" },
  ],
};

// ── State builders ────────────────────────────────────────────────────

const gatesReady: CoordinationGatesState = {
  phase: "ready",
  data: { source_path: "docs/operator_gate_actions.md", gates: CANONICAL_GATES },
};

const roadmapReady: CoordinationRoadmapState = {
  phase: "ready",
  data: CANONICAL_ROADMAP,
};

const gatesLoading: CoordinationGatesState = { phase: "loading" };
const roadmapLoading: CoordinationRoadmapState = { phase: "loading" };

const gatesError: CoordinationGatesState = {
  phase: "error",
  copy: "Gate data is temporarily unavailable.",
};

const roadmapError: CoordinationRoadmapState = {
  phase: "error",
  copy: "Roadmap data is temporarily unavailable.",
};

const gatesMalformed: CoordinationGatesState = {
  phase: "malformed",
  copy: "Gate data arrived in an unexpected format.",
};

const roadmapMalformed: CoordinationRoadmapState = {
  phase: "malformed",
  copy: "Roadmap data arrived in an unexpected format.",
};

const callbacks: Pick<
  CoordinationViewProps,
  "onRetryGates" | "onRetryRoadmap"
> = {
  onRetryGates: fn(),
  onRetryRoadmap: fn(),
};

// ── Story meta ────────────────────────────────────────────────────────

const meta = {
  title: "Coordination / Gatehouse Atlas",
  component: CoordinationView,
  parameters: {
    layout: "fullscreen",
  },
  tags: ["autodocs", "a11y-audit"],
  args: {
    gatesState: gatesReady,
    roadmapState: roadmapReady,
    ...callbacks,
  },
} satisfies Meta<typeof CoordinationView>;

export default meta;
type Story = StoryObj<typeof meta>;

// ── Canonical atlas (both ready) ──────────────────────────────────────

/** Canonical atlas — 13 gates, full roadmap, both endpoints ready. */
export const CanonicalAtlas: Story = {};

// ── Loading states ────────────────────────────────────────────────────

/** Gates loading, roadmap ready. */
export const GatesLoading: Story = {
  args: {
    gatesState: gatesLoading,
  },
};

/** Roadmap loading, gates ready. */
export const RoadmapLoading: Story = {
  args: {
    roadmapState: roadmapLoading,
  },
};

/** Both loading — Werner thinking. */
export const BothLoading: Story = {
  args: {
    gatesState: gatesLoading,
    roadmapState: roadmapLoading,
  },
};

// ── Error states ──────────────────────────────────────────────────────

/** Gates failed, roadmap healthy — healthy panel retained. */
export const GatesFailed: Story = {
  args: {
    gatesState: gatesError,
  },
};

/** Roadmap failed, gates healthy — healthy panel retained. */
export const RoadmapFailed: Story = {
  args: {
    roadmapState: roadmapError,
  },
};

/** Both failed — Werner empty. */
export const BothFailed: Story = {
  args: {
    gatesState: gatesError,
    roadmapState: roadmapError,
  },
};

// ── Malformed states ──────────────────────────────────────────────────

/** Gates malformed, roadmap healthy. */
export const GatesMalformed: Story = {
  args: {
    gatesState: gatesMalformed,
  },
};

/** Roadmap malformed, gates healthy. */
export const RoadmapMalformed: Story = {
  args: {
    roadmapState: roadmapMalformed,
  },
};

// ── Content variants ──────────────────────────────────────────────────

/** Empty roster — a spec with zero sprints. */
export const EmptyRoster: Story = {
  args: {
    roadmapState: {
      phase: "ready",
      data: {
        ...CANONICAL_ROADMAP,
        rosters: [
          ...CANONICAL_ROADMAP.rosters.slice(0, 4),
          {
            spec: "unified",
            label: "Antiek-Unified",
            directory: "antiek-unified",
            count: 0,
            sprints: [],
          },
        ],
        total_sprints: 37,
        reconciliation:
          "Research 10 + Read 9 + Write 9 + Speak 9 + Antiek-Unified 0 = 37; empty-roster fixture",
        unblocked_now: CANONICAL_ROADMAP.unblocked_now.filter(
          (node) => !node.startsWith("unified:"),
        ),
      },
    },
  },
};

/** Provisional closure — G5 shown with provisional tag. */
export const ProvisionalClosure: Story = {
  args: {
    gatesState: {
      phase: "ready",
      data: {
        source_path: "docs/operator_gate_actions.md",
        gates: CANONICAL_GATES.filter((g) =>
          ["G5", "G4", "G1"].includes(g.gate_id),
        ),
      },
    },
  },
};

/** Unmapped impact — an open gate with no reviewed per-product mapping. */
export const UnmappedImpact: Story = {
  args: {
    gatesState: {
      phase: "ready",
      data: {
        source_path: "docs/operator_gate_actions.md",
        gates: [
          {
            gate_id: "G99",
            title: "New operator gate awaiting cross-workflow review",
            status: "open" as const,
            status_raw: "❌ OPEN",
            is_provisional: false,
            owner: "Operator",
            blocks: "Canonical source describes a block; product mapping has not been reviewed",
            closure_record: null,
            impacts: [],
          },
        ],
      },
    },
  },
};

/** Many gates — all 13 canonical gates displayed. */
export const ManyGates: Story = {};

/** Long values — long owner names, long block descriptions. */
export const LongValues: Story = {
  args: {
    gatesState: {
      phase: "ready",
      data: {
        source_path: "docs/operator_gate_actions.md",
        gates: [
          {
            gate_id: "G99",
            title: "An extremely long gate title that tests how the layout handles verbose descriptions of complex multi-step operator verification requirements across several product domains",
            status: "open",
            status_raw: "❌ OPEN — awaiting a very long series of multi-step operator verifications that span several months of iterative review cycles",
            is_provisional: false,
            owner: "A very long owner name that represents a complex multi-stakeholder responsibility chain spanning operator, counsel, engineering, and external publisher review teams",
            blocks: "An extensive list of blocked items including all payout routes, all publisher outreach, all multi-user pivot activities, all training configurations, and all external integrations",
            closure_record: null,
            impacts: [
              {
                product: "research" as const,
                effect: "A very detailed and verbose description of how this gate blocks the research workflow across multiple sprints and dependency chains, preventing forward progress on several critical path items",
              },
              {
                product: "read" as const,
                effect: "Another verbose impact description that explains in great detail how the reading workflow is affected by this gate remaining open",
              },
            ],
          },
        ],
      },
    },
  },
};

// ── Visual fixture variants ───────────────────────────────────────────

/** Narrow viewport — responsive layout. */
export const Narrow: Story = {
  parameters: {
    viewport: { defaultViewport: "mobile1" },
  },
};

/** Forced night — dark theme for visual audit. */
export const ForcedNight: Story = {
  args: {
    fixtureTheme: "dark",
  },
  parameters: {
    backgrounds: { default: "dark" },
  },
};

// ── Re-exported canonical fixtures for test consumption ────────────────

export { CANONICAL_GATES as CANONICAL_GATES_FIXTURE };
export { CANONICAL_ROADMAP as CANONICAL_ROADMAP_FIXTURE };
