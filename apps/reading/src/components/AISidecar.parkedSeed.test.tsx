import { afterEach, describe, expect, it, vi, beforeEach } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";

/**
 * FFX-KPA SPR-03 M5 — a seed sent while the lazy AISidecar panel is still
 * loading must not be lost: the zen home opens the pane and seeds it in the
 * same tick. Mocks copied from AISidecar.context-wiring.test.tsx.
 */
vi.mock("../lib/api", () => ({
  ApiError: class ApiError extends Error {
    status: number;
    constructor(message: string, status: number) {
      super(message);
      this.status = status;
    }
  },
  apiFetch: vi.fn(),
  composeContext: vi.fn(),
}));
vi.mock("../brand/mascot/animated", () => ({
  BrainThinking: () => null,
}));
vi.mock("../hooks/useReplyMode", () => ({
  useReplyMode: () => ({ mode: "text", setMode: () => undefined }),
}));
vi.mock("./SpokenReply", () => ({
  __esModule: true,
  default: () => null,
}));
vi.mock("./ai/aiActions", () => ({
  dispatchAiAction: vi.fn(),
  parseAssistantReply: () => ({ prose: "ok", actions: [], parseErrors: [] }),
  // Sentinel so the fallback path is distinguishable from any composed ctx.
  workspaceContextPrompt: () => "OPAQUE-WORKSPACE-CTX",
}));

import { apiFetch } from "../lib/api";
import { composeContext } from "../lib/api";
import AISidecar from "./AISidecar";
import { seedThoughtPartner, takePendingThoughtPartnerSeed } from "./ai/thoughtPartnerSeed";

const apiFetchMock = apiFetch as unknown as ReturnType<typeof vi.fn>;
void composeContext;

beforeEach(() => {
  apiFetchMock.mockReset().mockResolvedValue({ ok: false, status: 404 });
  takePendingThoughtPartnerSeed();
});
afterEach(() => cleanup());

describe("AISidecar — parked seed (SPR-03 M5)", () => {
  it("a seed sent before mount lands in the draft on mount", async () => {
    seedThoughtPartner({ prompt: "a biography of my grandmother", system_context: "INTERVIEW-CTX", source_label: "zen-home" });
    render(<AISidecar />);
    await waitFor(() =>
      expect((screen.getByPlaceholderText("What's the question?") as HTMLTextAreaElement).value).toBe(
        "a biography of my grandmother",
      ),
    );
  });

  it("a seed the mounted sidecar already took is not replayed on a later mount", async () => {
    const first = render(<AISidecar />);
    seedThoughtPartner({ prompt: "live seed" });
    await waitFor(() =>
      expect((screen.getByPlaceholderText("What's the question?") as HTMLTextAreaElement).value).toBe("live seed"),
    );
    first.unmount();
    render(<AISidecar />);
    expect((screen.getByPlaceholderText("What's the question?") as HTMLTextAreaElement).value).toBe("");
  });

  it("a parked seed expires after ten seconds", () => {
    seedThoughtPartner({ prompt: "old" });
    expect(takePendingThoughtPartnerSeed(Date.now() + 10_001)).toBeNull();
    seedThoughtPartner({ prompt: "fresh" });
    expect(takePendingThoughtPartnerSeed()).toEqual({ prompt: "fresh" });
    expect(takePendingThoughtPartnerSeed()).toBeNull();
  });
});
