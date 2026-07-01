import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import type { Event } from "../../generated/types";
import PhaseRow from "./PhaseRow";

afterEach(() => cleanup());

const dispatchEvent = (payload: Record<string, unknown>): Event =>
  ({
    event_id: "e1",
    investigation_id: "inv-1",
    action_type: "dispatch.call",
    payload,
    param_version: "v1",
    emitted_at: "2026-07-01T12:00:00Z",
  }) as unknown as Event;

describe("PhaseRow", () => {
  it("does not render malformed dispatch metrics as NaN or Infinity", () => {
    render(
      <PhaseRow
        event={dispatchEvent({
          provider: "openai",
          model: "gpt-5.5",
          target_role: "synthesizer",
          input_tokens: Number.POSITIVE_INFINITY,
          output_tokens: 12.5,
          cost_usd: Number.NaN,
          latency_ms: Number.POSITIVE_INFINITY,
        })}
      />,
    );

    expect(screen.getByText("in=? out=?")).toBeTruthy();
    expect(screen.getByText("$0.000000")).toBeTruthy();
    expect(screen.getByText("0.0s")).toBeTruthy();
    expect(document.body.textContent).not.toMatch(/NaN|Infinity/);
  });

  it("formats valid dispatch metrics", () => {
    render(
      <PhaseRow
        event={dispatchEvent({
          provider: "anthropic",
          model: "claude",
          target_role: "decomposer",
          input_tokens: 1200,
          output_tokens: 84,
          cost_usd: 0.0123456,
          latency_ms: 1650,
        })}
      />,
    );

    expect(screen.getByText("in=1200 out=84")).toBeTruthy();
    expect(screen.getByText("$0.012346")).toBeTruthy();
    expect(screen.getByText("1.6s")).toBeTruthy();
  });

  it("accepts numeric-string dispatch metrics", () => {
    render(
      <PhaseRow
        event={dispatchEvent({
          provider: "anthropic",
          model: "claude",
          target_role: "decomposer",
          input_tokens: "1200",
          output_tokens: "84",
          cost_usd: "0.0123456",
          latency_ms: "1650",
        })}
      />,
    );

    expect(screen.getByText("in=1200 out=84")).toBeTruthy();
    expect(screen.getByText("$0.012346")).toBeTruthy();
    expect(screen.getByText("1.6s")).toBeTruthy();
  });
});
