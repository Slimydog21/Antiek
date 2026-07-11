import { describe, expect, it } from "vitest";
import {
  authorizeFinalize,
  FinalizeGateError,
  formatFinalizeReason,
} from "./draftFinalize";

describe("authorizeFinalize", () => {
  it("authorizes provisional + operator accept", () => {
    const auth = authorizeFinalize({
      draft_id: "draft-abc",
      parent_asset_id: "parent-1",
      provisional: true,
      operator_accepted: true,
      twin_ids: ["t1"],
      twin_parent_ids: ["parent-1"],
    });
    expect(auth.authorized).toBe(true);
    expect(auth.reason).toBe("ok");
    expect(auth.notes.join(" ")).toMatch(/not performed here/i);
  });

  it("denies non-provisional", () => {
    const auth = authorizeFinalize({
      draft_id: "d",
      parent_asset_id: "p",
      provisional: false,
      operator_accepted: true,
    });
    expect(auth.authorized).toBe(false);
    expect(auth.reason).toBe("not_provisional_draft");
  });

  it("denies without operator accept", () => {
    const auth = authorizeFinalize({
      draft_id: "d",
      parent_asset_id: "p",
      provisional: true,
      operator_accepted: false,
    });
    expect(auth.authorized).toBe(false);
    expect(auth.reason).toBe("operator_accept_required");
  });

  it("denies cross-parent twins", () => {
    const auth = authorizeFinalize({
      draft_id: "d",
      parent_asset_id: "p1",
      provisional: true,
      operator_accepted: true,
      twin_parent_ids: ["p1", "p2"],
    });
    expect(auth.authorized).toBe(false);
    expect(auth.reason).toBe("cross_parent_twins");
  });

  it("denies empty twin_ids when provided", () => {
    const auth = authorizeFinalize({
      draft_id: "d",
      parent_asset_id: "p",
      provisional: true,
      operator_accepted: true,
      twin_ids: [],
    });
    expect(auth.authorized).toBe(false);
    expect(auth.reason).toBe("no_twins");
  });

  it("throws on malformed ids", () => {
    expect(() =>
      authorizeFinalize({
        draft_id: "  ",
        parent_asset_id: "p",
        provisional: true,
        operator_accepted: true,
      }),
    ).toThrow(FinalizeGateError);
    expect(() =>
      authorizeFinalize({
        draft_id: "d",
        parent_asset_id: "",
        provisional: true,
        operator_accepted: true,
      }),
    ).toThrow(/parent_asset_id/);
  });

  it("formatFinalizeReason covers known codes", () => {
    expect(formatFinalizeReason("ok")).toMatch(/authorized/i);
    expect(formatFinalizeReason("operator_accept_required")).toMatch(
      /acceptance required/i,
    );
  });
});
