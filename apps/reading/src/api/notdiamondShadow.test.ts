import { describe, expect, it } from "vitest";
import {
  assertNotProductionAuthority,
  NotDiamondShadowError,
  recordShadowComparison,
} from "./notdiamondShadow";

describe("recordShadowComparison", () => {
  it("defaults kill switch off and discards ND reco", () => {
    const rec = recordShadowComparison({
      local_model_id: "m1",
      nd_recommended_model_id: "nd-would-say",
    });
    expect(rec.enabled).toBe(false);
    expect(rec.authority).toBe("shadow");
    expect(rec.nd_recommended_model_id).toBeNull();
    expect(rec.agreement).toBeNull();
  });

  it("records agreement when enabled", () => {
    const rec = recordShadowComparison({
      local_model_id: "m1",
      nd_recommended_model_id: "m1",
      enabled: true,
    });
    expect(rec.agreement).toBe(true);
    expect(rec.authority).toBe("shadow");
  });

  it("records disagreement", () => {
    const rec = recordShadowComparison({
      local_model_id: "m1",
      nd_recommended_model_id: "m2",
      enabled: true,
    });
    expect(rec.agreement).toBe(false);
  });

  it("rejects empty local and production authority claims", () => {
    expect(() =>
      recordShadowComparison({ local_model_id: "  " }),
    ).toThrow(NotDiamondShadowError);
    expect(() =>
      assertNotProductionAuthority({ authority: "production" }),
    ).toThrow(/shadow/);
    assertNotProductionAuthority(
      recordShadowComparison({ local_model_id: "m1", enabled: true, nd_recommended_model_id: "m1" }),
    );
  });
});
