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
  { n: 5, slug: "cascade-planner", status: "live" },
  { n: 6, slug: "parallel-orchestration", status: "live" },
  { n: 7, slug: "structural-gap-detection", status: "live" },
  { n: 8, slug: "universal-ingest", status: "live" },
  { n: 9, slug: "glassbox-monitor-ui", status: "live" },
  { n: 10, slug: "reading-surface", status: "transferred" },
];

const CRITICAL = ["drw:1", "drw:3", "drw:10"];

const readyNowIds = [
  ...drwSprints.map((d) => `drw:${d.n}`),
  ...Array.from({ length: 9 }, (_, i) => `read:${i + 1}`),
  ...Array.from({ length: 9 }, (_, i) => `write:${i + 1}`),
  ...Array.from({ length: 9 }, (_, i) => `speak:${i + 1}`),
  ...Array.from({ length: 8 }, (_, i) => `unified:${i + 1}`),
];

export const CANONICAL_ROADMAP: RoadmapView = {
  total_sprints: 45,
  superseded_count: 6,
  superseded_note: "five-surface portfolio-shell prototype, superseded by unified's 8",
  activation_note:
    "Structural sprint status is not activation closure. Read activation still requires the live dogfood evidence in specs/activation/golden-path.md; CI is the floor, use is the gate.",
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
        blocked_on: [],
        unblocked: true,
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
      sprints: [
        "consent-rights-gate",
        "async-voice-interview",
        "project-invitations",
        "compounding-interviewer",
        "cross-interviewee-verification",
        "contributor-economics",
        "economics-matrix",
        "biography-authoring",
        "publishing-physical",
      ].map((slug, i) => ({
        spec: "speak",
        spec_label: "Speak",
        sprint: i + 1,
        slug,
        node_id: `speak:${i + 1}`,
        status: "live",
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
        status: "live",
        on_critical_path: false,
        blocked_on: [],
        unblocked: true,
      })),
    },
  ],
  unblocked_now: readyNowIds,
  dependency_blockers: [],
  execution_focus: null,
  operator_gate_focus: {
    gate_id: "G2",
    title: "Lawyer review of Kalshi-pattern notification template",
    status: "open",
    status_raw: "OPEN",
    owner: "Operator + counsel",
    blocks: "All Stripe payouts; first publisher outreach",
    source_path: "docs/operator_gate_actions.md",
  },
  read_activation: {
    source_path: "reports/read-dogfood.jsonl",
    state: "not_started",
    total_sessions: 0,
    valid_sessions: 0,
    invalid_session_count: 0,
    live_provider_sessions: 0,
    citation_trace_sessions: 0,
    non_library_sessions: 0,
    final_verdict: null,
    closure_ready: false,
    required_counts: {
      valid_sessions: 10,
      live_provider_sessions: 5,
      citation_trace_sessions: 3,
      non_library_sessions: 1,
    },
    remaining_requirements: {
      valid_sessions: 10,
      live_provider_sessions: 5,
      citation_trace_sessions: 3,
      non_library_sessions: 1,
    },
    failures: [],
  },
  operator_actions: {
    source_path: "docs/OPERATOR_ACTIONS.md",
    total_actions: 20,
    open_count: 19,
    closeable_count: 1,
    status_counts: {
      open: 17,
      awaiting_operator_test: 1,
      partially_done: 1,
      closed: 1,
    },
    next_action: {
      action_id: "OA-001",
      title: "Lawyer review of Kalshi-pattern notification template",
      status: "open",
      status_raw: "OPEN",
      blocks: "All Stripe payouts; first publisher outreach",
      owner: "Operator + counsel",
    },
    closeable_action: {
      action_id: "OA-005",
      title: "Autoresearch Wedge 1 ratification",
      status: "awaiting_operator_test",
      status_raw: "AWAITING OPERATOR TEST",
      blocks: "Phase 8 enforcing + Wedges 2-4",
      owner: "Operator",
    },
  },
  phase2_audit: {
    source_path: "docs/phase2_execution_audit_v5_2026_07_01.md",
    scorecard_source_path: "docs/phase2_execution_audit_v4_2026_05_23.md",
    current_commit_evidence:
      "23048220 feat(ducklake): route default graph path through catalog",
    engineering_blocked_count: 0,
    status_summary:
      "net engineering-side-blocked items known from v4: 0.",
    next_action_ordering: [
      "Keep docs/OPERATOR_ACTIONS.md as the authoritative operator gate list.",
      "Do not pre-build anything listed in docs/engineering_deferrals.md.",
    ],
    sprint_scorecard: [
      { sprint: "Sprint 22", phases: 9, met: 1, partial: 6, unmet: 2, delta_vs_v3: "-1 unmet, +1 partial" },
      { sprint: "Sprint 23-24", phases: 6, met: 0, partial: 5, unmet: 1, delta_vs_v3: "-2 unmet, +2 partial" },
      { sprint: "Sprint 25+", phases: 7, met: 2, partial: 4, unmet: 1, delta_vs_v3: "unchanged" },
      { sprint: "Sprint 30+", phases: 6, met: 3, partial: 2, unmet: 1, delta_vs_v3: "unchanged" },
    ],
    total_score: {
      sprint: "TOTAL",
      phases: 28,
      met: 6,
      partial: 17,
      unmet: 5,
      delta_vs_v3: "-3 unmet, +3 partial since v3",
    },
    exit_criteria: {
      total: 23,
      met: 3,
      partial: 2,
      unmet: 18,
      note:
        "every unmet exit criterion is blocked by operator action or real-data accumulation, not substrate.",
    },
  },
  engineering_deferrals: {
    source_path: "docs/engineering_deferrals.md",
    total_deferrals: 19,
    open_count: 16,
    status_counts: {
      deferred: 7,
      partial: 5,
      substrate_shipped: 4,
      closed: 3,
    },
    first_open: {
      deferral_id: "D1",
      title: "Sprint 22 multi-user pivot cluster",
      status: "partial",
      status_raw: "Deferred. Substrate prep is partial.",
      unlock_criterion:
        "G7 (six-month solo-operator compounding window per master-spec §13.4) closes — earliest ~Nov 2026.",
      blocks:
        "D8 (Sprint 25+ ads at scale), D9 (Sprint 30+ federation activation), every second-user exit criterion.",
    },
  },
  loop3: {
    criteria: [],
    manual_met_count: 0,
    evidence_passed_count: 0,
    total_criteria: 5,
    all_criteria_met: false,
    all_evidence_passed: false,
    env_unlocked: false,
    fully_unlocked: false,
    first_failing_evidence: {
      criterion: "trajectory_volume",
      manual_met: false,
      evidence_passed: false,
      evidence_status: "FAIL",
      evidence_summary: "events_dir_exists: ~/.antiek/research_events",
    },
    events_dir: "~/.antiek/research_events",
    open_weight_policy_file: "reports/loop3/open-weight-policy-ids.json",
  },
  source_gate: {
    source_path: "reports/source_census.json",
    state: "missing",
    reference_source: "arxiv",
    source_count: 0,
    blocked_count: 0,
    rows: [],
    error:
      "no source census yet; source_gate is a no-op until the operator produces reports/source_census.json from the real corpus",
  },
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
