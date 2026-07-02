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

const event = (actionType: string, payload: Record<string, unknown>): Event =>
  ({
    event_id: "e1",
    investigation_id: "inv-1",
    action_type: actionType,
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

  it("sanitizes malformed decomposition payloads", () => {
    render(
      <PhaseRow
        event={event("decompose.delivered", {
          decomposition: [
            {
              sub_question: "  Which source matters? ",
              category: " market ",
              evidence_type_required: " direct ",
            },
            {
              sub_question: "",
              category: "ignored",
            },
            "not-a-record",
          ],
        })}
      />,
    );

    expect(screen.getByText("1 sub-question")).toBeTruthy();
    expect(screen.getByText("Which source matters?")).toBeTruthy();
    expect(document.body.textContent).not.toMatch(/undefined|NaN|Infinity/);
  });

  it("sanitizes malformed evidence payload arrays", () => {
    render(
      <PhaseRow
        event={event("evidence.retrieve.delivered", {
          sub_question: ["not text"],
          supporting_claims: [
            {
              claim: "  Supported claim. ",
              chunk_ids: [" chunk-1 ", "", 9],
            },
            {
              claim: "",
              chunk_ids: ["ignored"],
            },
          ],
          evidentiary_gaps: [
            {
              description: "  Missing primary source. ",
            },
            {
              gap: "",
            },
          ],
        })}
      />,
    );

    expect(screen.getByText("1 claim · 2 gaps")).toBeTruthy();
    expect(screen.getByText("Supported claim.")).toBeTruthy();
    expect(screen.getByText("[1 source]")).toBeTruthy();
    expect(screen.getByText("Missing primary source.")).toBeTruthy();
    expect(screen.getByText("(empty)")).toBeTruthy();
    expect(document.body.textContent).not.toMatch(/undefined|NaN|Infinity/);
  });

  it("sanitizes malformed connector and skill patch payloads", () => {
    const { rerender } = render(
      <PhaseRow
        event={event("connector.delivered", {
          paths: "not-an-array",
          mapped_nodes: [{ id: "n1" }],
        })}
      />,
    );

    expect(screen.getByText("0 paths · 1 node")).toBeTruthy();

    rerender(
      <PhaseRow
        event={event("skill.auto_patch_applied", {
          domains_patched: [" history ", "", 3],
        })}
      />,
    );

    expect(screen.getByText("✦ Phase 8: patched 1 domain skill (history)")).toBeTruthy();
    expect(document.body.textContent).not.toMatch(/undefined|NaN|Infinity/);
  });
});
