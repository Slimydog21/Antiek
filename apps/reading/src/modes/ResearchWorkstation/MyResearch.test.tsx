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
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import type { InvestigationSummary } from "../../lib/api";
import { useWindows } from "../../workspace/windowsStore";

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
  authState: {
    current: {
      status: "authenticated" as
        "authenticated" | "unauthenticated" | "loading",
    },
  },
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

import MyResearch, { ResearchLineageBoard } from "./MyResearch";

function inv(
  over: Partial<InvestigationSummary> & { investigation_id: string },
): InvestigationSummary {
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
  useWindows.getState().reset();
});
afterEach(() => cleanup());

describe("MyResearch — one monitor, plain language (M1)", () => {
  it("opens the stable review with only the ordered selected IDs and can clear the basket", async () => {
    listState.current.investigations = [
      inv({ investigation_id: "done-a", question: "Alpha" }),
      inv({ investigation_id: "done-b", question: "Beta" }),
    ];
    renderMonitor();

    fireEvent.click(await screen.findByLabelText("Select Alpha for composition"));
    fireEvent.click(screen.getByLabelText("Select Beta for composition"));
    fireEvent.click(screen.getByRole("button", { name: "Review 2 researches" }));

    const review = useWindows.getState().windows["win:research-composition-review"];
    expect(review.title).toBe("Collected research");
    expect(review.payload).toEqual({ investigationIds: ["done-a", "done-b"] });
    fireEvent.click(screen.getByRole("button", { name: "Clear" }));
    expect(screen.queryByLabelText("Research composition selection")).toBeNull();
  });

  it("offers ordered controlled selection only for completed rows and caps it at eight", () => {
    const completed = Array.from({ length: 9 }, (_, index) => inv({
      investigation_id: `done-${index}`,
      question: `Done ${index}`,
    }));
    const onSelectionChange = vi.fn();
    const view = render(
      <MemoryRouter>
        <ResearchLineageBoard
          investigations={[...completed, inv({ investigation_id: "running", question: "Running", status: "in_progress" })]}
          selectedInvestigationIds={completed.slice(0, 8).map((item) => item.investigation_id)}
          onSelectionChange={onSelectionChange}
        />
      </MemoryRouter>,
    );
    expect(screen.queryByLabelText("Select Running for composition")).toBeNull();
    expect(
      (screen.getByLabelText("Select Done 8 for composition") as HTMLInputElement).disabled,
    ).toBe(true);

    fireEvent.click(screen.getByLabelText("Select Done 0 for composition"));
    expect(onSelectionChange).toHaveBeenLastCalledWith(completed.slice(1, 8).map((item) => item.investigation_id));
    view.rerender(
      <MemoryRouter>
        <ResearchLineageBoard investigations={completed} selectedInvestigationIds={["done-1"]} onSelectionChange={onSelectionChange} />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByLabelText("Select Done 0 for composition"));
    expect(onSelectionChange).toHaveBeenLastCalledWith(["done-1", "done-0"]);
  });
  it("shows plain-language status, never the raw state enum", async () => {
    listState.current.investigations = [
      inv({
        investigation_id: "inv-aaa111",
        question: "Running one",
        status: "in_progress",
      }),
      inv({
        investigation_id: "inv-bbb222",
        question: "Done one",
        status: "completed",
      }),
      inv({
        investigation_id: "inv-ccc333",
        question: "Broken one",
        status: "failed",
      }),
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
      inv({
        investigation_id: "inv-loop01",
        question: "Loop launched this",
        status: "completed",
        spawned_by_daemon: true,
      }),
      inv({
        investigation_id: "inv-op01",
        question: "I launched this",
        status: "completed",
        spawned_by_daemon: false,
      }),
    ];
    renderMonitor();
    // The loop-launched one carries the distinction badge; exactly one row has it.
    expect(await screen.findByText("found by the loop")).toBeTruthy();
    expect(screen.getAllByText("found by the loop").length).toBe(1);
  });

  it("groups cascade/chase children under their parent session", () => {
    listState.current.investigations = [
      inv({
        investigation_id: "inv-parent01",
        question: "The big question",
        status: "in_progress",
      }),
      inv({
        investigation_id: "inv-leaf01",
        question: "Sub one",
        status: "in_progress",
        parent_investigation_id: "inv-parent01",
      }),
      inv({
        investigation_id: "inv-leaf02",
        question: "Sub two",
        status: "completed",
        parent_investigation_id: "inv-parent01",
      }),
      inv({
        investigation_id: "inv-solo01",
        question: "Standalone",
        status: "completed",
      }),
    ];
    renderMonitor();
    // The family header names the parent (which also appears as its own row,
    // since the parent IS a research) + counts its members (parent + 2).
    expect(screen.getAllByText("The big question").length).toBeGreaterThan(0);
    expect(screen.queryByText("3 researches")).toBeNull();
    // The standalone research is its own row, not under a family header.
    expect(screen.getByText("Standalone")).toBeTruthy();
    expect(screen.getByText("Research family")).toBeTruthy();
    expect(screen.getByText("2 branches")).toBeTruthy();
    expect(screen.getByText("Origin")).toBeTruthy();
    expect(screen.getByText("Branch 01")).toBeTruthy();
    expect(screen.getByText("Branch 02")).toBeTruthy();
    expect(
      document.querySelectorAll('[data-lineage-role="branch"]'),
    ).toHaveLength(2);
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
      inv({
        investigation_id: "inv-c1",
        status: "completed",
        cost_usd_total: 0.0123,
      }),
      inv({
        investigation_id: "inv-c2",
        status: "completed",
        cost_usd_total: 0.0077,
      }),
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
    listState.current.investigations = [
      inv({ investigation_id: "inv-z1", status: "completed" }),
    ];
    renderMonitor();
    const start = screen.getByRole("button", {
      name: "Start a research",
    }) as HTMLButtonElement;
    const several = screen.getByRole("button", {
      name: "Launch several at once",
    }) as HTMLButtonElement;
    expect(start.disabled).toBe(true);
    expect(several.disabled).toBe(true);
    expect(screen.getByText(/Sign in to start a research/i)).toBeTruthy();
  });

  it("launch routes to the one start surface (no second composer)", async () => {
    listState.current.investigations = [
      inv({ investigation_id: "inv-x1", status: "completed" }),
    ];
    const { default: userEventModule } =
      await import("@testing-library/user-event");
    const user = userEventModule.setup();
    renderMonitor();
    await user.click(
      screen.getByRole("button", { name: "Launch several at once" }),
    );
    expect(navigateMock).toHaveBeenCalledWith("/");
  });
});

