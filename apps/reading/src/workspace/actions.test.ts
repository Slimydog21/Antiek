import { beforeEach, describe, expect, it } from "vitest";

import type { Claim } from "../generated/types";
import { EMPTY_SNAPSHOT } from "./panel.types";
import { openClaimInspector } from "./actions";
import { useWorkspace } from "./WorkspaceStore";

beforeEach(() => {
  useWorkspace.setState({ ...EMPTY_SNAPSHOT });
});

describe("workspace actions", () => {
  it("openClaimInspector preserves the full claim payload when the caller has it", () => {
    const claim: Claim = {
      claim_id: "claim-1",
      text: "A claim with loaded text.",
      confidence: "moderate",
      attribution_region_ids: ["region-1"],
    };

    const id = openClaimInspector({
      claimId: claim.claim_id,
      claim,
      investigationId: "inv-1",
      documentId: "doc-1",
    });

    expect(id).toBe("claim:claim-1");
    expect(useWorkspace.getState().panels[id].props).toEqual({
      claim,
      claimId: "claim-1",
      investigationId: "inv-1",
      documentId: "doc-1",
    });
  });
});
