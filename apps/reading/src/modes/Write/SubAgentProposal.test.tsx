/**
 * SubAgentProposal invent densify — collective multi-agent merge product door.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";

import SubAgentProposal from "./SubAgentProposal";

vi.mock("./writeApi", () => ({
  searchRepository: vi.fn(async () => []),
}));

vi.mock("../../lib/api", () => ({
  startInvestigation: vi.fn(),
}));

afterEach(cleanup);

describe("SubAgentProposal invent densify", () => {
  it("product-maps collective merge invent strip (not inventory-only)", async () => {
    render(
      <SubAgentProposal
        claimText="penguins invent knowledge graphs"
        parentInvestigationId="inv-1"
        onAccept={() => {}}
        onReject={() => {}}
      />,
    );
    const invent = await screen.findByTestId("sub-agent-proposal-living-tv-art");
    expect((invent as HTMLImageElement).getAttribute("src") ?? "").toMatch(
      /werner_collective_merge_session_v1/,
    );
  });
});
