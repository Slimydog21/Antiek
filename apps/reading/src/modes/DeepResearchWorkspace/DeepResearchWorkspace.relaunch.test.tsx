import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import type { PlanTree } from "../../api/research";
import { WERNER_EXPERIENCE_EVENT } from "../../werner";

const api = vi.hoisted(() => ({
  approvePlan: vi.fn(),
  createPlan: vi.fn(),
  getPlan: vi.fn(),
  getSession: vi.fn(),
  launchPlan: vi.fn(),
}));

const projectionApi = vi.hoisted(() => ({
  fetchComposerProjection: vi.fn(),
}));

vi.mock("../../api/research", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../api/research")>()),
  ...api,
}));

vi.mock("../../api/composerProjection", () => projectionApi);

vi.mock("../../workspace/PanelHost", () => ({
  PanelHost: ({ children }: { children: ReactNode }) => children,
}));

import DeepResearchWorkspace from ".";

beforeAll(() => {
  Object.defineProperty(window, "matchMedia", {
    configurable: true,
    value: (query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    }),
  });
});

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
    projectionApi.fetchComposerProjection.mockResolvedValue({
      task: "deep_research",
      recommended_tier: "deep",
      ranked_candidates: [
        {
          rank: 1,
          tier: "deep",
          provider: "zai",
          model: "glm-5.2",
          quality_score: 0.9,
          quality_basis: "measured",
          eligible: true,
          pricing_status: "known",
          estimated_usd_low: 0.1,
          estimated_usd_high: 0.3,
        },
      ],
      budget: { daily_cap_usd: null, spent_usd: null },
      remaining_usd: null,
      chosen_provider: null,
      chosen_model: null,
      chosen_projection: null,
      would_exceed_budget: null,
      pricing_status: "known",
      authority: "advisory_explanatory",
      notes: [],
      fallback_plan: null,
    });
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
    fireEvent.click(await screen.findByRole("button", { name: /choose model driver/i }));
    fireEvent.click(await screen.findByRole("option", { name: /glm-5\.2/i }));
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
    const launchPayload = api.launchPlan.mock.calls[0]?.[1];
    expect(launchPayload).toEqual({
      owner_model_choices: {
        decomposer: {
          authority: "user_model",
          provider_id: "zai",
          model_id: "glm-5.2",
        },
        evidence_retriever: {
          authority: "user_model",
          provider_id: "zai",
          model_id: "glm-5.2",
        },
        parameter_extractor: {
          authority: "user_model",
          provider_id: "zai",
          model_id: "glm-5.2",
        },
        connector: {
          authority: "user_model",
          provider_id: "zai",
          model_id: "glm-5.2",
        },
        synthesizer: {
          authority: "user_model",
          provider_id: "zai",
          model_id: "glm-5.2",
        },
        knowledge_extractor: {
          authority: "user_model",
          provider_id: "zai",
          model_id: "glm-5.2",
        },
      },
    });
    window.removeEventListener(WERNER_EXPERIENCE_EVENT, listener);
  });
});
