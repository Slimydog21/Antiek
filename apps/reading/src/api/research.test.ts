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
  getBudgetDefaults,
  getSession,
  getSessionCost,
  getSuggestions,
  launchPlan,
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
      problem: "Break down the energy transition",
      sub_questions: ["Who controls critical minerals?"],
    });

    expect(postedJsonBody()).toEqual({
      problem: "Break down the energy transition",
      sub_questions: ["Who controls critical minerals?"],
    });
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
                  max_depth: 1.5,
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
});
