import { afterEach, describe, expect, it, vi, beforeEach } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

// Mock the heavy deps so the test isolates the CK-4 wiring logic.
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
vi.mock("../brand/werner/animated", () => ({
  WernerThinking: () => null,
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

const apiFetchMock = apiFetch as unknown as ReturnType<typeof vi.fn>;
const composeMock = composeContext as unknown as ReturnType<typeof vi.fn>;

/** apiFetch answers /thought-partner with a minimal reply; everything else
 *  (the mount-time usage/trajectory loads) gets a benign 404 so usage stays
 *  null and no error path interferes with the wiring under test. */
function mockApiFetch(): void {
  apiFetchMock.mockImplementation((url: string) => {
    if (typeof url === "string" && url.includes("/thought-partner")) {
      return Promise.resolve({
        ok: true,
        status: 200,
        json: async () => ({ text: "reply", shape: "SYNTHESIS" }),
      });
    }
    return Promise.resolve({ ok: false, status: 404 });
  });
}

function thoughtPartnerCall(): { url: string; body: Record<string, unknown> } | undefined {
  for (const [url, init] of apiFetchMock.mock.calls) {
    if (typeof url === "string" && url.includes("/thought-partner")) {
      const body = JSON.parse((init as RequestInit).body as string);
      return { url, body };
    }
  }
  return undefined;
}

async function composeContextViaPicker(ctx: string): Promise<void> {
  composeMock.mockResolvedValueOnce({
    system_context: ctx,
    withheld: [],
    missing: [],
  });
  fireEvent.change(screen.getByLabelText("Item id"), {
    target: { value: "doc-1" },
  });
  fireEvent.click(screen.getByText("Add"));
  fireEvent.click(screen.getByText("Compose context"));
  // onContextChange fires after the (mocked) compose resolves.
  await waitFor(() =>
    expect(screen.getByTestId("system-context").textContent).toContain(ctx),
  );
}

describe("AISidecar CK-4 context wiring", () => {
  beforeEach(() => {
    apiFetchMock.mockReset();
    composeMock.mockReset();
    mockApiFetch();
  });
  afterEach(cleanup);

  it("uses the composed §9.0 context as system_context when the operator picked one", async () => {
    render(<AISidecar />);

    await composeContextViaPicker("COMPOSED-CTX");

    fireEvent.change(screen.getByPlaceholderText("What's the question?"), {
      target: { value: "summarize this" },
    });
    fireEvent.click(screen.getByText("Send"));

    await waitFor(() => expect(thoughtPartnerCall()).toBeDefined());
    expect(thoughtPartnerCall()?.body.system_context).toBe("COMPOSED-CTX");
  });

  it("falls back to the opaque workspace context when nothing was composed", async () => {
    render(<AISidecar />);

    fireEvent.change(screen.getByPlaceholderText("What's the question?"), {
      target: { value: "summarize this" },
    });
    fireEvent.click(screen.getByText("Send"));

    await waitFor(() => expect(thoughtPartnerCall()).toBeDefined());
    expect(thoughtPartnerCall()?.body.system_context).toBe("OPAQUE-WORKSPACE-CTX");
  });
});
