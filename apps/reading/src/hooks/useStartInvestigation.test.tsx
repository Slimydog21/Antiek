import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, startInvestigation } from "../lib/api";
import { useStartInvestigation } from "./useStartInvestigation";

vi.mock("../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../lib/api")>();
  return { ...actual, startInvestigation: vi.fn() };
});

vi.mock("./useEventStream", () => ({
  useEventStream: () => ({ events: [], status: "closed", reconnects: 0 }),
}));

const startInvestigationMock = vi.mocked(startInvestigation);

afterEach(() => {
  cleanup();
  vi.resetAllMocks();
});

describe("useStartInvestigation submit errors", () => {
  it("directs an exact connect_model conflict to Settings", async () => {
    startInvestigationMock.mockRejectedValue(
      new ApiError("POST /investigations failed: HTTP 409", 409, '{"detail":"connect_model"}'),
    );
    const { result } = renderHook(() => useStartInvestigation());

    await act(async () => {
      await result.current.submit({ question: "Explain payer containment" });
    });

    expect(result.current.error).toBe(
      "Choose a model in Settings, then try starting your research again.",
    );
  });

  it("keeps other failures generic without exposing provider or response details", async () => {
    startInvestigationMock.mockRejectedValue(
      new ApiError(
        "POST /investigations failed: HTTP 500",
        500,
        '{"detail":"provider-secret-value"}',
      ),
    );
    const { result } = renderHook(() => useStartInvestigation());

    await act(async () => {
      await result.current.submit({ question: "Explain payer containment" });
    });

    expect(result.current.error).toBe("Submit failed. Please try again.");
    expect(result.current.error).not.toContain("provider-secret-value");
  });

  it.each([
    ["an unrelated conflict code", '{"detail":"different_conflict"}'],
    ["a malformed response body", "not-json"],
  ])("keeps a 409 with %s generic", async (_description, body) => {
    startInvestigationMock.mockRejectedValue(
      new ApiError("POST /investigations failed: HTTP 409", 409, body),
    );
    const { result } = renderHook(() => useStartInvestigation());

    await act(async () => {
      await result.current.submit({ question: "Explain payer containment" });
    });

    expect(result.current.error).toBe("Submit failed. Please try again.");
  });
});
