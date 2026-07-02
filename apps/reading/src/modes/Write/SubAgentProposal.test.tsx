import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { searchRepositoryMock, startInvestigationMock } = vi.hoisted(() => ({
  searchRepositoryMock: vi.fn(),
  startInvestigationMock: vi.fn(),
}));

vi.mock("../../lib/api", async (orig) => ({
  ...(await orig<typeof import("../../lib/api")>()),
  startInvestigation: startInvestigationMock,
}));

vi.mock("./writeApi", async (orig) => ({
  ...(await orig<typeof import("./writeApi")>()),
  searchRepository: searchRepositoryMock,
}));

import SubAgentProposal from "./SubAgentProposal";

beforeEach(() => {
  searchRepositoryMock.mockReset().mockResolvedValue([
    {
      node_id: " node-1 ",
      label: "  Corroborating block  ",
      node_type: "claim",
      source_tier: "2",
      document_id: "doc-1",
      document_title: "  Source document  ",
      score: 1,
    },
    {
      node_id: "",
      label: "Invisible support",
      node_type: "claim",
      source_tier: 1,
      document_id: null,
      document_title: null,
      score: 1,
    },
  ]);
  startInvestigationMock.mockReset().mockResolvedValue({
    investigation_id: " child-1 ",
    status: "in_progress",
    start_event_id: "ev-1",
  });
});

afterEach(cleanup);

describe("SubAgentProposal", () => {
  it("sanitizes search hits before showing support", async () => {
    render(
      <SubAgentProposal
        claimText="The claim"
        parentInvestigationId="inv-parent"
        onAccept={vi.fn()}
        onReject={vi.fn()}
      />,
    );

    expect(await screen.findByText(/Source document/)).toBeTruthy();
    expect(screen.getByText(/Corroborating block/)).toBeTruthy();
    expect(screen.queryByText("Invisible support")).toBeNull();
  });

  it("trims accepted child investigation ids", async () => {
    const onAccept = vi.fn();
    render(
      <SubAgentProposal
        claimText="The claim"
        parentInvestigationId="inv-parent"
        onAccept={onAccept}
        onReject={vi.fn()}
      />,
    );

    await userEvent.click(await screen.findByRole("button", { name: /accept/i }));

    await waitFor(() => expect(onAccept).toHaveBeenCalledWith("child-1"));
    expect(startInvestigationMock).toHaveBeenCalledWith(
      expect.objectContaining({
        question: "Strengthen: The claim",
        spawn_context: "The claim",
        parent_investigation_id: "inv-parent",
      }),
    );
  });

  it("surfaces malformed child investigation ids instead of accepting", async () => {
    startInvestigationMock.mockResolvedValue({
      investigation_id: " ",
      status: "in_progress",
      start_event_id: "ev-1",
    });
    const onAccept = vi.fn();
    render(
      <SubAgentProposal
        claimText="The claim"
        parentInvestigationId="inv-parent"
        onAccept={onAccept}
        onReject={vi.fn()}
      />,
    );

    await userEvent.click(await screen.findByRole("button", { name: /accept/i }));

    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(screen.getByRole("alert").textContent ?? "").toMatch(/did not return an id/i);
    expect(onAccept).not.toHaveBeenCalled();
  });
});
