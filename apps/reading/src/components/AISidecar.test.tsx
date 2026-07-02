import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Event } from "../generated/types";
import AISidecar from "./AISidecar";

const { apiFetchMock, spokenReplyMock, replyModeState } = vi.hoisted(() => ({
  apiFetchMock: vi.fn(),
  spokenReplyMock: vi.fn(),
  replyModeState: { mode: "text" as "text" | "audio", setMode: vi.fn() },
}));

vi.mock("../lib/api", async (orig) => {
  const actual = await orig<typeof import("../lib/api")>();
  return {
    ...actual,
    apiFetch: apiFetchMock,
  };
});

vi.mock("./SpokenReply", () => ({
  default: (props: { text: string; autoPlay?: boolean }) => {
    spokenReplyMock(props);
    return (
      <div data-testid="spoken-reply" data-autoplay={String(Boolean(props.autoPlay))}>
        {props.text}
      </div>
    );
  },
}));

vi.mock("../hooks/useReplyMode", () => ({
  useReplyMode: () => ({
    mode: replyModeState.mode,
    setMode: replyModeState.setMode,
  }),
}));

const okJson = (body: unknown) =>
  ({
    ok: true,
    json: async () => body,
  }) as Response;

function dispatchEvent(
  id: string,
  payload: Record<string, unknown>,
  over: Partial<Event> = {},
): Event {
  return {
    event_id: id,
    investigation_id: "inv-1",
    action_type: "dispatch.call",
    payload: {
      action_type: "dispatch.call",
      ...payload,
    } as Event["payload"],
    param_version: "test",
    emitted_at: "2026-07-01T12:00:00Z",
    ...over,
  };
}

beforeEach(() => {
  apiFetchMock.mockReset();
  spokenReplyMock.mockReset();
  replyModeState.mode = "text";
  replyModeState.setMode.mockReset();
  apiFetchMock.mockImplementation(async (input: RequestInfo | URL) => {
    const path = String(input);
    if (path.includes("/billing/summary/")) {
      return okJson({
        free_tokens_consumed: Number.POSITIVE_INFINITY,
        free_tokens_remaining: Number.NaN,
        record_count: -1,
      });
    }
    if (path.includes("/trajectory")) {
      return okJson({
        events: [
          dispatchEvent("valid-bad-latency", {
              call_id: "call-bad",
              tier: "synthesis",
              provider: "openai",
              model: "gpt-5.5",
              latency_ms: Number.POSITIVE_INFINITY,
          }),
          dispatchEvent("valid-good", {
              call_id: "call-good",
              tier: "verify",
              provider: "anthropic",
              model: "claude",
              latency_ms: 1532,
          }),
          {
            payload: {
              call_id: "call-fabricated",
              tier: "fake",
              provider: "bad",
              model: "row",
              latency_ms: 1,
            },
          },
          dispatchEvent("mismatch", {
            call_id: "call-mismatch",
            tier: "fake",
            provider: "bad",
            model: "mismatch",
            latency_ms: 1,
          }, { payload: { action_type: "phase.enter" } as Event["payload"] }),
          dispatchEvent("not-dispatch", {
            call_id: "call-not-dispatch",
            tier: "fake",
            provider: "bad",
            model: "wrong-action",
            latency_ms: 1,
          }, { action_type: "phase.enter" }),
        ],
      });
    }
    return okJson({});
  });
});

afterEach(() => cleanup());

describe("AISidecar", () => {
  it("sanitizes malformed usage and dispatch latency before rendering", async () => {
    render(<AISidecar />);

    await screen.findByText("synthesis · openai/gpt-5.5");
    expect(screen.getByText("0 / 5,000,000 tokens")).toBeTruthy();
    expect(screen.getByText("0ms")).toBeTruthy();
    expect(screen.getByText("1532ms")).toBeTruthy();
    await waitFor(() =>
      expect(document.body.textContent).not.toMatch(/NaN|Infinity/),
    );
    expect(document.body.textContent).not.toMatch(/fake · bad\/row|bad\/mismatch|bad\/wrong-action/);
  });

  it("keeps dispatch context visible when usage JSON is not an object", async () => {
    apiFetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      const path = String(input);
      if (path.includes("/billing/summary/")) {
        return okJson(null);
      }
      if (path.includes("/trajectory")) {
        return okJson({
          events: [
            dispatchEvent("valid-after-bad-usage", {
              call_id: "call-visible",
              tier: "route",
              provider: "openai",
              model: "gpt-5.5",
              latency_ms: 44,
            }),
          ],
        });
      }
      return okJson({});
    });

    render(<AISidecar />);

    expect(await screen.findByText("route · openai/gpt-5.5")).toBeTruthy();
    expect(screen.getByText("0 / 5,000,000 tokens")).toBeTruthy();
    expect(screen.getByText("44ms")).toBeTruthy();
  });

  it("sanitizes malformed thought-partner replies before parsing actions", async () => {
    apiFetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      const path = String(input);
      if (path.includes("/billing/summary/")) {
        return okJson({
          free_tokens_consumed: 12,
          free_tokens_remaining: 4_999_988,
          record_count: 1,
        });
      }
      if (path.includes("/trajectory")) {
        return okJson({ events: [] });
      }
      if (path === "/thought-partner") {
        return okJson({
          shape: "UNBOUNDED",
          text: "  Reply text  ",
        });
      }
      return okJson({});
    });

    render(<AISidecar />);

    await userEvent.type(await screen.findByPlaceholderText("What's the question?"), "challenge this");
    await userEvent.click(screen.getByRole("button", { name: "Send" }));

    expect(await screen.findAllByText("Reply text")).toHaveLength(2);
    expect(screen.getByText("SYNTHESIS")).toBeTruthy();
    expect(screen.queryByText("UNBOUNDED")).toBeNull();
  });

  it("keeps rabbit-hole reply text visible and auto-speaks only when audio mode is selected", async () => {
    replyModeState.mode = "audio";
    apiFetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      const path = String(input);
      if (path.includes("/billing/summary/")) return okJson({});
      if (path.includes("/trajectory")) return okJson({ events: [] });
      if (path === "/thought-partner") {
        return okJson({ shape: "SYNTHESIS", text: "Audio-mode reply" });
      }
      return okJson({});
    });

    render(<AISidecar />);

    await userEvent.type(await screen.findByPlaceholderText("What's the question?"), "read this back");
    await userEvent.click(screen.getByRole("button", { name: "Send" }));

    expect(await screen.findAllByText("Audio-mode reply")).toHaveLength(2);
    expect(screen.getByTestId("spoken-reply").getAttribute("data-autoplay")).toBe("true");
    expect(spokenReplyMock).toHaveBeenLastCalledWith(
      expect.objectContaining({ text: "Audio-mode reply", autoPlay: true }),
    );
  });
});
