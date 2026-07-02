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

import {
  approvePlan,
  createPlan,
  editPlan,
  getBudgetDefaults,
  getPlan,
  getSession,
  getSessionCost,
  getSuggestions,
  launchPlan,
  sessionStreamUrl,
  steerResearch,
} from "./research";

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
      problem: " Break down the energy transition ",
      sub_questions: [" Who controls critical minerals? ", " ", "Who refines them?"],
    });

    expect(postedJsonBody()).toEqual({
      problem: "Break down the energy transition",
      sub_questions: ["Who controls critical minerals?", "Who refines them?"],
    });
  });

  it("rejects malformed createPlan requests before sending", async () => {
    expect(() => createPlan({ problem: " " })).toThrow(/problem/);
    expect(() =>
      createPlan({
        problem: "Break down energy",
        max_depth: Number.POSITIVE_INFINITY,
      }),
    ).toThrow(/max_depth/);

    expect(apiFetchMock).not.toHaveBeenCalled();
  });

  it("sanitizes returned plan trees before the cascade UI renders them", async () => {
    apiFetchMock.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          root_node_id: " q-root ",
          tree: {
            root: {
              local_id: " root ",
              question: "  Root question  ",
              rationale: " ",
              focus_boundary: "  energy only  ",
              budget_usd: "1.25",
              max_depth: "2",
              graph_node_id: " q-root ",
              children: [
                {
                  local_id: " leaf-1 ",
                  question: "  Who controls critical minerals?  ",
                  rationale: "  supply-chain bottleneck  ",
                  focus_boundary: null,
                  budget_usd: -1,
                  max_depth: "9",
                  graph_node_id: "",
                  children: [],
                },
                { local_id: "leaf-bad", question: " ", children: [] },
              ],
            },
            seed_kind: "",
            seed_provenance: [],
            approval: { state: "approved", plan_version: "3", approved_by: " operator " },
            root_investigation_id: " inv-root ",
          },
          capped_nodes: [" leaf-2 ", "", 8],
          over_broad_leaves: [" broad-1 "],
        }),
        { status: 200 },
      ),
    );

    await expect(createPlan({ problem: "Break down energy" })).resolves.toEqual({
      root_node_id: "q-root",
      tree: {
        root: {
          local_id: "root",
          question: "Root question",
          rationale: "",
          focus_boundary: "energy only",
          budget_usd: 1.25,
          max_depth: 2,
          graph_node_id: "q-root",
          children: [
            {
              local_id: "leaf-1",
              question: "Who controls critical minerals?",
              rationale: "supply-chain bottleneck",
              focus_boundary: "",
              budget_usd: null,
              max_depth: null,
              graph_node_id: null,
              children: [],
            },
          ],
        },
        seed_kind: "problem",
        seed_provenance: {},
        approval: {
          state: "approved",
          approved_at: null,
          approved_by: "operator",
          plan_version: 3,
        },
        root_investigation_id: "inv-root",
      },
      capped_nodes: ["leaf-2"],
      over_broad_leaves: ["broad-1"],
    });
  });

  it("rejects malformed plan and launch handles instead of opening dead monitors", async () => {
    apiFetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify({ ...createPlanResponse(), root_node_id: " " }), { status: 200 }),
    );

    await expect(createPlan({ problem: "x" })).rejects.toThrow(/root_node_id/);

    apiFetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify({ session_id: " ", researches: [] }), { status: 200 }),
    );

    await expect(launchPlan("root")).rejects.toThrow(/session_id/);
  });

  it("sanitizes launch, session, cost, and steer responses", async () => {
    apiFetchMock.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          session_id: " sess-1 ",
          researches: [
            {
              investigation_id: " inv-1 ",
              sub_question: "  First question  ",
              question_node_id: " q-1 ",
            },
            { investigation_id: "", sub_question: "missing id" },
          ],
          aggregate_cap_usd: "12.5",
        }),
        { status: 200 },
      ),
    );

    await expect(launchPlan("root")).resolves.toEqual({
      session_id: "sess-1",
      researches: [
        {
          investigation_id: "inv-1",
          sub_question: "First question",
          question_node_id: "q-1",
        },
      ],
      aggregate_cap_usd: 12.5,
    });

    apiFetchMock.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          session_id: " sess-1 ",
          live: "yes",
          researches: [
            {
              investigation_id: " inv-1 ",
              sub_question: "",
              state: "mystery",
              question_node_id: " ",
            },
          ],
          cost: {
            per_research: { " inv-1 ": "0.25", " ": 9, bad: -1 },
            session_total_usd: "0.25",
            aggregate_spent_usd: "0.5",
            aggregate_cap_usd: "2",
          },
          all_terminal: "no",
        }),
        { status: 200 },
      ),
    );

    await expect(getSession("sess-1")).resolves.toEqual({
      session_id: "sess-1",
      live: false,
      researches: [
        {
          investigation_id: "inv-1",
          sub_question: "Untitled research",
          state: "failed",
          question_node_id: null,
        },
      ],
      cost: {
        per_research: { "inv-1": 0.25 },
        session_total_usd: 0.25,
        aggregate_spent_usd: 0.5,
        aggregate_cap_usd: 2,
      },
      all_terminal: undefined,
    });

    apiFetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify({ per_research: { " inv-1 ": "0.1" } }), { status: 200 }),
    );
    await expect(getSessionCost("sess-1")).resolves.toMatchObject({
      per_research: { "inv-1": 0.1 },
      session_total_usd: 0,
    });

    apiFetchMock.mockResolvedValueOnce(
      new Response(
        JSON.stringify({ session_id: " sess-1 ", investigation_id: " inv-1 ", state: "paused" }),
        { status: 200 },
      ),
    );
    await expect(steerResearch("sess-1", "inv-1", "pause")).resolves.toEqual({
      session_id: "sess-1",
      investigation_id: "inv-1",
      state: "paused",
    });
  });

  it("trims plan lifecycle handles and edit bodies before sending", async () => {
    apiFetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify({ ...createPlanResponse(), launchable: true }), {
        status: 200,
      }),
    );
    await getPlan(" root with space ");
    expect(apiFetchMock.mock.calls[0][0]).toBe("/api/research/plans/root%20with%20space");

    apiFetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify({ ...createPlanResponse(), launchable: true }), {
        status: 200,
      }),
    );
    await editPlan(" root with space ", {
      op: "split",
      target_local_id: " root ",
      question: "  sharper question  ",
      budget_usd: 1.25,
      max_depth: 2,
      into: [" leaf 1 ", " ", "leaf 2"],
    });
    expect(apiFetchMock.mock.calls[1][0]).toBe(
      "/api/research/plans/root%20with%20space/edit",
    );
    expect(JSON.parse((apiFetchMock.mock.calls[1][1] as RequestInit).body as string)).toEqual({
      op: "split",
      target_local_id: "root",
      question: "sharper question",
      budget_usd: 1.25,
      max_depth: 2,
      into: ["leaf 1", "leaf 2"],
    });

    apiFetchMock.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          root_node_id: "root",
          approval: { state: "approved", plan_version: 1, approved_by: "operator" },
          launchable: true,
        }),
        { status: 200 },
      ),
    );
    await approvePlan(" root with space ", " operator ");
    expect(apiFetchMock.mock.calls[2][0]).toBe(
      "/api/research/plans/root%20with%20space/approve",
    );
    expect(JSON.parse((apiFetchMock.mock.calls[2][1] as RequestInit).body as string)).toEqual({
      approver: "operator",
    });
  });

  it("rejects malformed plan lifecycle request handles before sending", async () => {
    expect(() => getPlan(" ")).toThrow(/rootId/);
    expect(() =>
      editPlan("root", { op: "reword", target_local_id: " ", question: "new question" }),
    ).toThrow(/target_local_id/);
    expect(() =>
      editPlan("root", { op: "reword", target_local_id: "root", question: " " }),
    ).toThrow(/question/);
    expect(() =>
      editPlan("root", { op: "set_budget", target_local_id: "root", budget_usd: -1 }),
    ).toThrow(/budget_usd/);
    expect(() => approvePlan(" ", "operator")).toThrow(/rootId/);
    expect(() => approvePlan("root", " ")).toThrow(/approver/);

    expect(apiFetchMock).not.toHaveBeenCalled();
  });

  it("trims session lifecycle handles and launch budgets before sending", async () => {
    apiFetchMock.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          session_id: "sess-1",
          researches: [],
          aggregate_cap_usd: 1.5,
        }),
        { status: 200 },
      ),
    );
    await launchPlan(" root with space ", {
      per_research_budget_usd: 0.75,
      aggregate_budget_usd: null,
    });
    expect(apiFetchMock.mock.calls[0][0]).toBe(
      "/api/research/plans/root%20with%20space/launch",
    );
    expect(postedJsonBody()).toEqual({
      per_research_budget_usd: 0.75,
      aggregate_budget_usd: null,
    });

    apiFetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify({ session_id: "sess-1", live: true, researches: [] }), {
        status: 200,
      }),
    );
    await getSession(" sess with space ");
    expect(apiFetchMock.mock.calls[1][0]).toBe(
      "/api/research/sessions/sess%20with%20space",
    );

    apiFetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify({ per_research: {} }), { status: 200 }),
    );
    await getSessionCost(" sess with space ");
    expect(apiFetchMock.mock.calls[2][0]).toBe(
      "/api/research/sessions/sess%20with%20space/cost",
    );

    apiFetchMock.mockResolvedValueOnce(
      new Response(
        JSON.stringify({ session_id: "sess-1", investigation_id: "inv-1", state: "running" }),
        { status: 200 },
      ),
    );
    await steerResearch(" sess with space ", " inv with space ", "redirect", { q: "next" });
    expect(apiFetchMock.mock.calls[3][0]).toBe(
      "/api/research/sessions/sess%20with%20space/researches/inv%20with%20space/steer",
    );
    expect(JSON.parse((apiFetchMock.mock.calls[3][1] as RequestInit).body as string)).toEqual({
      kind: "redirect",
      payload: { q: "next" },
    });

    expect(sessionStreamUrl(" sess with space ")).toBe(
      "/api/research/sessions/sess%20with%20space/stream",
    );
  });

  it("rejects malformed session lifecycle requests before sending", async () => {
    expect(() => launchPlan(" ")).toThrow(/rootId/);
    expect(() => launchPlan("root", { per_research_budget_usd: -1 })).toThrow(
      /per_research_budget_usd/,
    );
    expect(() => launchPlan("root", { aggregate_budget_usd: Number.NaN })).toThrow(
      /aggregate_budget_usd/,
    );
    expect(() => getSession(" ")).toThrow(/sessionId/);
    expect(() => getSessionCost(" ")).toThrow(/sessionId/);
    expect(() => steerResearch(" ", "inv", "pause")).toThrow(/sessionId/);
    expect(() => steerResearch("sess", " ", "pause")).toThrow(/investigationId/);
    expect(() => sessionStreamUrl(" ")).toThrow(/sessionId/);

    expect(apiFetchMock).not.toHaveBeenCalled();
  });

  it("sanitizes research budget defaults, suggestions, and approvals", async () => {
    apiFetchMock.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          per_research_cost_usd: "0.75",
          per_research_max_steps: "25",
          host_local_max_concurrency: 0,
        }),
        { status: 200 },
      ),
    );
    await expect(getBudgetDefaults()).resolves.toEqual({
      per_research_cost_usd: 0.75,
      per_research_max_steps: 25,
      host_local_max_concurrency: 1,
    });

    apiFetchMock.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          count: "not a number",
          suggestions: [
            {
              key: " key-1 ",
              question: "  Chase this  ",
              suggested_retrieval: "  papers  ",
              seen_in_research_count: "2",
              source_investigation_id: " inv-source ",
            },
            { key: " ", question: "missing key" },
          ],
        }),
        { status: 200 },
      ),
    );
    await expect(getSuggestions()).resolves.toEqual({
      count: 1,
      suggestions: [
        {
          key: "key-1",
          question: "Chase this",
          suggested_retrieval: "papers",
          seen_in_research_count: 2,
          source_investigation_id: "inv-source",
        },
      ],
    });
    expect(apiFetchMock.mock.calls[1][0]).toBe("/api/research/suggestions?limit=8");

    apiFetchMock.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          root_node_id: " root ",
          approval: { state: "surprise", plan_version: 0 },
          launchable: "yes",
        }),
        { status: 200 },
      ),
    );
    await expect(approvePlan("root")).resolves.toEqual({
      root_node_id: "root",
      approval: {
        state: "draft",
        approved_at: null,
        approved_by: null,
        plan_version: 1,
      },
      launchable: false,
    });
  });

  it("bounds suggestion requests with positive safe integer limits", async () => {
    apiFetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify({ count: 0, suggestions: [] }), { status: 200 }),
    );

    await expect(getSuggestions(3)).resolves.toEqual({ count: 0, suggestions: [] });
    expect(apiFetchMock.mock.calls[0][0]).toBe("/api/research/suggestions?limit=3");

    expect(() => getSuggestions(0)).toThrow(/limit/);
    expect(() => getSuggestions(-1)).toThrow(/limit/);
    expect(() => getSuggestions(1.5)).toThrow(/limit/);
    expect(() => getSuggestions(Number.POSITIVE_INFINITY)).toThrow(/limit/);
    expect(apiFetchMock).toHaveBeenCalledTimes(1);
  });
});
