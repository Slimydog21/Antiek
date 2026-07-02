import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

import type { Claim } from "../generated/types";
import ClaimCard from "./ClaimCard";

const postTypedEventMock = vi.hoisted(() => vi.fn());

vi.mock("../lib/api", async (orig) => ({
  ...(await orig<typeof import("../lib/api")>()),
  postTypedEvent: postTypedEventMock,
}));

const claim = (over: Partial<Claim> = {}): Claim => ({
  claim_id: "claim-1",
  text: "The source supports the claim.",
  confidence: "high",
  attribution_region_ids: ["region-1"],
  ...over,
});

beforeEach(() => {
  postTypedEventMock.mockReset();
  postTypedEventMock.mockResolvedValue({
    event_id: "evt-claim",
    action_type: "claim.challenge_raised",
  });
});

afterEach(cleanup);

describe("ClaimCard", () => {
  it("uses the first nonblank attribution region as the challenge anchor", async () => {
    render(
      <ClaimCard
        claim={claim({ attribution_region_ids: [" ", " region-1 ", "region-1"] })}
        investigationId="inv-1"
        documentId="doc-1"
      />,
    );

    expect(screen.getAllByTitle("region-1")).toHaveLength(1);
    fireEvent.click(screen.getByRole("button", { name: "challenge this claim" }));

    await waitFor(() => expect(postTypedEventMock).toHaveBeenCalledTimes(1));
    expect(postTypedEventMock.mock.calls[0][0]).toMatchObject({
      investigation_id: "inv-1",
      document_id: "doc-1",
      payload: {
        action_type: "claim.challenge_raised",
        challenged_claim_id: "claim-1",
        anchor_region_id: "region-1",
      },
    });
  });

  it("emits a null challenge anchor when no attribution region is valid", async () => {
    render(
      <ClaimCard
        claim={claim({ attribution_region_ids: [" "] })}
        investigationId="inv-1"
        documentId="doc-1"
      />,
    );

    expect(screen.queryByTitle(/open attribution region/i)).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "challenge this claim" }));

    await waitFor(() => expect(postTypedEventMock).toHaveBeenCalledTimes(1));
    expect(postTypedEventMock.mock.calls[0][0].payload.anchor_region_id).toBeNull();
  });
});
