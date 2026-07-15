import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";

import { ResearchIndexView } from "./InvestigationSidebar";
import type { ResearchIndexViewProps, TreeNode } from "./InvestigationSidebar";
import type { InvestigationSummary } from "../../lib/api";

const FIXED_NOW_MS = Date.parse("2026-07-15T12:00:00Z");

function inv(
  over: Partial<InvestigationSummary> & { investigation_id: string },
): InvestigationSummary {
  return {
    question: "A research question",
    status: "completed",
    started_at: "2026-07-10T09:00:00Z",
    completed_at: null,
    cost_usd_total: 0,
    parent_investigation_id: null,
    ...over,
  };
}

function node(
  summary: InvestigationSummary,
  children: TreeNode[] = [],
): TreeNode {
  return { investigationId: summary.investigation_id, summary, children };
}

function renderView(overrides: Partial<ResearchIndexViewProps> = {}) {
  const defaults: ResearchIndexViewProps = {
    tree: [],
    activeId: null,
    loading: false,
    error: null,
    onRefresh: () => {},
    nowMs: FIXED_NOW_MS,
  };
  return render(
    <MemoryRouter>
      <ResearchIndexView {...defaults} {...overrides} />
    </MemoryRouter>,
  );
}

afterEach(() => cleanup());

describe("ResearchIndexView — routing", () => {
  it("renders NavLink targets to /inv/{id} for each investigation", () => {
    const tree = [
      node(inv({ investigation_id: "inv-aaa" })),
      node(inv({ investigation_id: "inv-bbb" })),
    ];
    renderView({ tree });
    const links = screen.getAllByRole("link");
    const hrefs = links.map((a) => a.getAttribute("href"));
    expect(hrefs).toContain("/inv/inv-aaa");
    expect(hrefs).toContain("/inv/inv-bbb");
  });

  it("renders nested children with links to /inv/{childId}", () => {
    const tree = [
      node(inv({ investigation_id: "inv-parent", question: "Parent Q" }), [
        node(inv({ investigation_id: "inv-child-1", question: "Child Q", parent_investigation_id: "inv-parent" })),
      ]),
    ];
    renderView({ tree });
    const links = screen.getAllByRole("link");
    expect(links.some((a) => a.getAttribute("href") === "/inv/inv-parent")).toBe(true);
    expect(links.some((a) => a.getAttribute("href") === "/inv/inv-child-1")).toBe(true);
  });
});

describe("ResearchIndexView — active state", () => {
  it("applies aria-current='page' to the active investigation link", () => {
    const tree = [
      node(inv({ investigation_id: "inv-active", question: "Active one" })),
      node(inv({ investigation_id: "inv-other", question: "Other one" })),
    ];
    renderView({ tree, activeId: "inv-active" });
    const activeLink = document.querySelector('a[aria-current="page"]');
    expect(activeLink).toBeTruthy();
    expect(activeLink?.textContent).toContain("Active one");
  });

  it("adds the active modifier class to the active link", () => {
    const tree = [
      node(inv({ investigation_id: "inv-1", question: "First" })),
    ];
    renderView({ tree, activeId: "inv-1" });
    const link = screen.getByText("First").closest("a");
    expect(link?.className).toContain("ris__link--active");
  });

  it("does not mark non-active items with aria-current", () => {
    const tree = [
      node(inv({ investigation_id: "inv-active", question: "Active" })),
      node(inv({ investigation_id: "inv-other", question: "Other" })),
    ];
    renderView({ tree, activeId: "inv-active" });
    const items = document.querySelectorAll('[aria-current="page"]');
    expect(items).toHaveLength(1);
  });
});

describe("ResearchIndexView — collapse aria-expanded", () => {
  it("renders disclosure buttons with aria-expanded for parent nodes", () => {
    const tree = [
      node(inv({ investigation_id: "inv-root" }), [
        node(inv({ investigation_id: "inv-child" })),
      ]),
    ];
    renderView({ tree });
    const expandBtns = screen.getAllByRole("button", { name: "Collapse" });
    expect(expandBtns).toHaveLength(1);
    expect(expandBtns[0].getAttribute("aria-expanded")).toBe("true");
  });

  it("toggles aria-expanded when disclosure button is clicked", async () => {
    const user = userEvent.setup();
    const tree = [
      node(inv({ investigation_id: "inv-root" }), [
        node(inv({ investigation_id: "inv-child", question: "Child question" })),
      ]),
    ];
    renderView({ tree });
    const btn = screen.getByRole("button", { name: "Collapse" });
    await user.click(btn);
    expect(btn.getAttribute("aria-expanded")).toBe("false");
    expect(btn.getAttribute("aria-label")).toBe("Expand");
    const target = document.getElementById(btn.getAttribute("aria-controls") ?? "");
    expect(target?.hidden).toBe(true);
  });

  it("does not render disclosure button for leaf nodes", () => {
    const tree = [node(inv({ investigation_id: "inv-leaf" }))];
    renderView({ tree });
    expect(screen.queryByRole("button", { name: /expand|collapse/i })).toBeNull();
  });
});

