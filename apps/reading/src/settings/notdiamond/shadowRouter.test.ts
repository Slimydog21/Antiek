import { describe, expect, it, vi } from "vitest";

import {
  localHeuristicRecommend,
  selectModelShadow,
  type ModelRef,
} from "./shadowRouter";

const CANDIDATES: ModelRef[] = [
  { id: "gpt-4.1", provider: "openai" },
  { id: "claude-sonnet", provider: "anthropic" },
  { id: "deep-research-pro", provider: "xai" },
];

describe("localHeuristicRecommend", () => {
  it("prefers id containing taskClass", () => {
    expect(localHeuristicRecommend(CANDIDATES, "deep_research")?.id).toBe(
      "deep-research-pro",
    );
  });

  it("falls back to first candidate", () => {
    expect(localHeuristicRecommend(CANDIDATES, "unknown")?.id).toBe("gpt-4.1");
  });

  it("returns null for empty set", () => {
    expect(localHeuristicRecommend([], "x")).toBeNull();
  });
});

describe("selectModelShadow", () => {
  it("is disabled by default and uses local heuristic", async () => {
    const d = await selectModelShadow({
      messages: [{ role: "user", content: "hi" }],
      candidates: CANDIDATES,
      taskClass: "deep_research",
    });
    expect(d.provider).toBe("fallback_local");
    expect(d.recommended?.id).toBe("deep-research-pro");
    expect(d.error).toBeUndefined();
  });

  it("fail-closed on empty candidates", async () => {
    const d = await selectModelShadow({
      messages: [],
      candidates: [],
      taskClass: "x",
    });
    expect(d.recommended).toBeNull();
    expect(d.error).toBe("empty_candidate_set");
  });

  it("uses transport when enabled and maps id into candidates", async () => {
    const transport = vi.fn(async () => ({
      recommendedId: "claude-sonnet",
      reason: "nd_pick",
    }));
    const d = await selectModelShadow(
      {
        messages: [{ role: "user", content: "route me" }],
        candidates: CANDIDATES,
        taskClass: "chat",
      },
      { enabled: true, transport },
    );
    expect(d.provider).toBe("notdiamond");
    expect(d.recommended?.id).toBe("claude-sonnet");
    expect(d.reason).toBe("nd_pick");
    expect(transport).toHaveBeenCalledOnce();
  });

  it("rejects transport ids outside candidate set", async () => {
    const d = await selectModelShadow(
      {
        messages: [],
        candidates: CANDIDATES,
        taskClass: "chat",
      },
      {
        enabled: true,
        transport: async () => ({ recommendedId: "secret-model" }),
      },
    );
    expect(d.recommended).toBeNull();
    expect(d.error).toBe("recommended_id_not_in_candidates");
  });

  it("falls back locally on transport timeout/error", async () => {
    const d = await selectModelShadow(
      {
        messages: [],
        candidates: CANDIDATES,
        taskClass: "deep_research",
        timeoutMs: 20,
      },
      {
        enabled: true,
        transport: async () => {
          await new Promise((r) => setTimeout(r, 100));
          return { recommendedId: "gpt-4.1" };
        },
      },
    );
    expect(d.provider).toBe("fallback_local");
    expect(d.error).toBe("notdiamond_timeout");
    expect(d.recommended?.id).toBe("deep-research-pro");
  });
});
