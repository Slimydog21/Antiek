import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import Stats from "./index";

const apiFetchMock = vi.hoisted(() => vi.fn());

vi.mock("../../lib/api", async (orig) => {
  const actual = await orig<typeof import("../../lib/api")>();
  return {
    ...actual,
    apiFetch: apiFetchMock,
  };
});

beforeEach(() => {
  apiFetchMock.mockReset();
  apiFetchMock.mockResolvedValue({
    ok: true,
    json: async () => ({
      counts: {
        investigations: Number.POSITIVE_INFINITY,
        documents: Number.NaN,
        chunks: -12,
        nodes: "1500.9",
        edges: "not-a-count",
        " ": 42,
      },
      warnings: [" partial stats install ", "", { message: "leaky object" }],
    }),
  });
});

afterEach(() => cleanup());

describe("Stats", () => {
  it("sanitizes malformed table counts", async () => {
    render(<Stats />);

    expect(await screen.findByText("partial stats install")).toBeTruthy();
    expect(screen.getByText("1,500")).toBeTruthy();
    expect(document.body.textContent).not.toMatch(
      /NaN|Infinity|-12|leaky object|object Object/,
    );
    expect(screen.getAllByText("0").length).toBeGreaterThan(0);
  });
});