describe("ResearchIndexView — status labels (all five)", () => {
  it("renders visible text label for in_progress", () => {
    renderView({ tree: [node(inv({ investigation_id: "a", status: "in_progress" }))] });
    expect(screen.getByText("in progress")).toBeTruthy();
  });

  it("renders visible text label for completed", () => {
    renderView({ tree: [node(inv({ investigation_id: "a", status: "completed" }))] });
    expect(screen.getByText("completed")).toBeTruthy();
  });

  it("renders visible text label for failed", () => {
    renderView({ tree: [node(inv({ investigation_id: "a", status: "failed" }))] });
    expect(screen.getByText("failed")).toBeTruthy();
  });

  it("renders visible text label for stopped", () => {
    renderView({ tree: [node(inv({ investigation_id: "a", status: "stopped" }))] });
    expect(screen.getByText("stopped")).toBeTruthy();
  });

  it("renders visible text label for not_found", () => {
    renderView({ tree: [node(inv({ investigation_id: "a", status: "not_found" }))] });
    expect(screen.getByText("not found")).toBeTruthy();
  });

  it("never renders raw status enum as visible text", () => {
    renderView({
      tree: [
        node(inv({ investigation_id: "a", status: "in_progress" })),
        node(inv({ investigation_id: "b", status: "failed" })),
      ],
    });
    expect(screen.queryByText("in_progress")).toBeNull();
    expect(screen.getByText("failed")).toBeTruthy();
  });
});

describe("ResearchIndexView — cost and time", () => {
  it("renders cost to exactly four decimal places", () => {
    const tree = [
      node(inv({ investigation_id: "a", cost_usd_total: 0.1234 })),
      node(inv({ investigation_id: "b", cost_usd_total: 0.005 })),
    ];
    renderView({ tree });
    // Cost text lives inside the same .ris__meta div as the age, so use regex
    expect(screen.getByText(/\$0\.1234/)).toBeTruthy();
    expect(screen.getByText(/\$0\.0050/)).toBeTruthy();
  });

  it("renders $0.0000 when cost is 0", () => {
    renderView({ tree: [node(inv({ investigation_id: "a", cost_usd_total: 0 }))] });
    expect(screen.getByText(/\$0\.0000/)).toBeTruthy();
  });

  it("renders deterministic relative time using nowMs", () => {
    // started_at: 2026-07-10T09:00:00Z, nowMs: 2026-07-15T12:00:00Z
    // = 5 days, 3 hours ago → "5d ago"
    const tree = [
      node(inv({ investigation_id: "a", started_at: "2026-07-10T09:00:00Z" })),
    ];
    renderView({ tree });
    expect(screen.getByText(/\$0\.0000 \u00B7 5d ago/)).toBeTruthy();
  });

  it("renders minutes ago for recent timestamps", () => {
    // 30 minutes before nowMs
    const tree = [
      node(inv({ investigation_id: "a", started_at: "2026-07-15T11:30:00Z" })),
    ];
    renderView({ tree });
    expect(screen.getByText(/30m ago/)).toBeTruthy();
  });

  it("omits invalid and future ages instead of inventing time", () => {
    const tree = [
      node(inv({ investigation_id: "bad", question: "Bad clock", started_at: "not-a-date" })),
      node(inv({ investigation_id: "future", question: "Future clock", started_at: "2026-07-16T12:00:00Z" })),
    ];
    renderView({ tree });
    const metadata = Array.from(document.querySelectorAll(".ris__meta"));
    expect(metadata.map((element) => element.textContent)).toEqual(["$0.0000", "$0.0000"]);
    expect(screen.queryByText(/invalid|nan|just now/i)).toBeNull();
  });

  it("does not invent a zero cost when a tree summary is unavailable", () => {
    renderView({ tree: [{ investigationId: "legacy-node", summary: null, children: [] }] });
    expect(screen.getByText("cost unavailable")).toBeTruthy();
    expect(screen.getByText("status unavailable")).toBeTruthy();
    expect(screen.queryByText("in progress")).toBeNull();
  });

  it("keeps the full question on the link when visible copy is truncated", () => {
    const question = "A deliberately long research question that exceeds sixty characters and remains fully inspectable";
    renderView({ tree: [node(inv({ investigation_id: "long", question }))] });
    expect(screen.getByRole("link").getAttribute("title")).toBe(question);
  });
});

