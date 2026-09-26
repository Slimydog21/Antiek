/**
 * FFX SPR-04 M4 (F-12): a dispatch row never coerces a usage field it was
 * not given into 0 or a blank.
 */
import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import type { Event } from "../../generated/types";
import PhaseRow from "./PhaseRow";

function dispatch(payload: Record<string, unknown>): Event {
  return {
    event_id: "ev-1",
    investigation_id: "inv-1",
    action_type: "dispatch.call",
    payload: payload as unknown as Event["payload"],
    param_version: "v1",
    emitted_at: "2026-09-27T00:00:00Z",
  } as Event;
}

afterEach(() => cleanup());

describe("PhaseRow dispatch row (F-12)", () => {
  it("renders a dash, not 0 or a blank, for each missing usage field, and says why", () => {
    const { container } = render(
      <PhaseRow event={dispatch({ provider: "openrouter", model: "glm", target_role: "synthesizer" })} />,
    );
    const text = container.textContent ?? "";
    expect(text).not.toContain("$0");
    expect(text).not.toContain("0.0s");
    expect(text).not.toMatch(/in=(\s|out|$)/);
    expect(text).not.toMatch(/out=(\s|·|$)/);
    expect(text).toContain("in=— out=—");
    expect(text).toContain("usage not reported");
  });

  it("renders reported values, including a real zero cost", () => {
    const { container } = render(
      <PhaseRow
        event={dispatch({
          provider: "openrouter",
          model: "glm",
          target_role: "synthesizer",
          input_tokens: 120,
          output_tokens: 45,
          cost_usd: 0,
          latency_ms: 1500,
        })}
      />,
    );
    const text = container.textContent ?? "";
    expect(text).toContain("in=120 out=45");
    expect(text).toContain("$0.000000");
    expect(text).toContain("1.5s");
    expect(text).not.toContain("usage not reported");
  });
});
