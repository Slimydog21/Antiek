import { afterEach, describe, expect, it, vi } from "vitest";

const { apiFetchMock } = vi.hoisted(() => ({
  apiFetchMock: vi.fn(),
}));

vi.mock("../lib/api", async (orig) => {
  const actual = await orig<typeof import("../lib/api")>();
  return { ...actual, API_BASE: "", apiFetch: apiFetchMock };
});

import { launchPlan } from "./research";

afterEach(() => {
  apiFetchMock.mockReset();
});

describe("research API client", () => {
  it("serializes source policy metadata on cascade launch", async () => {
    apiFetchMock.mockResolvedValue({
      ok: true,
      json: async () => ({
        session_id: "session-root",
        researches: [],
        aggregate_cap_usd: 10,
        source_policy: ["operator_corpus", "web"],
        source_policy_execution: "metadata_only",
      }),
    });

    const result = await launchPlan("root-1", {
      source_policy: ["operator_corpus", "web"],
    });

    expect(result.source_policy).toEqual(["operator_corpus", "web"]);
    expect(apiFetchMock).toHaveBeenCalledWith(
      "/research/plans/root-1/launch",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ source_policy: ["operator_corpus", "web"] }),
      }),
    );
  });
});
