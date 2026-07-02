import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }));
vi.mock("../lib/api", async (orig) => {
  const actual = await orig<typeof import("../lib/api")>();
  return { ...actual, API_BASE: "", apiFetch: apiFetchMock };
});

import { ArtifactExport } from "./ArtifactExport";

afterEach(() => cleanup());

beforeEach(() => {
  apiFetchMock.mockReset();
  (URL as unknown as { createObjectURL: () => string }).createObjectURL = vi.fn(
    () => "blob:x",
  );
  (URL as unknown as { revokeObjectURL: () => void }).revokeObjectURL = vi.fn();
});

describe("ArtifactExport", () => {
  it("renders all three formats with neutral, equal-prominence labels", () => {
    render(<ArtifactExport basePath="/api/syntheses/x" filenamePrefix="synthesis-x" />);
    expect(screen.getByRole("button", { name: "HTML" })).toBeTruthy();
    expect(screen.getByRole("button", { name: ".antiek" })).toBeTruthy();
    expect(screen.getByRole("button", { name: ".antiek.html" })).toBeTruthy();
  });

  it("fires the multi-format route for the clicked format", async () => {
    apiFetchMock.mockResolvedValue({
      ok: true,
      status: 200,
      blob: async () => new Blob(["x"]),
    });
    render(<ArtifactExport basePath="/api/notebooks/nb1" filenamePrefix="notebook-nb1" />);
    fireEvent.click(screen.getByRole("button", { name: ".antiek" }));
    await waitFor(() => expect(apiFetchMock).toHaveBeenCalledTimes(1));
    expect(String(apiFetchMock.mock.calls[0][0])).toContain(
      "/api/notebooks/nb1/artifact?format=antiek",
    );
  });

  it("surfaces the 403 rights reason verbatim, not a generic error", async () => {
    apiFetchMock.mockResolvedValue({
      status: 403,
      ok: false,
      json: async () => ({ reason: "owner withheld this synthesis" }),
    });
    render(<ArtifactExport basePath="/api/syntheses/x" filenamePrefix="synthesis-x" />);
    fireEvent.click(screen.getByRole("button", { name: "HTML" }));
    await waitFor(() =>
      expect(screen.getByText(/owner withheld this synthesis/)).toBeTruthy(),
    );
  });
});
