/**
 * OutcomesIndex.test.tsx — SPR-06 M3 (audit + minimal clarification).
 *
 * M3 is a CLARIFICATION, not a rebuild: the cross-investigation grading history
 * already shipped (OutcomesIndex reads GET /outcomes →
 * middleware.backtest.db.load_outcomes_for_synthesis, read by the Phase 8 gate;
 * no new grading concept/table/rubric is introduced here). This test pins:
 *   - the index renders the cross-investigation grading history from the EXISTING
 *     /outcomes data;
 *   - the empty state EXPLAINS what Outcomes IS (the grading/quality history) so a
 *     first-time user isn't confused by a blank tab.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

const apiFetchMock = vi.hoisted(() => vi.fn());
vi.mock("../../lib/api", async (orig) => ({
  ...(await orig<typeof import("../../lib/api")>()),
  apiFetch: apiFetchMock,
}));

import OutcomesIndex from "./index";

afterEach(() => {
  cleanup();
  apiFetchMock.mockReset();
});

function renderIndex() {
  return render(
    <MemoryRouter>
      <OutcomesIndex />
    </MemoryRouter>,
  );
}

describe("OutcomesIndex — cross-investigation grading history (M3)", () => {
  it("renders the existing /outcomes grading history", async () => {
    apiFetchMock.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        outcomes: [
          {
            outcome_id: "o1",
            synthesis_id: "syn-1",
            observer: "__operator__",
            observed_at: "2026-05-28",
          },
        ],
      }),
    });
    renderIndex();
    await waitFor(() => expect(screen.getByText("syn-1")).toBeTruthy());
    // The header frames it as the cross-investigation grading history.
    expect(screen.getByText(/Cross-investigation grading history/i)).toBeTruthy();
  });

  it("empty state explains what Outcomes IS (the grading/quality history)", async () => {
    apiFetchMock.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ outcomes: [] }),
    });
    renderIndex();
    await waitFor(() =>
      expect(
        screen.getByText(/grading \/ quality history of your\s+investigations/i),
      ).toBeTruthy(),
    );
    // It names the three verdicts so the concept is legible, not a blank tab.
    expect(
      screen.getByText(/validated, falsified, or indeterminate/i),
    ).toBeTruthy();
  });

  it("renders session thinking + living-TV brand chrome on the Outcomes door", async () => {
    apiFetchMock.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ outcomes: [] }),
    });
    renderIndex();
    await waitFor(() =>
      expect(screen.getByText(/Outcomes audit/i)).toBeTruthy(),
    );
    expect(screen.getByTestId("outcomes-home-werner-brand")).toBeTruthy();
    const livingTv = screen.getByTestId(
      "outcomes-home-living-tv-art",
    ) as HTMLImageElement;
    expect(livingTv.getAttribute("src") ?? "").toMatch(
      /werner_living_tv_session_v1/,
    );
  });
});