describe("ResearchIndexView — state truth", () => {
  it("shows initial loading when loading=true and hasRows=false", () => {
    renderView({ loading: true });
    expect(screen.getByText(/loading research index/i)).toBeTruthy();
    expect(screen.getByRole("navigation", { name: "Research index" }).getAttribute("aria-busy")).toBe("true");
    expect(screen.queryByRole("list")).toBeNull();
  });

  it("shows empty state when not loading, no error, empty tree", () => {
    renderView({ loading: false, error: null, tree: [] });
    expect(screen.getByText(/no investigations yet/i)).toBeTruthy();
  });

  it("shows terminal error with retry button when error and no rows", () => {
    const onRefresh = vi.fn();
    renderView({ error: "Connection refused", onRefresh });
    expect(screen.getByText("Connection refused")).toBeTruthy();
    expect(screen.getByRole("alert")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Retry" })).toBeTruthy();
  });

  it("calls onRefresh when retry button is clicked", async () => {
    const user = userEvent.setup();
    const onRefresh = vi.fn();
    renderView({ error: "Network error", onRefresh });
    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(onRefresh).toHaveBeenCalledOnce();
  });

  it("shows stale-data warning when error + hasRows", () => {
    const tree = [node(inv({ investigation_id: "a", question: "Cached" }))];
    renderView({ tree, error: "Timeout" });
    expect(screen.getByText(/could not refresh/i)).toBeTruthy();
    // The tree is still visible
    expect(screen.getByText("Cached")).toBeTruthy();
  });

  it("hides stale warning when no error", () => {
    const tree = [node(inv({ investigation_id: "a" }))];
    renderView({ tree, error: null });
    expect(screen.queryByText(/could not refresh/i)).toBeNull();
  });
});

describe("ResearchIndexView — refresh", () => {
  it("calls onRefresh when the header refresh button is clicked", async () => {
    const user = userEvent.setup();
    const onRefresh = vi.fn();
    renderView({ onRefresh });
    await user.click(screen.getByRole("button", { name: /refresh investigations/i }));
    expect(onRefresh).toHaveBeenCalledOnce();
  });
});

describe("ResearchIndexView — tree structure", () => {
  it("renders a nested tree with trunk and branch arms", () => {
    const tree = [
      node(inv({ investigation_id: "root", question: "Root" }), [
        node(inv({ investigation_id: "child1", question: "Child 1" })),
        node(inv({ investigation_id: "child2", question: "Child 2" })),
      ]),
    ];
    renderView({ tree });
    expect(screen.getByText("Root")).toBeTruthy();
    expect(screen.getByText("Child 1")).toBeTruthy();
    expect(screen.getByText("Child 2")).toBeTruthy();
    const lists = screen.getAllByRole("list");
    expect(lists.length).toBeGreaterThanOrEqual(2);
  });

  it("renders 3-generation depth correctly", () => {
    const tree = [
      node(inv({ investigation_id: "root" }), [
        node(inv({ investigation_id: "child" }), [
          node(inv({ investigation_id: "grandchild", question: "Deep node" })),
        ]),
      ]),
    ];
    renderView({ tree });
    expect(screen.getByText("Deep node")).toBeTruthy();
    expect(Array.from(document.querySelectorAll("li")).map((item) => item.dataset.depth)).toEqual([
      "0",
      "1",
      "2",
    ]);
  });

  it("associates disclosure state with the nested child list", () => {
    const tree = [
      node(inv({ investigation_id: "root" }), [
        node(inv({ investigation_id: "child" })),
      ]),
    ];
    renderView({ tree });
    const disclosure = screen.getByRole("button", { name: "Collapse" });
    const target = document.getElementById(disclosure.getAttribute("aria-controls") ?? "");
    expect(disclosure.getAttribute("aria-expanded")).toBe("true");
    expect(target).toBeTruthy();
  });
});