// ── Lineage board: tree structure (the visual hierarchy) ────────────────
//
// Focused tests for ResearchLineageBoard — the pure component that renders
// the parent/child tree. Uses the component directly (no hooks) so these
// are true unit tests of the tree-building and rendering logic.

describe("ResearchLineageBoard — tree structure", () => {
  function renderBoard(investigations: InvestigationSummary[]) {
    return render(
      <MemoryRouter>
        <ResearchLineageBoard investigations={investigations} />
      </MemoryRouter>,
    );
  }

  it("renders a family header with origin and branch labels for a parent+children group", () => {
    renderBoard([
      inv({ investigation_id: "inv-root", question: "The big question" }),
      inv({ investigation_id: "inv-a", question: "Sub A", parent_investigation_id: "inv-root" }),
      inv({ investigation_id: "inv-b", question: "Sub B", parent_investigation_id: "inv-root" }),
    ]);
    // Family header
    expect(screen.getByText("Research family")).toBeTruthy();
    // Family header + root row both show the question
    expect(screen.getAllByText("The big question").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText("2 branches")).toBeTruthy();
    // Origin label on the root row
    expect(screen.getByText("Origin")).toBeTruthy();
    // Branch labels (one-indexed, zero-padded)
    expect(screen.getByText("Branch 01")).toBeTruthy();
    expect(screen.getByText("Branch 02")).toBeTruthy();
    // data-lineage-role attributes on the li elements
    expect(document.querySelectorAll('[data-lineage-role="origin"]')).toHaveLength(1);
    expect(document.querySelectorAll('[data-lineage-role="branch"]')).toHaveLength(2);
  });

  it("renders standalone research as a flat card with no family header", () => {
    renderBoard([
      inv({ investigation_id: "inv-solo", question: "Standalone topic" }),
    ]);
    // No family header
    expect(screen.queryByText("Research family")).toBeNull();
    expect(screen.queryByText("Origin")).toBeNull();
    // The research question is rendered
    expect(screen.getByText("Standalone topic")).toBeTruthy();
    // Standalone role attribute
    expect(document.querySelectorAll('[data-lineage-role="standalone"]')).toHaveLength(1);
  });

  it("marks children as 'found by the loop' when spawned_by_daemon is true", () => {
    renderBoard([
      inv({ investigation_id: "inv-root", question: "Root" }),
      inv({
        investigation_id: "inv-child",
        question: "Daemon child",
        parent_investigation_id: "inv-root",
        spawned_by_daemon: true,
      }),
    ]);
    expect(screen.getByText("found by the loop")).toBeTruthy();
  });

  it("renders recursive descendants once inside their original family", () => {
    renderBoard([
      inv({ investigation_id: "inv-root", question: "Root question" }),
      inv({
        investigation_id: "inv-child",
        question: "Child question",
        parent_investigation_id: "inv-root",
      }),
      inv({
        investigation_id: "inv-grandchild",
        question: "Grandchild question",
        parent_investigation_id: "inv-child",
      }),
    ]);

    expect(screen.getAllByText("Research family")).toHaveLength(1);
    expect(screen.getByText("2 branches")).toBeTruthy();
    expect(screen.getByText("Grandchild question")).toBeTruthy();
    expect(screen.getByText("Depth 2 · Branch 01")).toBeTruthy();
    expect(document.querySelectorAll('[data-lineage-role="branch"]')).toHaveLength(2);
    expect(document.querySelectorAll('[data-lineage-depth="2"]')).toHaveLength(1);
  });

  it("returns null when the investigations list is empty", () => {
    const { container } = renderBoard([]);
    expect(container.innerHTML).toBe("");
  });

  it("handles orphan children (parent not in the list) as standalone roots", () => {
    renderBoard([
      inv({
        investigation_id: "inv-orphan",
        question: "Orphan child",
        parent_investigation_id: "inv-missing",
      }),
    ]);
    // No family header — the orphan becomes a standalone root.
    expect(screen.queryByText("Research family")).toBeNull();
    expect(screen.getByText("Orphan child")).toBeTruthy();
    expect(document.querySelectorAll('[data-lineage-role="standalone"]')).toHaveLength(1);
  });

  it("keeps cyclic lineage visible as standalone roots", () => {
    renderBoard([
      inv({
        investigation_id: "inv-cycle-a",
        question: "Cycle A",
        parent_investigation_id: "inv-cycle-b",
      }),
      inv({
        investigation_id: "inv-cycle-b",
        question: "Cycle B",
        parent_investigation_id: "inv-cycle-a",
      }),
    ]);

    expect(screen.getByText("Cycle A")).toBeTruthy();
    expect(screen.getByText("Cycle B")).toBeTruthy();
    expect(document.querySelectorAll('[data-lineage-role="standalone"]')).toHaveLength(2);
  });

  it("renders a repeated investigation id only once", () => {
    renderBoard([
      inv({ investigation_id: "inv-duplicate", question: "Canonical row" }),
      inv({ investigation_id: "inv-duplicate", question: "Repeated row" }),
    ]);

    expect(screen.getByText("Canonical row")).toBeTruthy();
    expect(screen.queryByText("Repeated row")).toBeNull();
    expect(document.querySelectorAll('[data-lineage-role="standalone"]')).toHaveLength(1);
  });

  it("separates independent families and standalones into distinct sections", () => {
    renderBoard([
      inv({ investigation_id: "inv-fam-root", question: "Family root" }),
      inv({ investigation_id: "inv-fam-child", question: "Family child", parent_investigation_id: "inv-fam-root" }),
      inv({ investigation_id: "inv-solo", question: "Lone research" }),
    ]);
    // Two sections: one family, one standalone
    const sections = document.querySelectorAll("section.research-lineage");
    expect(sections).toHaveLength(2);
    // Family root appears in header + origin row
    expect(screen.getAllByText("Family root").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText("Family child")).toBeTruthy();
    expect(screen.getByText("Lone research")).toBeTruthy();
    // Exactly one family header
    expect(screen.getAllByText("Research family")).toHaveLength(1);
    // Exactly one standalone role
    expect(document.querySelectorAll('[data-lineage-role="standalone"]')).toHaveLength(1);
  });
});

