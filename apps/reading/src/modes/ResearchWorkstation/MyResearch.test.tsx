/**
 * MyResearch.test.tsx — the one multi-research monitor (SPR-05 M1/M2/M4).
 *
 * Pins the load-bearing behaviour of the fold:
 *   - M1: ONE surface lists all researches in PLAIN LANGUAGE (working/done/
 *     stopped/needs attention), never a raw state; cascade + chase children
 *     group under their parent session.
 *   - M2: HONEST aggregate — "N running, M queued" reflects the real
 *     host-local semaphore cap read off the budget-defaults contract (the
 *     surplus past the cap is queued, not hidden); aggregate cost is the real
 *     sum of per-research cost, not an estimate.
 *   - M4: HONEST no-key state — an empty list shows the shared
 *     AIActionFailure no-provider sentence; the launch affordances disable
 *     with a clear reason when unauthenticated.
 *
 * The substrate list + the contract + auth are mocked at their module
 * boundaries, so this is a true unit of the monitor (no network, no socket).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import type { InvestigationSummary } from "../../lib/api";

const { listState, budgetState, authState, navigateMock } = vi.hoisted(() => ({
  listState: {
    current: {
      investigations: [] as InvestigationSummary[],
      loading: false,
      error: null as string | null,
      refetch: () => {},
    },
  },
  budgetState: {
    current: {
      per_research_cost_usd: 0.5,
      per_research_max_steps: 50,
      host_local_max_concurrency: 20,
    } as Record<string, number> | null,
  },
  authState: { current: { status: "authenticated" as "authenticated" | "unauthenticated" | "loading" } },
  navigateMock: vi.fn(),
}));

vi.mock("../../hooks/useInvestigationList", () => ({
  useInvestigationList: () => listState.current,
}));

vi.mock("../../api/research", async (orig) => {
  const actual = await orig<typeof import("../../api/research")>();
  return {
    ...actual,
    getBudgetDefaults: () =>
      budgetState.current
        ? Promise.resolve(budgetState.current)
        : Promise.reject(new Error("no provider")),
    // The monitor now hosts the SPR-09 "suggested next" lane; keep it
    // deterministic + offline here (empty → honest no-result), so these
    // monitor tests stay a true unit. SuggestedResearch has its own suite.
    getSuggestions: () => Promise.resolve({ count: 0, suggestions: [] }),
  };
});

vi.mock("../../lib/auth", async (orig) => {
  const actual = await orig<typeof import("../../lib/auth")>();
  return { ...actual, useAuth: () => ({ state: authState.current }) };
});

vi.mock("react-router-dom", async (orig) => {
  const actual = await orig<typeof import("react-router-dom")>();
  return { ...actual, useNavigate: () => navigateMock };
});

import MyResearch from "./MyResearch";

function inv(over: Partial<InvestigationSummary> & { investigation_id: string }): InvestigationSummary {
  return {
    question: "A question",
    status: "completed",
    started_at: new Date().toISOString(),
    completed_at: null,
    cost_usd_total: 0,
    parent_investigation_id: null,
    ...over,
  };
}

function renderMonitor() {
  return render(
    <MemoryRouter>
      <MyResearch />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  listState.current = {
    investigations: [],
    loading: false,
    error: null,
    refetch: () => {},
  };
  budgetState.current = {
    per_research_cost_usd: 0.5,
    per_research_max_steps: 50,
    host_local_max_concurrency: 20,
  };
  authState.current = { status: "authenticated" };
  navigateMock.mockReset();
});
afterEach(() => cleanup());

describe("MyResearch — one monitor, plain language (M1)", () => {
  it("shows plain-language status, never the raw state enum", async () => {
    listState.current.investigations = [
      inv({ investigation_id: "inv-aaa111", question: "Running one", status: "in_progress" }),
      inv({ investigation_id: "inv-bbb222", question: "Done one", status: "completed" }),
      inv({ investigation_id: "inv-ccc333", question: "Broken one", status: "failed" }),
    ];
    renderMonitor();
    // Plain words present on the row tags ("done" also appears in the
    // aggregate bar, so allow more than one)…
    expect(await screen.findByText("working")).toBeTruthy();
    expect(screen.getAllByText("done").length).toBeGreaterThan(0);
    expect(screen.getByText("needs attention")).toBeTruthy();
    // …and the raw enum tokens never rendered as a status.
    expect(screen.queryByText("in_progress")).toBeNull();
    expect(screen.queryByText("failed")).toBeNull();
  });

  it("badges a daemon-spawned research 'found by the loop', not an operator one (SPR-09)", async () => {
    listState.current.investigations = [
      inv({ investigation_id: "inv-loop01", question: "Loop launched this", status: "completed", spawned_by_daemon: true }),
      inv({ investigation_id: "inv-op01", question: "I launched this", status: "completed", spawned_by_daemon: false }),
    ];
    renderMonitor();
    // The loop-launched one carries the distinction badge; exactly one row has it.
    expect(await screen.findByText("found by the loop")).toBeTruthy();
    expect(screen.getAllByText("found by the loop").length).toBe(1);
  });

  it("groups cascade/chase children under their parent session", () => {
    listState.current.investigations = [
      inv({ investigation_id: "inv-parent01", question: "The big question", status: "in_progress" }),
      inv({ investigation_id: "inv-leaf01", question: "Sub one", status: "in_progress", parent_investigation_id: "inv-parent01" }),
      inv({ investigation_id: "inv-leaf02", question: "Sub two", status: "completed", parent_investigation_id: "inv-parent01" }),
      inv({ investigation_id: "inv-solo01", question: "Standalone", status: "completed" }),
    ];
    renderMonitor();
    // The family header names the parent (which also appears as its own row,
    // since the parent IS a research) + counts its members (parent + 2).
    expect(screen.getAllByText("The big question").length).toBeGreaterThan(0);
    expect(screen.getByText("3 researches")).toBeTruthy();
    // The standalone research is its own row, not under a family header.
    expect(screen.getByText("Standalone")).toBeTruthy();
  });
});

describe("MyResearch — honest aggregate (M2)", () => {
  it('shows "N running, M queued" against the real host-local cap', async () => {
    budgetState.current = {
      per_research_cost_usd: 0.5,
      per_research_max_steps: 50,
      host_local_max_concurrency: 2, // tiny cap so the surplus queues
    };
    listState.current.investigations = [
      inv({ investigation_id: "inv-r1", status: "in_progress" }),
      inv({ investigation_id: "inv-r2", status: "in_progress" }),
      inv({ investigation_id: "inv-r3", status: "in_progress" }),
    ];
    renderMonitor();
    // 3 in_progress, cap 2 → 2 running, 1 queued (visible, not a hang).
    const line = screen.getByTestId("concurrency-line");
    // The first render intentionally has no budget contract yet and may read
    // "3 running". Wait for getBudgetDefaults to resolve before asserting the
    // cap-derived state; grabbing the first matching DOM node made CI timing
    // decide whether this contract test passed.
    await waitFor(() => {
      expect(line.textContent).toContain("2 running");
      expect(line.textContent).toContain("1 queued");
    });
  });

  it("sums real per-research cost, not an estimate", () => {
    listState.current.investigations = [
      inv({ investigation_id: "inv-c1", status: "completed", cost_usd_total: 0.0123 }),
      inv({ investigation_id: "inv-c2", status: "completed", cost_usd_total: 0.0077 }),
    ];
    renderMonitor();
    // 0.0123 + 0.0077 = 0.0200 — the real sum, rendered to 4dp.
    expect(screen.getByText("$0.0200")).toBeTruthy();
  });
});

describe("MyResearch — honest no-key state + use-gate (M4)", () => {
  it("shows the honest no-result state when the list is empty", () => {
    listState.current.investigations = [];
    renderMonitor();
    // The shared no-provider sentence (AIActionFailure no-reason branch).
    expect(screen.getByText(/the engine returned no result/i)).toBeTruthy();
    expect(screen.getByText(/model provider isn/i)).toBeTruthy();
  });

  it("disables launch with a clear reason when unauthenticated", () => {
    authState.current = { status: "unauthenticated" };
    // Non-empty list so the empty-state retry button (also "Start a research")
    // doesn't collide — this test isolates the launch-bar gate.
    listState.current.investigations = [inv({ investigation_id: "inv-z1", status: "completed" })];
    renderMonitor();
    const start = screen.getByRole("button", { name: "Start a research" }) as HTMLButtonElement;
    const several = screen.getByRole("button", { name: "Launch several at once" }) as HTMLButtonElement;
    expect(start.disabled).toBe(true);
    expect(several.disabled).toBe(true);
    expect(screen.getByText(/Sign in to start a research/i)).toBeTruthy();
  });

  it("launch routes to the one start surface (no second composer)", async () => {
    listState.current.investigations = [
      inv({ investigation_id: "inv-x1", status: "completed" }),
    ];
    const { default: userEventModule } = await import("@testing-library/user-event");
    const user = userEventModule.setup();
    renderMonitor();
    await user.click(screen.getByRole("button", { name: "Launch several at once" }));
    expect(navigateMock).toHaveBeenCalledWith("/");
  });
});
