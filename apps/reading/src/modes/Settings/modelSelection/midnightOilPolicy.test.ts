import { describe, expect, it } from "vitest";

import {
  buildMidnightOilPreflight,
  recommendCeilingCents,
  requestMidnightOilApproval,
} from "./midnightOilPolicy";

describe("midnightOilPolicy", () => {
  it("recommends integer cents from goals + duration", () => {
    expect(recommendCeilingCents(2, 60)).toBe(50 + 50 + 120);
  });

  it("rejects empty goals and out-of-range duration", () => {
    expect(
      buildMidnightOilPreflight({ goals: [], durationMinutes: 60 }),
    ).toEqual({ ok: false, reason: "need_goals" });
    expect(
      buildMidnightOilPreflight({
        goals: [{ id: "1", text: "What is X?" }],
        durationMinutes: 5,
      }),
    ).toEqual({ ok: false, reason: "duration_out_of_range" });
  });

  it("builds advisory preflight with spend_authorized false", () => {
    const plan = buildMidnightOilPreflight({
      goals: [
        { id: "1", text: "Map agent frameworks" },
        { id: "2", text: "Compare eval harnesses" },
      ],
      durationMinutes: 90,
    });
    expect(plan.ok).toBe(true);
    if (!plan.ok) return;
    expect(plan.spend_authorized).toBe(false);
    expect(plan.authority).toBe("preflight_advisory");
    expect(Number.isInteger(plan.ceilingCents)).toBe(true);
  });

  it("approval request requires operator ack and never asserts server authority", () => {
    const plan = buildMidnightOilPreflight({
      goals: [{ id: "1", text: "Deep dive on routers" }],
      durationMinutes: 30,
    });
    expect(requestMidnightOilApproval(plan, false)).toEqual({
      ok: false,
      reason: "operator_ack_required",
    });
    const req = requestMidnightOilApproval(plan, true, () =>
      new Date("2026-07-15T13:00:00.000Z"),
    );
    expect(req.ok).toBe(true);
    if (!req.ok) return;
    expect(req.authority).toBe("operator_request_only");
    expect(req.plan.spend_authorized).toBe(false);
  });
});
