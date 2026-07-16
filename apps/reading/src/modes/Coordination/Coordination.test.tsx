import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { StrictMode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { apiFetch } from "../../lib/api";
import Coordination, {
  CoordinationView,
  type CoordinationViewProps,
  type GateView,
  type RoadmapView,
} from "./index";

vi.mock("../../lib/api", () => ({ apiFetch: vi.fn() }));
afterEach(cleanup);

// ── Fixtures ──────────────────────────────────────────────────────────

const CANONICAL_GATES: GateView[] = [
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
      { product: "research", effect: "Retrieval-time legal gating on served chunks (closed)" },
      { product: "read", effect: "Full-text serving passes the gate (closed)" },
    ],
  },
  {
    gate_id: "G2",
    title: "Lawyer review of publisher notification template",
    status: "open",
    status_raw: "❌ OPEN",
    is_provisional: false,
    owner: "Operator + counsel",
    blocks: "All Stripe payouts",
    closure_record: null,
    impacts: [
      { product: "read", effect: "Ad-revenue disbursement blocked" },
      { product: "speak", effect: "Contributor disbursement blocked" },
    ],
  },
  {
    gate_id: "G3",
    title: "At least one publisher opted in",
    status: "open",
    status_raw: "❌ OPEN",
    is_provisional: false,
    owner: "Operator (outreach)",
    blocks: "All Stripe payouts",
    closure_record: null,
    impacts: [
      { product: "read", effect: "No payout until ≥1 publisher opts in" },
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
    status_raw: "✅ CLOSED 2026-05-23 (provisionally)",
    is_provisional: true,
    owner: null,
    blocks: null,
    closure_record: "docs/decisions/dispatch-tier-verdict.md",
    impacts: [],
  },
  {
    gate_id: "G6",
    title: "Autoresearch Wedge 1 ratification",
    status: "open",
    status_raw: "⏳ AWAITING OPERATOR TEST",
    is_provisional: false,
    owner: "Operator",
    blocks: "Phase 8 enforcing mode",
    closure_record: null,
    impacts: [
      { product: "research", effect: "Phase-8 enforcing mode stays shadow" },
    ],
  },
  {
    gate_id: "G7",
    title: "Six months of solo-operator compounding",
    status: "calendar",
    status_raw: "❌ OPEN (earliest ~Nov 2026)",
    is_provisional: false,
    owner: "Operator",
    blocks: "Multi-user pivot",
    closure_record: null,
    impacts: [
      { product: "research", effect: "Multi-user pivot blocked" },
      { product: "read", effect: "Public reading blocked" },
      { product: "write", effect: "Multi-user authoring blocked" },
      { product: "speak", effect: "Public interviews blocked" },
    ],
  },
  {
    gate_id: "G8",
    title: "Loop 3 unlock criteria",
    status: "data_bound",
    status_raw: "❌ OPEN (none checked)",
    is_provisional: false,
    owner: "Operator",
    blocks: "All RLM + SFT + hosted RL",
    closure_record: null,
    impacts: [
      { product: "write", effect: "Edit-trajectory SFT / RL training blocked" },
      { product: "speak", effect: "Interviewer RL training blocked" },
    ],
  },
];

const CRITICAL = ["drw:1", "drw:3", "drw:10"];