// ── Chart Room environment (investigation-chart-room) ──────────────────
//
// Focused tests for the decorative Chart Room frame on standalone
// MyResearch. Embedded mode must be visually and behaviourally unchanged.

describe("Chart Room — standalone frame and art", () => {
  it("renders the Chart Room frame with decorative art on standalone MyResearch", () => {
    listState.current.investigations = [
      inv({ investigation_id: "inv-cr01", status: "completed" }),
    ];
    renderMonitor();
    const frame = screen.getByTestId("chart-room-frame");
    expect(frame).toBeTruthy();
    expect(frame.classList.contains("investigation-chart-room")).toBe(true);
    const art = screen.getByTestId("investigation-chart-room-art");
    expect(art).toBeTruthy();
    expect(art.tagName).toBe("IMG");
    expect(art.getAttribute("alt")).toBe("");
    expect(art.getAttribute("aria-hidden")).toBe("true");
    expect(art.getAttribute("loading")).toBe("lazy");
    expect(art.getAttribute("decoding")).toBe("async");
    expect(art.getAttribute("draggable")).toBe("false");
  });

  it("shows the masthead heading and subtitle on standalone MyResearch", () => {
    listState.current.investigations = [
      inv({ investigation_id: "inv-cr02", status: "completed" }),
    ];
    renderMonitor();
    expect(screen.getByText("My research")).toBeTruthy();
    expect(
      screen.getByText(/Every research you have running and finished/),
    ).toBeTruthy();
  });
});

