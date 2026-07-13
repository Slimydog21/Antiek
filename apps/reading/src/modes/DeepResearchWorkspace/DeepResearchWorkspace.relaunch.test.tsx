import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { PlanTree } from "../../api/research";
import { WERNER_EXPERIENCE_EVENT } from "../../werner";

const api = vi.hoisted(() => ({
  approvePlan: vi.fn(),
  createPlan: vi.fn(),
  getPlan: vi.fn(),
  getSession: vi.fn(),
  launchPlan: vi.fn(),
}));

vi.mock("../../api/research", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../api/research")>()),
  ...api,
}));

vi.mock("../../workspace/PanelHost", () => ({
  PanelHost: ({ children }: { children: ReactNode }) => children,
}));

import DeepResearchWorkspace from ".";

const APPROVED_TREE: PlanTree = {
  root: {
    local_id: "pn-root",
    question: "Relaunch this",
    rationale: "",
    focus_boundary: "",
    budget_usd: null,
    max_depth: null,
    graph_node_id: "q-root",
    children: [],
  },
  seed_kind: "problem",
  seed_provenance: {},
  approval: {
    state: "approved",
    approved_at: "2026-07-13T00:00:00Z",
    approved_by: "operator",
    plan_version: 1,
  },
  root_investigation_id: "__operator__",
};

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("DeepResearchWorkspace deterministic session relaunch", () => {
  it("remounts polling and reactions when a successful relaunch reuses the session ID", async () => {
    api.createPlan.mockResolvedValue({
      root_node_id: "q-root",
      tree: APPROVED_TREE,
    });
    api.approvePlan.mockResolvedValue({});
    api.getPlan.mockResolvedValue({
      root_node_id: "q-root",
      tree: APPROVED_TREE,
      launchable: true,
    });
    api.launchPlan.mockResolvedValue({
      session_id: "session-q-root",
      researches: [],
      aggregate_cap_usd: 10,
    });
    api.getSession.mockResolvedValue({
      session_id: "session-q-root",
      live: true,
      researches: [
        {
          investigation_id: "inv-1",
          sub_question: "Relaunch this",
          state: "done",
        },
      ],
      all_terminal: true,
      cost: null,
    });
    const experiences: string[] = [];
    const listener = (event: Event) =>
      experiences.push((event as CustomEvent).detail.experience);
    window.addEventListener(WERNER_EXPERIENCE_EVENT, listener);

    render(
      <MemoryRouter>
        <DeepResearchWorkspace />
      </MemoryRouter>,
    );
    fireEvent.change(screen.getByLabelText("research problem"), {
      target: { value: "Relaunch this" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Cascade" }));
    fireEvent.click(await screen.findByRole("button", { name: "Re-approve" }));
    await waitFor(() =>
      expect(
        (screen.getByRole("button", { name: "Launch 1" }) as HTMLButtonElement)
          .disabled,
      ).toBe(false),
    );
    const launch = screen.getByRole("button", { name: "Launch 1" });

    fireEvent.click(launch);
    await waitFor(() => expect(api.getSession).toHaveBeenCalledTimes(1));
    await waitFor(() =>
      expect(experiences).toEqual([
        "deep_research_start",
        "deep_research_complete",
      ]),
    );

    fireEvent.click(screen.getByRole("button", { name: "Launch 1" }));
    await waitFor(() => expect(api.getSession).toHaveBeenCalledTimes(2));
    await waitFor(() =>
      expect(experiences).toEqual([
        "deep_research_start",
        "deep_research_complete",
        "deep_research_start",
        "deep_research_complete",
      ]),
    );
    expect(api.launchPlan).toHaveBeenCalledTimes(2);
    window.removeEventListener(WERNER_EXPERIENCE_EVENT, listener);
  });
});
