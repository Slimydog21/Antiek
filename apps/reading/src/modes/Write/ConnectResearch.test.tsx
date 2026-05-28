import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

/**
 * ConnectResearch.test — the M1 connect step (SPR-09).
 *
 * Mechanically checked:
 *  - picking an existing project connects the piece to it (resolves its id);
 *  - "none" AUTO-SPAWNS a research folder (startInvestigation) and connects to
 *    the spawned id — the bridge that keeps Write net-new but always backed.
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

describe("ConnectResearch — M1 connect or auto-spawn", () => {
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

  it('"none" auto-spawns a folder and connects to the spawned id', async () => {
    const onConnect = vi.fn();
    render(<ConnectResearch pieceTitle="My memo" onConnect={onConnect} />);
    await userEvent.click(await screen.findByText(/start without a project/i));
    await waitFor(() =>
      expect(onConnect).toHaveBeenCalledWith(
        expect.objectContaining({ investigationId: "inv-spawned" }),
      ),
    );
    // The spawned folder is seeded with the piece title (legible, not blank).
    expect(startInvestigationMock).toHaveBeenCalledWith(
      expect.objectContaining({ question: "My memo" }),
    );
  });

  it("a failed spawn is surfaced, never a silent connect", async () => {
    startInvestigationMock.mockRejectedValue(new Error("provider down"));
    const onConnect = vi.fn();
    render(<ConnectResearch pieceTitle="My memo" onConnect={onConnect} />);
    await userEvent.click(await screen.findByText(/start without a project/i));
    await waitFor(() => expect(screen.getByRole("alert")).toBeTruthy());
    expect(onConnect).not.toHaveBeenCalled();
  });
});
