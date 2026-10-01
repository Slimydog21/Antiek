import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

/**
 * ConnectResearch.test — the M1 connect step (SPR-09).
 *
 * Mechanically checked:
 *  - picking an existing project connects the piece to it (resolves its id);
 *  - starting empty resolves an explicit no-research choice;
 *  - research starts only through the separately named research choice.
 */

const { listInvestigationsMock, startInvestigationMock } = vi.hoisted(() => ({
  listInvestigationsMock: vi.fn(),
  startInvestigationMock: vi.fn(),
}));

vi.mock("../../lib/api", async (orig) => ({
  ...(await orig<typeof import("../../lib/api")>()),
  listInvestigations: listInvestigationsMock,
  startInvestigation: startInvestigationMock,
}));

import ConnectResearch from "./ConnectResearch";

beforeEach(() => {
  listInvestigationsMock.mockReset().mockResolvedValue({
    count: 1,
    investigations: [
      {
        investigation_id: "inv-existing", question: "Why do margins compress?",
        status: "completed", started_at: null, completed_at: null,
        cost_usd_total: 0, parent_investigation_id: null,
      },
    ],
  });
  startInvestigationMock.mockReset().mockResolvedValue({
    investigation_id: "inv-spawned", status: "in_progress", start_event_id: "ev-1",
  });
});
afterEach(cleanup);

describe("ConnectResearch: empty or explicit research", () => {
  it("picking an existing project resolves its investigation id", async () => {
    const onConnect = vi.fn();
    render(<ConnectResearch pieceTitle="My memo" onConnect={onConnect} />);
    await userEvent.click(await screen.findByText("Why do margins compress?"));
    expect(onConnect).toHaveBeenCalledWith(
      expect.objectContaining({ investigationId: "inv-existing" }),
    );
    // No spawn — we connected to an existing folder.
    expect(startInvestigationMock).not.toHaveBeenCalled();
  });

  it("starting empty never launches research", async () => {
    const onConnect = vi.fn();
    render(<ConnectResearch pieceTitle="My memo" onConnect={onConnect} />);
    await userEvent.click(await screen.findByRole("button", { name: /start empty/i }));
    expect(onConnect).toHaveBeenCalledWith({ kind: "empty" });
    expect(startInvestigationMock).not.toHaveBeenCalled();
  });

  it("a failed list is surfaced while starting empty remains available", async () => {
    listInvestigationsMock.mockRejectedValue(new Error("list unavailable"));
    const onConnect = vi.fn();
    render(<ConnectResearch pieceTitle="My memo" onConnect={onConnect} />);
    await waitFor(() => expect(screen.getByRole("alert")).toBeTruthy());
    await userEvent.click(await screen.findByRole("button", { name: /start empty/i }));
    expect(onConnect).toHaveBeenCalledWith({ kind: "empty" });
    expect(startInvestigationMock).not.toHaveBeenCalled();
  });

  it("only the explicit research-first choice requests a launch", async () => {
    const onConnect = vi.fn();
    render(<ConnectResearch pieceTitle="My memo" onConnect={onConnect} />);
    await userEvent.click(await screen.findByText(/start research first/i));
    expect(onConnect).toHaveBeenCalledWith({ kind: "new-research", request: expect.objectContaining({ question: "My memo" }) });
    expect(startInvestigationMock).not.toHaveBeenCalled();
  });
});
