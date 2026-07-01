import { beforeEach, describe, expect, it, vi } from "vitest";

const apiFetchMock = vi.hoisted(() => vi.fn());

vi.mock("../lib/api", async () => {
  const actual = await vi.importActual<typeof import("../lib/api")>("../lib/api");
  return {
    ...actual,
    API_BASE: "/api",
    apiFetch: apiFetchMock,
  };
});

import { createPlan } from "./research";

function createPlanResponse() {
  return {
    root_node_id: "q-root",
    tree: {
      root: {
        local_id: "root",
        question: "Root question",
        rationale: "",
        focus_boundary: "",
        budget_usd: null,
        max_depth: null,
        graph_node_id: "q-root",
        children: [],
      },
      seed_kind: "problem",
      seed_provenance: {},
      approval: { state: "draft", approved_at: null, approved_by: null, plan_version: 1 },
      root_investigation_id: "__operator__",
    },
    capped_nodes: [],
    over_broad_leaves: [],
  };
}

function postedJsonBody(): Record<string, unknown> {
  const [, init] = apiFetchMock.mock.calls[0] as [string, RequestInit];
  expect(typeof init.body).toBe("string");
  return JSON.parse(init.body as string) as Record<string, unknown>;
}

beforeEach(() => {
  apiFetchMock.mockReset();
  apiFetchMock.mockResolvedValue(
    new Response(JSON.stringify(createPlanResponse()), { status: 200 }),
  );
});

describe("research api - cascade plan boundary", () => {
  it("omits sub_questions on auto-decompose createPlan calls", async () => {
    await createPlan({ problem: "Break down the energy transition" });

    expect(apiFetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = apiFetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/research/plans");
    expect(init.method).toBe("POST");
    expect(init.headers).toMatchObject({ "Content-Type": "application/json" });
    expect(postedJsonBody()).toEqual({ problem: "Break down the energy transition" });
  });

  it("preserves explicit sub_questions for the manual createPlan branch", async () => {
    await createPlan({
      problem: "Break down the energy transition",
      sub_questions: ["Who controls critical minerals?"],
    });

    expect(postedJsonBody()).toEqual({
      problem: "Break down the energy transition",
      sub_questions: ["Who controls critical minerals?"],
    });
  });
});
