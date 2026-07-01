import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import type { Claim } from "../generated/types";
import ClaimInspectorPanel from "./ClaimInspectorPanel";

afterEach(() => cleanup());

describe("ClaimInspectorPanel", () => {
  const claim: Claim = {
    claim_id: "claim-1",
    text: "The source supports the central claim.",
    confidence: "high",
    attribution_region_ids: ["region-1"],
  };

  it("renders the full claim card when workspace props include the claim payload", () => {
    render(
      <ClaimInspectorPanel
        claim={claim}
        claimId={claim.claim_id}
        investigationId="inv-1"
        documentId="doc-1"
      />,
    );

    expect(screen.getByText("The source supports the central claim.")).toBeTruthy();
    expect(screen.getByText("challenge this claim")).toBeTruthy();
  });

  it("does not crash when a legacy panel only has a claim id", () => {
    render(<ClaimInspectorPanel claimId="claim-legacy" investigationId="inv-1" />);

    expect(screen.getByText("Claim details are not loaded here.")).toBeTruthy();
    expect(screen.getByText("claim_id: claim-legacy")).toBeTruthy();
  });
});