const CANONICAL_ROADMAP: RoadmapView = {
  total_sprints: 45,
  superseded_count: 6,
  superseded_note: "superseded by unified's 8",
  reconciliation: "Research 10 + Read 9 + Write 9 + Speak 9 + Antiek-Unified 8 = 45",
  critical_path: CRITICAL,
  rosters: [
    {
      spec: "drw",
      label: "Research (DRW)",
      directory: "deep-research-workspace",
      count: 10,
      sprints: Array.from({ length: 10 }, (_, i) => ({
        spec: "drw",
        spec_label: "Research (DRW)",
        sprint: i + 1,
        slug: `sprint-${i + 1}`,
        node_id: `drw:${i + 1}`,
        status: i < 4 ? "live" : i === 9 ? "provisional" : "planned",
        on_critical_path: CRITICAL.includes(`drw:${i + 1}`),
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
    { name: "Write coordination (db_lock)", owner: "runtime/db_lock.py", status: "Hardened" },
  ],
};

const gatesResponse = (gates: GateView[] = CANONICAL_GATES) => ({
  source_path: "docs/operator_gate_actions.md",
  gates,
});

const response = (body: unknown, ok = true) =>
  ({
    ok,
    json: vi.fn().mockResolvedValue(body),
  }) as unknown as Response;

const viewCallbacks: Pick<
  CoordinationViewProps,
  "onRetryGates" | "onRetryRoadmap"
> = {
  onRetryGates: vi.fn(),
  onRetryRoadmap: vi.fn(),
};

// ── CoordinationView (pure) ───────────────────────────────────────────

describe("CoordinationView", () => {
  it("exposes the read-only doorway to Cost & Consent", () => {
    render(
      <CoordinationView
        gatesState={{ phase: "ready", data: gatesResponse() }}
        roadmapState={{ phase: "ready", data: CANONICAL_ROADMAP }}
        {...viewCallbacks}
      />,
    );

    expect(
      screen
        .getByRole("link", { name: /open cost & consent/i })
        .getAttribute("href"),
    ).toBe("/coordination/cost-consent");
  });

  beforeEach(() => vi.clearAllMocks());

  // ── Hero + truth boundary ──────────────────────────────────────────

  it("renders the hero with title and Werner", () => {
    render(
      <CoordinationView
        gatesState={{ phase: "ready", data: gatesResponse() }}
        roadmapState={{ phase: "ready", data: CANONICAL_ROADMAP }}
        {...viewCallbacks}
      />,
    );
    expect(screen.getByRole("heading", { name: /coordination gatehouse atlas/i })).toBeTruthy();
    expect(screen.getByRole("img", { name: /werner watches/i })).toBeTruthy();
  });

  it("states the truth boundary: read-only, no mutation authority", () => {
    render(
      <CoordinationView
        gatesState={{ phase: "ready", data: gatesResponse() }}
        roadmapState={{ phase: "ready", data: CANONICAL_ROADMAP }}
        {...viewCallbacks}
      />,
    );
    const aside = screen.getByLabelText("Gatehouse boundary");
    expect(within(aside).getByText(/read-only operator view/i)).toBeTruthy();
    expect(within(aside).getByText(/no control here can mutate/i)).toBeTruthy();
  });

  it("states that status_raw preserves nuance", () => {
    render(
      <CoordinationView
        gatesState={{ phase: "ready", data: gatesResponse() }}
        roadmapState={{ phase: "ready", data: CANONICAL_ROADMAP }}
        {...viewCallbacks}
      />,
    );
    const aside = screen.getByLabelText("Gatehouse boundary");
    expect(aside.textContent).toMatch(/status_raw.*preserves the original nuance/i);
  });

  it("states empty impacts mean no reviewed mapping, never no block", () => {
    render(
      <CoordinationView
        gatesState={{ phase: "ready", data: gatesResponse() }}
        roadmapState={{ phase: "ready", data: CANONICAL_ROADMAP }}
        {...viewCallbacks}
      />,
    );
    const aside = screen.getByLabelText("Gatehouse boundary");
    expect(aside.textContent).toMatch(/no reviewed per-product mapping/i);
  });

  it("states no freshness timestamp invented", () => {
    render(
      <CoordinationView
        gatesState={{ phase: "ready", data: gatesResponse() }}
        roadmapState={{ phase: "ready", data: CANONICAL_ROADMAP }}
        {...viewCallbacks}
      />,
    );
    const aside = screen.getByLabelText("Gatehouse boundary");
    expect(aside.textContent).toMatch(/neither endpoint supplies a freshness/i);
  });

  // ── Status tally ───────────────────────────────────────────────────

  it("renders payload-derived status tally", () => {
    render(
      <CoordinationView
        gatesState={{ phase: "ready", data: gatesResponse() }}
        roadmapState={{ phase: "ready", data: CANONICAL_ROADMAP }}
        {...viewCallbacks}
      />,
    );
    const tally = screen.getByLabelText("Gate status tally");
    // 3 open, 1 calendar, 1 data-bound, 3 closed
    expect(within(tally).getAllByText("3").length).toBeGreaterThanOrEqual(1); // open + closed
    expect(within(tally).getAllByText("1").length).toBeGreaterThanOrEqual(1); // calendar + data-bound
  });

  // ── Gate Wall ──────────────────────────────────────────────────────

  it("renders gates sorted: open/calendar/data_bound before closed, then by numeric ID", () => {
    render(
      <CoordinationView
        gatesState={{ phase: "ready", data: gatesResponse() }}
        roadmapState={{ phase: "ready", data: CANONICAL_ROADMAP }}
        {...viewCallbacks}
      />,
    );
    const gateWall = screen.getByRole("region", { name: "Gate wall" });
    const gateCards = within(gateWall).getAllByRole("article");
    // First should be open gates (G2, G3, G6), then calendar (G7), data_bound (G8), then closed (G1, G4, G5)
    expect(gateCards[0].textContent).toContain("G2");
    expect(gateCards[1].textContent).toContain("G3");
    expect(gateCards[2].textContent).toContain("G6");
    expect(gateCards[3].textContent).toContain("G7");
    expect(gateCards[4].textContent).toContain("G8");
    // Closed gates follow
    expect(gateCards[5].textContent).toContain("G1");
  });

  it("shows status_raw for each gate", () => {
    render(
      <CoordinationView
        gatesState={{ phase: "ready", data: gatesResponse() }}
        roadmapState={{ phase: "ready", data: CANONICAL_ROADMAP }}
        {...viewCallbacks}
      />,
    );
    expect(screen.getAllByText("❌ OPEN")).toHaveLength(2);
    expect(screen.getByText("⏳ AWAITING OPERATOR TEST")).toBeTruthy();
    expect(screen.getAllByText("✅ CLOSED").length).toBeGreaterThanOrEqual(1);
  });

  it("shows provisional tag for provisional closures", () => {
    render(
      <CoordinationView
        gatesState={{ phase: "ready", data: gatesResponse() }}
        roadmapState={{ phase: "ready", data: CANONICAL_ROADMAP }}
        {...viewCallbacks}
      />,
    );
    // Multiple elements contain "provisional" — check at least 1 exists
    expect(screen.getAllByText(/provisional/i).length).toBeGreaterThanOrEqual(1);
  });

  it("shows closure record link for gates with closure_record", () => {
    render(
      <CoordinationView
        gatesState={{ phase: "ready", data: gatesResponse() }}
        roadmapState={{ phase: "ready", data: CANONICAL_ROADMAP }}
        {...viewCallbacks}
      />,
    );
    expect(screen.getAllByText("closure record").length).toBeGreaterThanOrEqual(1);
  });

  it("shows per-product impacts for open gates", () => {
    render(
      <CoordinationView
        gatesState={{ phase: "ready", data: gatesResponse() }}
        roadmapState={{ phase: "ready", data: CANONICAL_ROADMAP }}
        {...viewCallbacks}
      />,
    );
    expect(screen.getAllByText("Blocks per workflow").length).toBeGreaterThan(0);
    expect(screen.getByText(/ad-revenue disbursement blocked/i)).toBeTruthy();
  });

  it("shows historical copy for closed gates with no impacts", () => {
    render(
      <CoordinationView
        gatesState={{ phase: "ready", data: gatesResponse() }}
        roadmapState={{ phase: "ready", data: CANONICAL_ROADMAP }}
        {...viewCallbacks}
      />,
    );
    expect(
      screen.getAllByText(/historical — no active per-product mapping/i),
    ).toHaveLength(2);
  });

  it("shows no reviewed mapping for open gates with no impacts", () => {
    const gates: GateView[] = [
      {
        gate_id: "G99",
        title: "Open gate with no impacts",
        status: "open",
        status_raw: "❌ OPEN",
        is_provisional: false,
        owner: null,
        blocks: null,
        closure_record: null,
        impacts: [],
      },
    ];
    render(
      <CoordinationView
        gatesState={{ phase: "ready", data: gatesResponse(gates) }}
        roadmapState={{ phase: "ready", data: CANONICAL_ROADMAP }}
        {...viewCallbacks}
      />,
    );
    expect(screen.getByText(/^no reviewed per-product mapping\.$/i)).toBeTruthy();
  });

  // ── Route Atlas ────────────────────────────────────────────────────

  it("renders reconciliation banner", () => {
    render(
      <CoordinationView
        gatesState={{ phase: "ready", data: gatesResponse() }}
        roadmapState={{ phase: "ready", data: CANONICAL_ROADMAP }}
        {...viewCallbacks}
      />,
    );
    expect(screen.getByText(/reconciled sprint count/i)).toBeTruthy();
    expect(screen.getByText(/Research 10 \+ Read 9/i)).toBeTruthy();
  });

  it("renders ordered critical path", () => {
    render(
      <CoordinationView
        gatesState={{ phase: "ready", data: gatesResponse() }}
        roadmapState={{ phase: "ready", data: CANONICAL_ROADMAP }}
        {...viewCallbacks}
      />,
    );
    const criticalLabel = screen.getByText(/^DRW critical path$/i);
    const criticalPath = criticalLabel.parentElement;
    expect(criticalPath).not.toBeNull();
    const nodes = within(criticalPath as HTMLElement).getAllByText(/^drw:\d+$/);
    expect(nodes.length).toBe(3);
  });

  it("renders rosters with correct counts", () => {
    render(
      <CoordinationView
        gatesState={{ phase: "ready", data: gatesResponse() }}
        roadmapState={{ phase: "ready", data: CANONICAL_ROADMAP }}
        {...viewCallbacks}
      />,
    );
    expect(screen.getByText("Research (DRW)")).toBeTruthy();
    expect(screen.getByText("10 sprints")).toBeTruthy();
    const readHeading = screen.getByRole("heading", { name: "Read", level: 3 });
    expect(within(readHeading.parentElement as HTMLElement).getByText("9 sprints")).toBeTruthy();
  });

  it("renders dependency-unblocked semantics correctly", () => {
    render(
      <CoordinationView
        gatesState={{ phase: "ready", data: gatesResponse() }}
        roadmapState={{ phase: "ready", data: CANONICAL_ROADMAP }}
        {...viewCallbacks}
      />,
    );
    // DRW sprints are unblocked
    expect(screen.getAllByText("unblocked").length).toBeGreaterThanOrEqual(1);
    // Read sprints are blocked on drw:5, drw:6
    expect(screen.getAllByText(/waits on drw:5, drw:6/).length).toBeGreaterThanOrEqual(1);
  });

  it("renders substrate layers", () => {
    render(
      <CoordinationView
        gatesState={{ phase: "ready", data: gatesResponse() }}
        roadmapState={{ phase: "ready", data: CANONICAL_ROADMAP }}
        {...viewCallbacks}
      />,
    );
    expect(screen.getByText(/substrate-execution layer/i)).toBeTruthy();
    expect(screen.getByText("Write coordination (db_lock)")).toBeTruthy();
  });

  // ── Loading states ─────────────────────────────────────────────────

  it("shows loading state for gates with polite aria-live", () => {
    render(
      <CoordinationView
        gatesState={{ phase: "loading" }}
        roadmapState={{ phase: "ready", data: CANONICAL_ROADMAP }}
        {...viewCallbacks}
      />,
    );
    expect(screen.getByText(/loading gate register/i)).toBeTruthy();
    expect(screen.getByText(/no status is inferred/i)).toBeTruthy();
  });

  it("shows loading state for roadmap", () => {
    render(
      <CoordinationView
        gatesState={{ phase: "ready", data: gatesResponse() }}
        roadmapState={{ phase: "loading" }}
        {...viewCallbacks}
      />,
    );
    expect(screen.getByText(/loading roadmap/i)).toBeTruthy();
  });

  // ── Error states ───────────────────────────────────────────────────

  it("renders gates error with retry button, retains roadmap", () => {
    render(
      <CoordinationView
        gatesState={{ phase: "error", copy: "Gate data temporarily unavailable." }}
        roadmapState={{ phase: "ready", data: CANONICAL_ROADMAP }}
        {...viewCallbacks}
      />,
    );
    expect(screen.getByText(/gate data unavailable/i)).toBeTruthy();
    expect(screen.getByText(/gate data temporarily unavailable/i)).toBeTruthy();
    const btn = screen.getByRole("button", { name: /retry gates/i });
    fireEvent.click(btn);
    expect(viewCallbacks.onRetryGates).toHaveBeenCalledTimes(1);
    // Roadmap still visible
    expect(screen.getByText("Research (DRW)")).toBeTruthy();
  });

  it("renders roadmap error with retry button, retains gates", () => {
    render(
      <CoordinationView
        gatesState={{ phase: "ready", data: gatesResponse() }}
        roadmapState={{ phase: "error", copy: "Roadmap data temporarily unavailable." }}
        {...viewCallbacks}
      />,
    );
    expect(screen.getByText(/roadmap unavailable/i)).toBeTruthy();
    const btn = screen.getByRole("button", { name: /retry roadmap/i });
    fireEvent.click(btn);
    expect(viewCallbacks.onRetryRoadmap).toHaveBeenCalledTimes(1);
    // Gates still visible
    expect(screen.getByText("G2")).toBeTruthy();
  });

  it("renders both errors — Werner empty mood", () => {
    render(
      <CoordinationView
        gatesState={{ phase: "error", copy: "Gate error." }}
        roadmapState={{ phase: "error", copy: "Roadmap error." }}
        {...viewCallbacks}
      />,
    );
    expect(screen.getByRole("img", { name: /werner found no data/i })).toBeTruthy();
  });

  it("renders malformed gates with safe copy", () => {
    render(
      <CoordinationView
        gatesState={{ phase: "malformed", copy: "Gate data arrived in unexpected format." }}
        roadmapState={{ phase: "ready", data: CANONICAL_ROADMAP }}
        {...viewCallbacks}
      />,
    );
    expect(screen.getByText(/gate data malformed/i)).toBeTruthy();
  });

  it("renders malformed roadmap with safe copy", () => {
    render(
      <CoordinationView
        gatesState={{ phase: "ready", data: gatesResponse() }}
        roadmapState={{ phase: "malformed", copy: "Roadmap data arrived in unexpected format." }}
        {...viewCallbacks}
      />,
    );
    expect(screen.getByText(/roadmap malformed/i)).toBeTruthy();
  });

  // ── Werner moods ───────────────────────────────────────────────────

  it("renders Werner thinking when either endpoint loading", () => {
    render(
      <CoordinationView
        gatesState={{ phase: "loading" }}
        roadmapState={{ phase: "ready", data: CANONICAL_ROADMAP }}
        {...viewCallbacks}
      />,
    );
    expect(screen.getByRole("img", { name: /werner is listening/i })).toBeTruthy();
  });

  it("renders Werner idle when both ready", () => {
    render(
      <CoordinationView
        gatesState={{ phase: "ready", data: gatesResponse() }}
        roadmapState={{ phase: "ready", data: CANONICAL_ROADMAP }}
        {...viewCallbacks}
      />,
    );
    expect(screen.getByRole("img", { name: /werner watches/i })).toBeTruthy();
  });

  it("renders Werner empty only when both error", () => {
    render(
      <CoordinationView
        gatesState={{ phase: "error", copy: "err" }}
        roadmapState={{ phase: "error", copy: "err" }}
        {...viewCallbacks}
      />,
    );
    expect(screen.getByRole("img", { name: /werner found no data/i })).toBeTruthy();
  });

  it("renders Werner idle when one error, one ready", () => {
    render(
      <CoordinationView
        gatesState={{ phase: "error", copy: "err" }}
        roadmapState={{ phase: "ready", data: CANONICAL_ROADMAP }}
        {...viewCallbacks}
      />,
    );
    expect(screen.getByRole("img", { name: /werner watches/i })).toBeTruthy();
  });

  // ── Night fixture ──────────────────────────────────────────────────

  it("forces night fixture independently of host media", () => {
    const { container } = render(
      <CoordinationView
        gatesState={{ phase: "ready", data: gatesResponse() }}
        roadmapState={{ phase: "ready", data: CANONICAL_ROADMAP }}
        fixtureTheme="dark"
        {...viewCallbacks}
      />,
    );
    expect(container.querySelector(".cga-shell")?.getAttribute("data-theme")).toBe("dark");
  });

  // ── Empty roster ───────────────────────────────────────────────────

  it("renders empty roster with fallback copy", () => {
    const emptyRosterRoadmap: RoadmapView = {
      ...CANONICAL_ROADMAP,
      rosters: [
        {
          spec: "empty",
          label: "Empty Spec",
          directory: "empty-spec",
          count: 0,
          sprints: [],
        },
      ],
      total_sprints: 0,
    };
    render(
      <CoordinationView
        gatesState={{ phase: "ready", data: gatesResponse() }}
        roadmapState={{ phase: "ready", data: emptyRosterRoadmap }}
        {...viewCallbacks}
      />,
    );
    expect(screen.getByText(/no sprint files found/i)).toBeTruthy();
  });

  // ── Raw error absence ──────────────────────────────────────────────

  it("never renders raw HTTP errors in the DOM", () => {
    render(
      <CoordinationView
        gatesState={{ phase: "error", copy: "Gate data is temporarily unavailable." }}
        roadmapState={{ phase: "error", copy: "Roadmap data is temporarily unavailable." }}
        {...viewCallbacks}
      />,
    );
    expect(screen.queryByText(/HTTP \d+/i)).toBeNull();
    expect(screen.queryByText(/500/i)).toBeNull();
    expect(screen.queryByText(/fetch/i)).toBeNull();
  });
});

// ── Coordination controller (integration) ─────────────────────────────

describe("Coordination controller", () => {
  beforeEach(() => vi.clearAllMocks());

  it("loads both endpoints on mount", async () => {
    vi.mocked(apiFetch).mockImplementation(async (url: RequestInfo | URL) => {
      const u = String(url);
      if (u.includes("/coordination/gates")) return response(gatesResponse());
      if (u.includes("/coordination/roadmap")) return response(CANONICAL_ROADMAP);
      return response(null, false);
    });
    render(<Coordination />);
    await waitFor(() => expect(apiFetch).toHaveBeenCalledTimes(2));
    expect(apiFetch).toHaveBeenCalledWith("/coordination/gates");
    expect(apiFetch).toHaveBeenCalledWith("/coordination/roadmap");
  });

  it("renders both panels on success", async () => {
    vi.mocked(apiFetch).mockImplementation(async (url: RequestInfo | URL) =>
      String(url).endsWith("/gates")
        ? response(gatesResponse())
        : response(CANONICAL_ROADMAP),
    );
    render(<Coordination />);
    expect(await screen.findByText("G2")).toBeTruthy();
    expect(await screen.findByText("Research (DRW)")).toBeTruthy();
  });

  it("retains healthy roadmap when gates fail", async () => {
    vi.mocked(apiFetch).mockImplementation(async (url: RequestInfo | URL) => {
      const u = String(url);
      if (u.includes("/coordination/gates")) return response(null, false);
      if (u.includes("/coordination/roadmap")) return response(CANONICAL_ROADMAP);
      return response(null, false);
    });
    render(<Coordination />);
    expect(await screen.findByText(/gate data unavailable/i)).toBeTruthy();
    expect(screen.getByText("Research (DRW)")).toBeTruthy();
  });

  it("retains healthy gates when roadmap fails", async () => {
    vi.mocked(apiFetch).mockImplementation(async (url: RequestInfo | URL) => {
      const u = String(url);
      if (u.includes("/coordination/gates")) return response(gatesResponse());
      if (u.includes("/coordination/roadmap")) return response(null, false);
      return response(null, false);
    });
    render(<Coordination />);
    expect(await screen.findByText("G2")).toBeTruthy();
    expect(screen.getByText(/roadmap unavailable/i)).toBeTruthy();
  });

  it("scoped retry: retries only gates when gates failed", async () => {
    let gatesCallCount = 0;
    vi.mocked(apiFetch).mockImplementation(async (url: RequestInfo | URL) => {
      const u = String(url);
      if (u.includes("/coordination/gates")) {
        gatesCallCount++;
        // First call fails, second succeeds
        return gatesCallCount === 1 ? response(null, false) : response(gatesResponse());
      }
      if (u.includes("/coordination/roadmap")) return response(CANONICAL_ROADMAP);
      return response(null, false);
    });
    render(<Coordination />);
    await screen.findByText(/gate data unavailable/i);

    // Now retry gates — should call only gates endpoint
    fireEvent.click(screen.getByRole("button", { name: /retry gates/i }));
    expect(await screen.findByText("G2")).toBeTruthy();
    expect(gatesCallCount).toBe(2);
  });

  it("scoped retry: retries only roadmap when roadmap failed", async () => {
    let roadmapCallCount = 0;
    vi.mocked(apiFetch).mockImplementation(async (url: RequestInfo | URL) => {
      const u = String(url);
      if (u.includes("/coordination/gates")) return response(gatesResponse());
      if (u.includes("/coordination/roadmap")) {
        roadmapCallCount++;
        return roadmapCallCount === 1 ? response(null, false) : response(CANONICAL_ROADMAP);
      }
      return response(null, false);
    });
    render(<Coordination />);
    await screen.findByText("G2");

    fireEvent.click(screen.getByRole("button", { name: /retry roadmap/i }));
    expect(await screen.findByText("Research (DRW)")).toBeTruthy();
    expect(roadmapCallCount).toBe(2);
  });

  it("rejects malformed gates response safely", async () => {
    vi.mocked(apiFetch).mockImplementation(async (url: RequestInfo | URL) => {
      const u = String(url);
      if (u.includes("/coordination/gates")) return response({ source_path: "test", gates: "not-an-array" });
      if (u.includes("/coordination/roadmap")) return response(CANONICAL_ROADMAP);
      return response(null, false);
    });
    render(<Coordination />);
    expect(await screen.findByText(/gate data malformed/i)).toBeTruthy();
    expect(screen.getByText("Research (DRW)")).toBeTruthy();
  });

  it("rejects malformed roadmap response safely", async () => {
    vi.mocked(apiFetch).mockImplementation(async (url: RequestInfo | URL) => {
      const u = String(url);
      if (u.includes("/coordination/gates")) return response(gatesResponse());
      if (u.includes("/coordination/roadmap")) return response({ total_sprints: "not-a-number" });
      return response(null, false);
    });
    render(<Coordination />);
    expect(await screen.findByText("G2")).toBeTruthy();
    expect(screen.getByText(/roadmap malformed/i)).toBeTruthy();
  });

  it("rejects gates with duplicate gate_id", async () => {
    const duped = [
      { ...CANONICAL_GATES[0] },
      { ...CANONICAL_GATES[0] },
    ];
    vi.mocked(apiFetch).mockImplementation(async (url: RequestInfo | URL) => {
      const u = String(url);
      if (u.includes("/coordination/gates")) return response(gatesResponse(duped));
      if (u.includes("/coordination/roadmap")) return response(CANONICAL_ROADMAP);
      return response(null, false);
    });
    render(<Coordination />);
    expect(await screen.findByText(/gate data malformed/i)).toBeTruthy();
  });

  it("rejects gates with invalid status", async () => {
    const bad = [{ ...CANONICAL_GATES[0], status: "invalid_status" } as unknown as GateView];
    vi.mocked(apiFetch).mockImplementation(async (url: RequestInfo | URL) => {
      const u = String(url);
      if (u.includes("/coordination/gates")) return response(gatesResponse(bad));
      if (u.includes("/coordination/roadmap")) return response(CANONICAL_ROADMAP);
      return response(null, false);
    });
    render(<Coordination />);
    expect(await screen.findByText(/gate data malformed/i)).toBeTruthy();
  });

  it("rejects gates with invalid product in impacts", async () => {
    const bad = [
      {
        ...CANONICAL_GATES[0],
        impacts: [{ product: "invalid", effect: "test" }],
      } as unknown as GateView,
    ];
    vi.mocked(apiFetch).mockImplementation(async (url: RequestInfo | URL) => {
      const u = String(url);
      if (u.includes("/coordination/gates")) return response(gatesResponse(bad));
      if (u.includes("/coordination/roadmap")) return response(CANONICAL_ROADMAP);
      return response(null, false);
    });
    render(<Coordination />);
    expect(await screen.findByText(/gate data malformed/i)).toBeTruthy();
  });

  it("rejects roadmap where total_sprints != sum of roster counts", async () => {
    const bad = { ...CANONICAL_ROADMAP, total_sprints: 999 };
    vi.mocked(apiFetch).mockImplementation(async (url: RequestInfo | URL) => {
      const u = String(url);
      if (u.includes("/coordination/gates")) return response(gatesResponse());
      if (u.includes("/coordination/roadmap")) return response(bad);
      return response(null, false);
    });
    render(<Coordination />);
    expect(await screen.findByText(/roadmap malformed/i)).toBeTruthy();
  });

  it("rejects roadmap with duplicate node_ids in a roster", async () => {
    const bad = { ...CANONICAL_ROADMAP };
    bad.rosters = [
      {
        ...bad.rosters[0],
        count: 2,
        sprints: [
          { ...bad.rosters[0].sprints[0] },
          { ...bad.rosters[0].sprints[0] },
        ],
      },
    ];
    bad.total_sprints = 2;
    vi.mocked(apiFetch).mockImplementation(async (url: RequestInfo | URL) => {
      const u = String(url);
      if (u.includes("/coordination/gates")) return response(gatesResponse());
      if (u.includes("/coordination/roadmap")) return response(bad);
      return response(null, false);
    });
    render(<Coordination />);
    expect(await screen.findByText(/roadmap malformed/i)).toBeTruthy();
  });

  it("rejects roadmap with invalid dependency reference", async () => {
    const bad = { ...CANONICAL_ROADMAP };
    bad.rosters = [
      {
        ...bad.rosters[0],
        count: 1,
        sprints: [
          {
            ...bad.rosters[0].sprints[0],
            blocked_on: ["nonexistent:99"],
            unblocked: false,
          },
        ],
      },
    ];
    bad.total_sprints = 1;
    vi.mocked(apiFetch).mockImplementation(async (url: RequestInfo | URL) => {
      const u = String(url);
      if (u.includes("/coordination/gates")) return response(gatesResponse());
      if (u.includes("/coordination/roadmap")) return response(bad);
      return response(null, false);
    });
    render(<Coordination />);
    expect(await screen.findByText(/roadmap malformed/i)).toBeTruthy();
  });

  it("rejects sprint with inconsistent unblocked/blocked_on", async () => {
    const bad = { ...CANONICAL_ROADMAP };
    bad.rosters = [
      {
        ...bad.rosters[0],
        count: 1,
        sprints: [
          {
            ...bad.rosters[0].sprints[0],
            unblocked: true,
            blocked_on: ["drw:2"],
          },
        ],
      },
    ];
    bad.total_sprints = 1;
    vi.mocked(apiFetch).mockImplementation(async (url: RequestInfo | URL) => {
      const u = String(url);
      if (u.includes("/coordination/gates")) return response(gatesResponse());
      if (u.includes("/coordination/roadmap")) return response(bad);
      return response(null, false);
    });
    render(<Coordination />);
    expect(await screen.findByText(/roadmap malformed/i)).toBeTruthy();
  });

  it("rejects roster where count != sprints.length", async () => {
    const bad = { ...CANONICAL_ROADMAP };
    bad.rosters = [
      {
        ...bad.rosters[0],
        count: 999,
      },
    ];
    vi.mocked(apiFetch).mockImplementation(async (url: RequestInfo | URL) => {
      const u = String(url);
      if (u.includes("/coordination/gates")) return response(gatesResponse());
      if (u.includes("/coordination/roadmap")) return response(bad);
      return response(null, false);
    });
    render(<Coordination />);
    expect(await screen.findByText(/roadmap malformed/i)).toBeTruthy();
  });

  it.each([
    ["duplicate roster spec", (bad: RoadmapView) => {
      bad.rosters = [bad.rosters[0], { ...bad.rosters[0] }];
      bad.total_sprints = bad.rosters[0].count * 2;
    }],
    ["sprint/roster spec mismatch", (bad: RoadmapView) => {
      bad.rosters = [{
        ...bad.rosters[0],
        sprints: bad.rosters[0].sprints.map((sprint, index) =>
          index === 0 ? { ...sprint, spec: "write" } : sprint),
      }];
      bad.total_sprints = bad.rosters[0].count;
    }],
    ["sprint/roster label mismatch", (bad: RoadmapView) => {
      bad.rosters = [{
        ...bad.rosters[0],
        sprints: bad.rosters[0].sprints.map((sprint, index) =>
          index === 0 ? { ...sprint, spec_label: "Wrong label" } : sprint),
      }];
      bad.total_sprints = bad.rosters[0].count;
    }],
    ["node id does not match canonical sprint identity", (bad: RoadmapView) => {
      bad.rosters = [{
        ...bad.rosters[0],
        sprints: bad.rosters[0].sprints.map((sprint, index) =>
          index === 0 ? { ...sprint, node_id: "drw:99" } : sprint),
      }];
      bad.total_sprints = bad.rosters[0].count;
    }],
  ])("rejects roadmap identity contradiction: %s", async (_label, mutate) => {
    const bad = structuredClone(CANONICAL_ROADMAP);
    mutate(bad);
    vi.mocked(apiFetch).mockImplementation(async (url: RequestInfo | URL) =>
      String(url).includes("/coordination/gates")
        ? response(gatesResponse())
        : response(bad),
    );
    render(<Coordination />);
    expect(await screen.findByText(/roadmap malformed/i)).toBeTruthy();
  });

  it("rejects gates with unsafe integer values", async () => {
    const bad = {
      ...gatesResponse(),
      gates: [{ ...CANONICAL_GATES[0], is_provisional: "not-boolean" } as unknown as GateView],
    };
    vi.mocked(apiFetch).mockImplementation(async (url: RequestInfo | URL) => {
      const u = String(url);
      if (u.includes("/coordination/gates")) return response(bad);
      if (u.includes("/coordination/roadmap")) return response(CANONICAL_ROADMAP);
      return response(null, false);
    });
    render(<Coordination />);
    expect(await screen.findByText(/gate data malformed/i)).toBeTruthy();
  });

  it("discards in-flight responses on unmount", async () => {
    let resolveGates!: (value: Response) => void;
    let resolveRoadmap!: (value: Response) => void;
    vi.mocked(apiFetch).mockImplementation(async (url: RequestInfo | URL) => {
      const u = String(url);
      if (u.includes("/coordination/gates"))
        return new Promise((r) => { resolveGates = r; });
      if (u.includes("/coordination/roadmap"))
        return new Promise((r) => { resolveRoadmap = r; });
      return response(null, false);
    });

    const consoleError = vi.spyOn(console, "error").mockImplementation(() => undefined);
    const { unmount } = render(<Coordination />);
    unmount();

    await act(async () => {
      resolveGates(response(gatesResponse()));
      resolveRoadmap(response(CANONICAL_ROADMAP));
      await Promise.resolve();
    });
    expect(consoleError).not.toHaveBeenCalled();
    consoleError.mockRestore();
  });

  it("discards JSON bodies that finish after unmount", async () => {
    let resolveGatesJson!: (value: unknown) => void;
    let resolveRoadmapJson!: (value: unknown) => void;
    let jsonCalls = 0;
    vi.mocked(apiFetch).mockImplementation(async (url: RequestInfo | URL) => ({
      ok: true,
      status: 200,
      json: () => {
        jsonCalls += 1;
        return new Promise((resolve) => {
          if (String(url).endsWith("/gates")) resolveGatesJson = resolve;
          else resolveRoadmapJson = resolve;
        });
      },
    } as Response));

    const consoleError = vi.spyOn(console, "error").mockImplementation(() => undefined);
    const { unmount } = render(<Coordination />);
    await waitFor(() => expect(jsonCalls).toBe(2));
    unmount();

    await act(async () => {
      resolveGatesJson(gatesResponse());
      resolveRoadmapJson(CANONICAL_ROADMAP);
      await Promise.resolve();
    });
    expect(consoleError).not.toHaveBeenCalled();
    consoleError.mockRestore();
  });

  it("discards an older response after a newer request wins", async () => {
    let resolveFirstGates!: (value: Response) => void;
    let gatesCalls = 0;
    const newestGates = CANONICAL_GATES.map((gate) =>
      gate.gate_id === "G2" ? { ...gate, title: "Newest gate register" } : gate,
    );
    const staleGates = CANONICAL_GATES.map((gate) =>
      gate.gate_id === "G2" ? { ...gate, title: "Stale gate register" } : gate,
    );

    vi.mocked(apiFetch).mockImplementation(async (url: RequestInfo | URL) => {
      if (String(url).endsWith("/gates")) {
        gatesCalls += 1;
        if (gatesCalls === 1) {
          return new Promise((resolve) => {
            resolveFirstGates = resolve;
          });
        }
        return response(gatesResponse(newestGates));
      }
      return response(CANONICAL_ROADMAP);
    });

    render(
      <StrictMode>
        <Coordination />
      </StrictMode>,
    );

    expect(await screen.findByText("Newest gate register")).toBeTruthy();
    expect(gatesCalls).toBe(2);

    await act(async () => {
      resolveFirstGates(response(gatesResponse(staleGates)));
      await Promise.resolve();
    });

    expect(screen.queryByText("Stale gate register")).toBeNull();
    expect(screen.getByText("Newest gate register")).toBeTruthy();
  });

  it("handles network errors gracefully without exposing raw errors", async () => {
    vi.mocked(apiFetch).mockImplementation(async (url: RequestInfo | URL) => {
      const u = String(url);
      if (u.includes("/coordination/gates")) throw new Error("ECONNREFUSED");
      if (u.includes("/coordination/roadmap")) return response(CANONICAL_ROADMAP);
      throw new Error("unknown");
    });
    render(<Coordination />);
    expect(await screen.findByText(/gate data unavailable/i)).toBeTruthy();
    expect(screen.queryByText(/ECONNREFUSED/i)).toBeNull();
    expect(screen.getByText("Research (DRW)")).toBeTruthy();
  });

  it("never renders raw backend errors in the DOM", async () => {
    vi.mocked(apiFetch).mockImplementation(async () => {
      throw new Error("TypeError: fetch failed");
    });
    render(<Coordination />);
    await screen.findByText(/coordination gatehouse atlas/i);
    expect(screen.queryByText(/TypeError/i)).toBeNull();
    expect(screen.queryByText(/NetworkError/i)).toBeNull();
  });
});
