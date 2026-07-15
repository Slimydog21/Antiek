import { StrictMode, type ReactNode } from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";

import { createPlan, type CreatePlanResponse, type PlanTree } from "../../api/research";
import DeepResearchWorkspace from ".";

vi.mock("../../lib/analytics", () => ({ track: vi.fn() }));
vi.mock("../../workspace/PanelHost", () => ({
  PanelHost: ({ children }: { children: ReactNode }) => children,
}));

const TREE: PlanTree = {
  root: {
    local_id: "root",
    question: "Which evidence would reverse the thesis?",
    rationale: "Decision boundary",
    focus_boundary: "Evidence",
    budget_usd: null,
    max_depth: null,
    graph_node_id: "q-root",
    children: [],
  },
  seed_kind: "problem",
  seed_provenance: {},
  approval: { state: "draft", approved_at: null, approved_by: null, plan_version: 1 },
  root_investigation_id: "__operator__",
};

const RESPONSE: CreatePlanResponse = {
  root_node_id: "q-root",
  tree: TREE,
  capped_nodes: [],
  over_broad_leaves: [],
};

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

afterEach(cleanup);

function mount(createResearchPlan: typeof createPlan) {
  return render(
    <MemoryRouter>
      <DeepResearchWorkspace withWorkspacePanels={false} createResearchPlan={createResearchPlan} />
    </MemoryRouter>,
  );
}

describe("Deep Research Mission Control", () => {
  it("renders the production raster as decorative architecture with live HTML truth", () => {
    mount(vi.fn(async () => RESPONSE));
    const environment = screen.getByTestId("deep-research-mission-control-environment");
    expect(environment.getAttribute("src")).toContain("deep_research_mission_control_v1");
    expect(environment.getAttribute("alt")).toBe("");
    expect(environment.getAttribute("aria-hidden")).toBe("true");
    const frame = environment.closest(".deep-research-mission-control");
    expect(frame?.tagName).toBe("DIV");
    expect(frame?.className).not.toContain("--fixture");
    expect(screen.getByRole("heading", { name: "Deep research mission control" })).toBeTruthy();
    expect(screen.getByLabelText("Deep research controls")).toBeTruthy();
  });

  it("sends only one create request for synchronous duplicate submissions", async () => {
    let resolve!: (value: CreatePlanResponse) => void;
    const createResearchPlan = vi.fn(() => new Promise<CreatePlanResponse>((done) => { resolve = done; }));
    mount(createResearchPlan);
    fireEvent.change(screen.getByLabelText("research problem"), { target: { value: TREE.root.question } });
    const form = screen.getByRole("button", { name: "Cascade" }).closest("form")!;
    fireEvent.submit(form);
    fireEvent.submit(form);
    expect(createResearchPlan).toHaveBeenCalledTimes(1);
    expect(await screen.findByText("Charting the first research paths…")).toBeTruthy();
    resolve(RESPONSE);
    expect(await screen.findByRole("heading", { name: "Cascade plan" })).toBeTruthy();
  });

  it("never exposes a private create failure", async () => {
    mount(vi.fn(async () => { throw new Error("provider credential trace"); }));
    fireEvent.change(screen.getByLabelText("research problem"), { target: { value: TREE.root.question } });
    fireEvent.click(screen.getByRole("button", { name: "Cascade" }));
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toMatch(/could not complete/);
    expect(alert.textContent).toMatch(/Nothing new was launched or approved/);
    expect(alert.textContent).not.toMatch(/provider credential trace/);
  });

  it("remains usable under React StrictMode effect replay", async () => {
    const createResearchPlan = vi.fn(async () => RESPONSE);
    render(
      <StrictMode><MemoryRouter><DeepResearchWorkspace withWorkspacePanels={false} createResearchPlan={createResearchPlan} /></MemoryRouter></StrictMode>,
    );
    fireEvent.change(screen.getByLabelText("research problem"), { target: { value: TREE.root.question } });
    fireEvent.click(screen.getByRole("button", { name: "Cascade" }));
    expect(await screen.findByRole("heading", { name: "Cascade plan" })).toBeTruthy();
    expect(createResearchPlan).toHaveBeenCalledTimes(1);
  });
});
