/**
 * FFX SPR-04 M1 (F-10 / A-18): a table the backend reports as missing is not
 * a table with zero rows, and a failed load never shows a status line.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }));

vi.mock("../../lib/api", async (orig) => {
  const actual = await orig<typeof import("../../lib/api")>();
  return { ...actual, apiFetch: apiFetchMock };
});

import Stats from ".";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

beforeEach(() => apiFetchMock.mockReset());
afterEach(() => cleanup());

describe("Stats (F-10)", () => {
  it("renders a missing table as a dash with its reason, never 0", async () => {
    apiFetchMock.mockResolvedValue(
      jsonResponse({
        counts: { investigations: 3, outcomes: 0 },
        warnings: ["table 'skill_rules' not present"],
      }),
    );
    render(<Stats />);

    const label = await screen.findByText("skill rules");
    const tile = label.parentElement as HTMLElement;
    expect(tile.textContent).toContain("—");
    expect(tile.textContent).toContain("not present in this substrate");
    expect(tile.textContent).not.toMatch(/\d/);

    // A table the backend counted as zero is still an honest 0.
    const outcomes = screen.getByText("outcomes").parentElement as HTMLElement;
    expect(outcomes.textContent).toContain("0");
    expect(outcomes.textContent).not.toContain("—");
    // A present, counted table keeps its number.
    expect((screen.getByText("investigations").parentElement as HTMLElement).textContent).toContain("3");
  });

  it("renders a table absent from counts with no warning as unknown, not 0", async () => {
    apiFetchMock.mockResolvedValue(jsonResponse({ counts: {}, warnings: [] }));
    render(<Stats />);
    const tile = (await screen.findByText("notebooks")).parentElement as HTMLElement;
    expect(tile.textContent).toContain("—");
    expect(tile.textContent).not.toMatch(/\d/);
  });

  it("describes a 503 without a status, method or path", async () => {
    apiFetchMock.mockResolvedValue(new Response("upstream down", { status: 503 }));
    render(<Stats />);
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("Couldn't load substrate stats.");
    expect(alert.textContent).not.toMatch(/\b\d{3}\b|HTTP|GET|\/stats/);
  });
});
