/**
 * FFX SPR-04 M2 (F-11) + M3 page half (A-14): the monitor never prints a cost
 * it was not given, and a session that does not exist is a terminal page,
 * not an endless "reconnecting…" with a raw transport line.
 */
import { cleanup, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

const sessionView = vi.hoisted(() => ({
  current: {} as Record<string, unknown>,
}));

vi.mock("./ResearchWaitArcade", () => ({ default: () => null }));
vi.mock("./Canvas/Canvas", () => ({ default: () => null }));
vi.mock("../../components/windows/openWindow", () => ({ openWindow: vi.fn() }));
vi.mock("../../lib/analytics", () => ({ track: vi.fn() }));
vi.mock("../../arcade/waitArcadeFlag", () => ({ mascotResearchWaitArcadeEnabled: false }));
vi.mock("../../workspace/PanelHost", () => ({
  PanelHost: ({ children }: { children: ReactNode }) => children,
}));
vi.mock("./useResearchSession", () => ({
  useResearchSession: () => sessionView.current,
}));
vi.mock("./useMascotResearchReactions", () => ({
  useMascotResearchReactions: () => undefined,
}));

import { Monitor } from ".";

const researches = [
  { investigation_id: "inv-aaaaaaaaaaaa", sub_question: "First question", state: "running" },
  { investigation_id: "inv-bbbbbbbbbbbb", sub_question: "Second question", state: "running" },
];

function view(over: Record<string, unknown>) {
  return {
    researches,
    cost: null,
    hardCeiling: null,
    live: true,
    allTerminal: false,
    loading: false,
    sourcePolicy: [],
    sourcePolicyExecution: null,
    error: null,
    ...over,
  };
}

function renderMonitor() {
  return render(
    <MemoryRouter>
      <Monitor sessionId="s-1" sessionGeneration={0} busy={false} />
    </MemoryRouter>,
  );
}

afterEach(() => cleanup());

describe("DRW monitor — cost honesty (F-11)", () => {
  it("shows no $0.0000 in any panel while the session cost is unknown", () => {
    sessionView.current = view({ cost: null });
    const { container } = renderMonitor();
    expect(container.textContent).not.toContain("$0.0000");
    const panels = screen.getAllByRole("region", { name: /^research / });
    expect(panels).toHaveLength(2);
    for (const panel of panels) expect(panel.textContent).toContain("cost · awaiting");
  });

  it("shows a real per-research cost and awaits only the research the backend has not costed", () => {
    sessionView.current = view({
      cost: {
        per_research: { "inv-aaaaaaaaaaaa": 0.1234 },
        session_total_usd: 0.1234,
        aggregate_spent_usd: 0.1234,
        aggregate_cap_usd: 10,
      },
    });
    renderMonitor();
    const first = screen.getByRole("region", { name: "research inv-aaaaaaaaaaaa" });
    const second = screen.getByRole("region", { name: "research inv-bbbbbbbbbbbb" });
    expect(first.textContent).toContain("$0.1234");
    expect(second.textContent).toContain("cost · awaiting");
    expect(second.textContent).not.toContain("$0.0000");
  });
});

describe("DRW monitor — a missing session is terminal (A-14)", () => {
  it("renders the unavailable page with a way back, and no transport line", () => {
    sessionView.current = view({
      researches: [],
      live: false,
      missing: true,
      error: "Couldn't load this research session.",
    });
    const { container } = renderMonitor();
    expect(screen.getByText("That research session isn't available.")).toBeTruthy();
    const back = screen.getByRole("link", { name: /deep research/i });
    expect(back.getAttribute("href")).toBe("/deep-research");
    expect(container.textContent).not.toMatch(/reconnecting|HTTP|\b404\b|GET \//);
  });

  it("renders a transient failure as the humanised title while it reconnects", () => {
    sessionView.current = view({ error: "Couldn't reach this research session." });
    const { container } = renderMonitor();
    expect(container.textContent).toContain("reconnecting… (Couldn't reach this research session.)");
    expect(container.textContent).not.toMatch(/HTTP|\b503\b/);
  });
});
