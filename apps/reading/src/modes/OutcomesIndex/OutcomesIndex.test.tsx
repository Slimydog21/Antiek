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
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router-dom";

const apiFetchMock = vi.hoisted(() => vi.fn());
vi.mock("../../lib/api", async (orig) => ({
  ...(await orig<typeof import("../../lib/api")>()),
  apiFetch: apiFetchMock,
}));

import OutcomesIndex from "./index";

function LocationProbe() {
  const location = useLocation();
  return <div data-testid="location">{location.pathname}</div>;
}

afterEach(() => {
  cleanup();
  apiFetchMock.mockReset();
});

function renderIndex() {
  return render(
    <MemoryRouter initialEntries={["/outcomes"]}>
      <OutcomesIndex />
      <LocationProbe />
    </MemoryRouter>,
  );
}

describe("OutcomesIndex — cross-investigation grading history (M3)", () => {
  it("renders review history with user-facing labels instead of raw handles", async () => {
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

    expect(await screen.findByText("Review 1 from 2026-05-28")).toBeTruthy();
    expect(screen.getByText("Open the graded answer and replay")).toBeTruthy();
    expect(screen.getByText("You")).toBeTruthy();
    expect(screen.getByText("Open details")).toBeTruthy();
    expect(screen.queryByText("syn-1")).toBeNull();
    expect(screen.queryByText("o1")).toBeNull();
    expect(screen.queryByText("__operator__")).toBeNull();
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
        screen.getByText(/No reviews yet/i),
      ).toBeTruthy(),
    );
    // It names the three verdicts so the concept is legible, not a blank tab.
    expect(
      screen.getByText(/validated, falsified, or indeterminate/i),
    ).toBeTruthy();
  });

  it("filters 'you' through the backend observer contract", async () => {
    apiFetchMock.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ outcomes: [] }),
    });
    renderIndex();

    await screen.findByText(/No reviews yet/i);
    await userEvent.type(screen.getByLabelText("Filter by reviewer"), "You");

    await waitFor(() => {
      expect(
        apiFetchMock.mock.calls.some(([path]) =>
          String(path).includes("observer=__operator__"),
        ),
      ).toBe(true);
    });
    expect(screen.queryByPlaceholderText(/__operator__/i)).toBeNull();
    expect(await screen.findByText(/No reviews match this filter yet/i)).toBeTruthy();
  });

  it("keeps non-operator reviewer handles filterable as displayed", async () => {
    apiFetchMock.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        outcomes: [
          {
            outcome_id: "outcome-2",
            synthesis_id: "syn-2",
            observer: "agent_beta",
            observed_at: "2026-05-29",
          },
        ],
      }),
    });
    renderIndex();

    expect(await screen.findByText("agent_beta")).toBeTruthy();
    await userEvent.type(screen.getByLabelText("Filter by reviewer"), "agent_beta");

    await waitFor(() => {
      expect(
        apiFetchMock.mock.calls.some(([path]) =>
          String(path).includes("observer=agent_beta"),
        ),
      ).toBe(true);
    });
  });

  it("keeps same-day reviews distinguishable without raw ids", async () => {
    apiFetchMock.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        outcomes: [
          {
            outcome_id: "outcome-1",
            synthesis_id: "syn-1",
            observer: "__operator__",
            observed_at: "2026-05-28",
          },
          {
            outcome_id: "outcome-2",
            synthesis_id: "syn-2",
            observer: "agent_beta",
            observed_at: "2026-05-28",
          },
        ],
      }),
    });
    renderIndex();

    expect(await screen.findByText("Review 1 from 2026-05-28")).toBeTruthy();
    expect(screen.getByText("Review 2 from 2026-05-28")).toBeTruthy();
    expect(screen.queryByText("syn-1")).toBeNull();
    expect(screen.queryByText("outcome-1")).toBeNull();
  });

  it("opens a review row on the canonical detail route", async () => {
    apiFetchMock.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        outcomes: [
          {
            outcome_id: "outcome-1",
            synthesis_id: "syn-1",
            observer: "__operator__",
            observed_at: "2026-05-28",
          },
        ],
      }),
    });
    renderIndex();

    await userEvent.click(await screen.findByText("Review 1 from 2026-05-28"));

    expect(screen.getByTestId("location").textContent).toBe("/outcomes/syn-1");
  });
});
