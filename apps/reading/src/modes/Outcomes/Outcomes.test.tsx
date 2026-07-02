import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import Outcomes from "./index";

const apiFetchMock = vi.hoisted(() => vi.fn());

vi.mock("../../lib/api", async (orig) => {
  const actual = await orig<typeof import("../../lib/api")>();
  return {
    ...actual,
    apiFetch: apiFetchMock,
  };
});

beforeEach(() => {
  Object.defineProperty(window, "matchMedia", {
    configurable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  });
  apiFetchMock.mockReset();
  apiFetchMock.mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => ({
      outcomes: [
        {
          outcome_id: " outcome dirty ",
          observer: " reviewer dirty ",
          observed_at: " 2026-06-01 ",
          thesis_outcomes: [
            { kind: " validated ", note: " thesis note " },
            { kind: "validated", note: " " },
            { kind: null, note: "Skipped nested note" },
          ],
          falsification_outcomes: [
            { kind: " falsified ", note: " falsification note " },
          ],
          execution_risk_outcomes: [
            { kind: " indeterminate ", note: " risk note " },
            "Skipped scalar",
          ],
          notes: " row note ",
        },
        {
          outcome_id: " ",
          observer: "Skipped row",
          observed_at: "Skipped date",
          thesis_outcomes: [{ kind: "validated", note: "Skipped note" }],
        },
      ],
    }),
  });
});

afterEach(() => cleanup());

function renderOutcomes() {
  return render(
    <MemoryRouter initialEntries={["/outcomes/syn-1"]}>
      <Routes>
        <Route path="/outcomes/:synthesisId" element={<Outcomes />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("Outcomes", () => {
  it("sanitizes outcome detail rows before rendering counts and history", async () => {
    renderOutcomes();

    expect(await screen.findByText("2026-06-01 · reviewer dirty")).toBeTruthy();
    expect(screen.getByText("validated — thesis note")).toBeTruthy();
    expect(screen.getByText("falsified — falsification note")).toBeTruthy();
    expect(screen.getByText("indeterminate — risk note")).toBeTruthy();
    expect(screen.getByText("Note: row note")).toBeTruthy();
    expect(screen.getAllByText("1")).toHaveLength(3);
    expect(document.body.textContent).not.toMatch(
      /Skipped|outcome dirty|Skipped nested note/,
    );
  });
});
