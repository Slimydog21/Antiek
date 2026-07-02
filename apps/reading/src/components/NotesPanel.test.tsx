import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import type { Event } from "../generated/types";
import NotesPanel from "./NotesPanel";

afterEach(() => cleanup());

const dispatchEvent = (payload: Record<string, unknown>): Event =>
  ({
    event_id: "event-dispatch-1",
    investigation_id: "inv-1",
    document_id: "doc-1",
    action_type: "dispatch.call",
    emitted_at: "2026-07-01T12:00:00Z",
    role: "system",
    payload: {
      action_type: "dispatch.call",
      provider: "openai",
      model: "gpt-5.5",
      tier: "synthesis",
      target_role: "synthesizer",
      prompt_hash: "hash-1",
      ...payload,
    },
  }) as unknown as Event;

const contextPackEvent = (payload: Record<string, unknown>): Event =>
  ({
    event_id: "event-context-pack-1",
    investigation_id: "inv-1",
    document_id: "doc-1",
    action_type: "context_pack.assembled",
    emitted_at: "2026-07-01T12:00:00Z",
    role: "system",
    payload: {
      action_type: "context_pack.assembled",
      target_role: "synthesizer",
      actual_tokens: 1200,
      target_tokens: 1600,
      layers: [{ kind: "claim", tokens: 1200 }],
      budget_overrun: false,
      ...payload,
    },
  }) as unknown as Event;

describe("NotesPanel", () => {
  it("does not render malformed dispatch metrics as NaN or Infinity", () => {
    render(
      <NotesPanel
        events={[
          dispatchEvent({
            input_tokens: Number.POSITIVE_INFINITY,
            output_tokens: 12.5,
            cost_usd: Number.NaN,
            latency_ms: Number.POSITIVE_INFINITY,
          }),
        ]}
        status="open"
        reconnects={0}
        investigationId="inv-1"
        documentId="doc-1"
      />,
    );

    expect(
      screen.getByText(
        (_, element) =>
          element?.textContent === "openai/gpt-5.5  in=? out=? $0.00000 0ms",
      ),
    ).toBeTruthy();
    expect(document.body.textContent).not.toMatch(/NaN|Infinity/);
  });

  it("formats valid dispatch metrics", () => {
    render(
      <NotesPanel
        events={[
          dispatchEvent({
            provider: "anthropic",
            model: "claude",
            input_tokens: 1200,
            output_tokens: 84,
            cost_usd: 0.0123456,
            latency_ms: 1650.4,
          }),
        ]}
        status="open"
        reconnects={0}
        investigationId="inv-1"
        documentId="doc-1"
      />,
    );

    expect(
      screen.getByText(
        (_, element) =>
          element?.textContent ===
          "anthropic/claude  in=1200 out=84 $0.01235 1650ms",
      ),
    ).toBeTruthy();
  });

  it("accepts numeric-string dispatch metrics", () => {
    render(
      <NotesPanel
        events={[
          dispatchEvent({
            provider: "anthropic",
            model: "claude",
            input_tokens: "1200",
            output_tokens: "84",
            cost_usd: "0.0123456",
            latency_ms: "1650.4",
          }),
        ]}
        status="open"
        reconnects={0}
        investigationId="inv-1"
        documentId="doc-1"
      />,
    );

    expect(
      screen.getByText(
        (_, element) =>
          element?.textContent ===
          "anthropic/claude  in=1200 out=84 $0.01235 1650ms",
      ),
    ).toBeTruthy();
  });

  it("does not throw or leak malformed context pack metrics", () => {
    render(
      <NotesPanel
        events={[
          contextPackEvent({
            target_role: " ",
            actual_tokens: Number.NaN,
            target_tokens: "1600",
            layers: "not-an-array",
            budget_overrun: true,
          }),
        ]}
        status="open"
        reconnects={0}
        investigationId="inv-1"
        documentId="doc-1"
      />,
    );

    expect(
      screen.getByText(
        (_, element) =>
          element?.textContent ===
          "pack[context] 0/1600tok · 0 layers · overflow",
      ),
    ).toBeTruthy();
    expect(document.body.textContent).not.toMatch(/NaN|Infinity|undefined/);
  });
});
