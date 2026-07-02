import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Event } from "../generated/types";
import NotesPanel from "./NotesPanel";

const { openDocumentMock } = vi.hoisted(() => ({
  openDocumentMock: vi.fn(),
}));

vi.mock("../lib/openDocument", () => ({
  useOpenDocument: () => openDocumentMock,
}));

afterEach(() => cleanup());

beforeEach(() => {
  openDocumentMock.mockReset();
});

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

const feedEvent = (
  actionType: string,
  payload: Record<string, unknown>,
  index: number,
): Event =>
  ({
    event_id: `event-feed-${index}`,
    investigation_id: "inv-1",
    document_id: "doc-1",
    action_type: actionType,
    emitted_at: "2026-07-01T12:00:00Z",
    role: "system",
    payload: {
      action_type: actionType,
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

  it("sanitizes malformed display fields in feed rows", () => {
    render(
      <NotesPanel
        events={[
          feedEvent(
            "distillation.requested",
            {
              user_prompt: 42,
            },
            1,
          ),
          feedEvent(
            "claim.challenge_raised",
            {
              user_question: null,
              claim_text: undefined,
            },
            2,
          ),
          feedEvent(
            "document.region_selected",
            {
              region_id: "region-1",
              page: Number.POSITIVE_INFINITY,
              text_excerpt: ["not text"],
            },
            3,
          ),
          feedEvent(
            "document.loaded",
            {
              media_type: "",
              size_bytes: Number.NaN,
              title: 99,
            },
            4,
          ),
        ]}
        status="open"
        reconnects={0}
        investigationId="inv-1"
        documentId="doc-1"
      />,
    );

    expect(screen.getByText("request unavailable")).toBeTruthy();
    expect(screen.getByText("challenge unavailable")).toBeTruthy();
    expect(
      screen.getByText(
        (_, element) =>
          element?.textContent === "↳ challenging: claim unavailable",
      ),
    ).toBeTruthy();
    expect(screen.getByText('selected p?: ""')).toBeTruthy();
    expect(screen.getByText("loaded document (? KB)")).toBeTruthy();
    expect(document.body.textContent).not.toMatch(/NaN|Infinity|undefined/);
  });

  it("sanitizes malformed delivered payloads before rendering claim rows", () => {
    render(
      <NotesPanel
        events={[
          feedEvent(
            "distillation.delivered",
            {
              request_event_id: 17,
              claims: "not-an-array",
              rendered_text: ["not text"],
              token_count: Number.NaN,
            },
            1,
          ),
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
          element?.textContent === "synthesizer · 0 claims · ? tok",
      ),
    ).toBeTruthy();
    expect(document.body.textContent).not.toMatch(/NaN|Infinity|undefined/);
  });

  it("keeps valid delivered claims while dropping malformed claim entries", () => {
    render(
      <NotesPanel
        events={[
          feedEvent(
            "distillation.delivered",
            {
              request_event_id: "event-request-1",
              claims: [
                {
                  claim_id: " claim-1 ",
                  text: "  Valid claim text. ",
                  confidence: "not-a-confidence",
                  attribution_region_ids: [" region-1 ", "", 9, "region-1"],
                },
                {
                  claim_id: "claim-2",
                  text: "",
                  confidence: "high",
                  attribution_region_ids: [],
                },
              ],
              rendered_text: "  Summary text. ",
              token_count: "2048",
            },
            1,
          ),
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
          element?.textContent === "synthesizer · 1 claim · 2048 tok",
      ),
    ).toBeTruthy();
    expect(screen.getByText("Summary text.")).toBeTruthy();
    expect(screen.getByText("Valid claim text.")).toBeTruthy();
    expect(screen.getAllByTitle("open attribution region region-1 in viewer")).toHaveLength(1);
    expect(screen.queryByText("claim-2")).toBeNull();
    expect(document.body.textContent).not.toMatch(/NaN|Infinity|undefined/);
  });

  it("sanitizes grounding verdicts before claim cards consume them", () => {
    render(
      <NotesPanel
        events={[
          feedEvent(
            "distillation.delivered",
            {
              request_event_id: "event-request-1",
              claims: [
                {
                  claim_id: "claim-pass",
                  text: "Passed claim.",
                  confidence: "high",
                  attribution_region_ids: [],
                },
                {
                  claim_id: "claim-fail",
                  text: "Failed claim.",
                  confidence: "low",
                  attribution_region_ids: [],
                },
              ],
              rendered_text: "Grounding summary.",
              token_count: 512,
            },
            1,
          ),
          feedEvent(
            "claim.grounding_check_passed",
            {
              claim_id: " claim-pass ",
              located_region_id: " region-pass ",
              confidence: "2",
            },
            2,
          ),
          feedEvent(
            "claim.grounding_check_failed",
            {
              claim_id: "claim-fail",
              reason: "ambiguous",
              searched_regions: "not-an-array",
            },
            3,
          ),
        ]}
        status="open"
        reconnects={0}
        investigationId="inv-1"
        documentId="doc-1"
      />,
    );

    expect(
      screen.getByText((_, element) => element?.textContent === "· 100%"),
    ).toBeTruthy();
    expect(screen.getByTitle("open region region-pass in viewer")).toBeTruthy();
    expect(screen.getByText("ambiguous")).toBeTruthy();
    expect(
      screen.getByText(
        (_, element) => element?.textContent === "· searched 0 regions",
      ),
    ).toBeTruthy();
    expect(document.body.textContent).not.toMatch(/NaN|Infinity|undefined/);
  });

  it("opens the canonical Reader at the selected region page from a grounded claim", () => {
    render(
      <NotesPanel
        events={[
          feedEvent(
            "document.region_selected",
            {
              region_id: "region-pass",
              page: 7,
              char_start: 10,
              char_end: 30,
              bbox: [0, 0, 10, 10],
              text_excerpt: "source passage",
            },
            1,
          ),
          feedEvent(
            "distillation.delivered",
            {
              request_event_id: "event-request-1",
              claims: [
                {
                  claim_id: "claim-pass",
                  text: "Passed claim.",
                  confidence: "high",
                  attribution_region_ids: ["region-pass"],
                },
              ],
              rendered_text: "Grounding summary.",
              token_count: 512,
            },
            2,
          ),
          feedEvent(
            "claim.grounding_check_passed",
            {
              claim_id: "claim-pass",
              located_region_id: "region-pass",
              confidence: 0.91,
            },
            3,
          ),
        ]}
        status="open"
        reconnects={0}
        investigationId="inv-1"
        documentId="doc-1"
      />,
    );

    fireEvent.click(screen.getByTitle("open region region-pass in viewer"));

    expect(openDocumentMock).toHaveBeenCalledWith("doc-1", { page: 6 });
  });

  it("opens the canonical Reader from a claim attribution chip before grounding", () => {
    render(
      <NotesPanel
        events={[
          feedEvent(
            "document.region_selected",
            {
              region_id: "region-attr",
              page: 3,
              char_start: 10,
              char_end: 30,
              bbox: [0, 0, 10, 10],
              text_excerpt: "source passage",
            },
            1,
          ),
          feedEvent(
            "distillation.delivered",
            {
              request_event_id: "event-request-1",
              claims: [
                {
                  claim_id: "claim-attr",
                  text: "Attributed claim.",
                  confidence: "moderate",
                  attribution_region_ids: ["region-attr"],
                },
              ],
              rendered_text: "Claim summary.",
              token_count: 256,
            },
            2,
          ),
        ]}
        status="open"
        reconnects={0}
        investigationId="inv-1"
        documentId="doc-1"
      />,
    );

    fireEvent.click(screen.getByTitle("open attribution region region-attr in viewer"));

    expect(openDocumentMock).toHaveBeenCalledWith("doc-1", { page: 2 });
  });
});
