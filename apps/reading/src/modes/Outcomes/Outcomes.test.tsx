import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useNavigate } from "react-router-dom";
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

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((res) => {
    resolve = res;
  });
  return { promise, resolve };
}

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

function RouteSwitchProbe() {
  const navigate = useNavigate();
  return (
    <button type="button" onClick={() => navigate("/outcomes/syn-fresh")}>
      open fresh synthesis
    </button>
  );
}

function renderOutcomesWithSwitch() {
  return render(
    <MemoryRouter initialEntries={["/outcomes/syn-stale"]}>
      <RouteSwitchProbe />
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

  it("keeps stale outcome detail loads from overwriting the active synthesis", async () => {
    const stale = deferred<{
      ok: true;
      status: 200;
      json: () => Promise<{ outcomes: unknown[] }>;
    }>();
    const fresh = deferred<{
      ok: true;
      status: 200;
      json: () => Promise<{ outcomes: unknown[] }>;
    }>();
    apiFetchMock.mockReset();
    apiFetchMock.mockReturnValueOnce(stale.promise).mockReturnValueOnce(fresh.promise);

    renderOutcomesWithSwitch();
    fireEvent.click(screen.getByRole("button", { name: /open fresh synthesis/i }));

    await act(async () => {
      fresh.resolve({
        ok: true,
        status: 200,
        json: async () => ({
          outcomes: [
            {
              outcome_id: "fresh-outcome",
              observer: "fresh reviewer",
              observed_at: "2026-06-03",
              thesis_outcomes: [{ kind: "validated", note: "fresh note" }],
            },
          ],
        }),
      });
    });

    expect(await screen.findByText("2026-06-03 · fresh reviewer")).toBeTruthy();
    expect(screen.getByText("validated — fresh note")).toBeTruthy();

    await act(async () => {
      stale.resolve({
        ok: true,
        status: 200,
        json: async () => ({
          outcomes: [
            {
              outcome_id: "stale-outcome",
              observer: "stale reviewer",
              observed_at: "2026-06-02",
              thesis_outcomes: [{ kind: "validated", note: "stale note" }],
            },
          ],
        }),
      });
    });

    expect(screen.getByText("validated — fresh note")).toBeTruthy();
    expect(screen.queryByText("validated — stale note")).toBeNull();
    expect(screen.queryByText("2026-06-02 · stale reviewer")).toBeNull();
  });
});