describe("Chart Room — embedded absence", () => {
  it("does not render the Chart Room frame or art when embedded", () => {
    listState.current.investigations = [
      inv({ investigation_id: "inv-cr03", status: "completed" }),
    ];
    render(
      <MemoryRouter>
        <MyResearch embedded />
      </MemoryRouter>,
    );
    expect(screen.queryByTestId("chart-room-frame")).toBeNull();
    expect(screen.queryByTestId("investigation-chart-room-art")).toBeNull();
    expect(screen.getByText("Your research")).toBeTruthy();
  });
});

describe("Chart Room — root launch navigation", () => {
  it("launch bar navigates to root / on 'Start a research'", async () => {
    listState.current.investigations = [
      inv({ investigation_id: "inv-cr04", status: "completed" }),
    ];
    const { default: userEventModule } =
      await import("@testing-library/user-event");
    const user = userEventModule.setup();
    renderMonitor();
    await user.click(
      screen.getByRole("button", { name: "Start a research" }),
    );
    expect(navigateMock).toHaveBeenCalledWith("/");
  });
});

describe("Chart Room — encoded workstation and replay links", () => {
  it("encodes investigation id in the workstation link", () => {
    listState.current.investigations = [
      inv({
        investigation_id: "inv/slash id",
        question: "Encoded question",
        status: "completed",
      }),
    ];
    renderMonitor();
    const link = screen.getByText("Encoded question").closest("a");
    expect(link).toBeTruthy();
    expect(link!.getAttribute("href")).toBe(
      "/inv/" + encodeURIComponent("inv/slash id"),
    );
  });

  it("encodes investigation id in the replay link", () => {
    listState.current.investigations = [
      inv({
        investigation_id: "inv/slash id",
        question: "Encoded question",
        status: "completed",
      }),
    ];
    renderMonitor();
    const replayLink = screen.getByText("replay →").closest("a");
    expect(replayLink).toBeTruthy();
    expect(replayLink!.getAttribute("href")).toBe(
      "/replay/" + encodeURIComponent("inv/slash id"),
    );
  });
});

describe("Chart Room — private-safe list failure", () => {
  it("shows the honest no-result state with AIActionFailure when the list is empty", () => {
    listState.current.investigations = [];
    renderMonitor();
    expect(screen.getByText(/the engine returned no result/i)).toBeTruthy();
    expect(screen.getByText(/model provider isn/i)).toBeTruthy();
  });

  it("shows fixed recovery copy without exposing the API error reason", () => {
    listState.current = {
      investigations: [],
      loading: false,
      error: "Forbidden: private investigation list",
      refetch: () => {},
    };
    renderMonitor();
    expect(screen.getByText(/Couldn\u2019t load your research/)).toBeTruthy();
    expect(screen.queryByText(/Forbidden: private investigation list/)).toBeNull();
  });
});
