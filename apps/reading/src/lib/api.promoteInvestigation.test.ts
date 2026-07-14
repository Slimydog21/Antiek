import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  ApiError,
  classifyInvestigationPromotionFailure,
  promoteInvestigationToWrite,
} from "./api";

const fetchMock = vi.fn();

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("promoteInvestigationToWrite", () => {
  it("posts the closed research-memo request and returns the seeded deliverable", async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      status: 201,
      json: async () => ({
        deliverable_id: "draft-1",
        section_id: "section-1",
        block_count: 3,
        dangling_count: 0,
        source_node_count: 3,
        synthesis_id: "synthesis-1",
        synthesis_status: "passed",
        synthesis_recommendation: "proceed",
      }),
    });

    const result = await promoteInvestigationToWrite("research/one");

    expect(result.deliverable_id).toBe("draft-1");
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toContain("/write/deliverables/from-investigation");
    expect(init?.method).toBe("POST");
    expect(init?.credentials).toBe("include");
    expect(JSON.parse(init?.body as string)).toEqual({
      investigation_id: "research/one",
      deliverable_kind: "research_memo",
    });
  });

  it("preserves the typed refusal body on ApiError", async () => {
    const body = JSON.stringify({
      detail: {
        error: "not_promotable",
        reason: "every source is unavailable",
        gate_failed: "all_dangling",
      },
    });
    fetchMock.mockResolvedValue({
      ok: false,
      status: 409,
      text: async () => body,
    });

    await expect(promoteInvestigationToWrite("inv-1")).rejects.toMatchObject({
      status: 409,
      body,
    });
  });
});

describe("classifyInvestigationPromotionFailure", () => {
  it("accepts only the closed 404 and 409 contracts", () => {
    expect(
      classifyInvestigationPromotionFailure(
        new ApiError(
          "missing",
          404,
          JSON.stringify({
            detail: { error: "no_synthesis", reason: "no completed synthesis" },
          }),
        ),
      ),
    ).toEqual({ kind: "no_synthesis", reason: "no completed synthesis" });
    expect(
      classifyInvestigationPromotionFailure(
        new ApiError(
          "refused",
          409,
          JSON.stringify({
            detail: {
              error: "not_promotable",
              reason: "synthesis did not converge",
              gate_failed: "status",
            },
          }),
        ),
      ),
    ).toEqual({
      kind: "not_promotable",
      reason: "synthesis did not converge",
      gate_failed: "status",
    });
    expect(
      classifyInvestigationPromotionFailure(
        new ApiError(
          "unknown",
          409,
          JSON.stringify({
            detail: { error: "not_promotable", reason: "x", gate_failed: "new_gate" },
          }),
        ),
      ),
    ).toEqual({ kind: "unknown", reason: null });
  });
});
