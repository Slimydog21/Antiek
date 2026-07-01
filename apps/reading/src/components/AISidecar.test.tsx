import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import AISidecar from "./AISidecar";

const apiFetchMock = vi.hoisted(() => vi.fn());

vi.mock("../lib/api", async (orig) => {
  const actual = await orig<typeof import("../lib/api")>();
  return {
    ...actual,
    apiFetch: apiFetchMock,
  };
});

const okJson = (body: unknown) =>
  ({
    ok: true,
    json: async () => body,
  }) as Response;

beforeEach(() => {
  apiFetchMock.mockReset();
  apiFetchMock.mockImplementation(async (input: RequestInfo | URL) => {
    const path = String(input);
    if (path.includes("/billing/summary/")) {
      return okJson({
        free_tokens_consumed: 1200,
        free_tokens_remaining: 4_998_800,
        record_count: 2,
      });
    }
    if (path.includes("/trajectory")) {
      return okJson({
        events: [
          {
            action_type: "dispatch.call",
            payload: {
              call_id: "call-bad",
              tier: "synthesis",
              provider: "openai",
              model: "gpt-5.5",
              latency_ms: Number.POSITIVE_INFINITY,
            },
          },
          {
            action_type: "dispatch.call",
            payload: {
              call_id: "call-good",
              tier: "verify",
              provider: "anthropic",
              model: "claude",
              latency_ms: 1532,
            },
          },
        ],
      });
    }
    return okJson({});
  });
});

afterEach(() => cleanup());

describe("AISidecar", () => {
  it("sanitizes malformed dispatch latency before rendering recent calls", async () => {
    render(<AISidecar />);

    await screen.findByText("synthesis · openai/gpt-5.5");
    expect(screen.getByText("0ms")).toBeTruthy();
    expect(screen.getByText("1532ms")).toBeTruthy();
    await waitFor(() =>
      expect(document.body.textContent).not.toMatch(/NaN|Infinity/),
    );
  });
});
