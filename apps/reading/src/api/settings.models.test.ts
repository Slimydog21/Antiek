import { describe, expect, it } from "vitest";

import { validateModelsResponse } from "./settings";

const unavailable = (research_tier: "fast" | "deep" | "wrestle") => ({
  research_tier,
  state: "unavailable",
  provider_id: null,
  model_id: null,
  candidate_rank: null,
  availability_source: "boot_registered_providers",
  reason: "no boot-ready provider",
});

const base = {
  models: [],
  count: 0,
  providers_ready: false,
  source: "test",
  cascade_targets: [unavailable("fast"), unavailable("deep"), unavailable("wrestle")],
  operator_models: [],
  authority_notes: [],
};

describe("Settings model authority validation", () => {
  it("requires exact three-tier coverage", () => {
    expect(() => validateModelsResponse({ ...base, cascade_targets: [unavailable("deep")] })).toThrow(/all research tiers/);
  });

  it("rejects a selected target without an exact route", () => {
    const targets = [...base.cascade_targets];
    targets[1] = { ...targets[1], state: "selected_for_cascade_launch", reason: "selected" };
    expect(() => validateModelsResponse({ ...base, cascade_targets: targets })).toThrow(/selected cascade target is incomplete/);
  });

  it("rejects unscoped operator registry entries", () => {
    expect(() => validateModelsResponse({
      ...base,
      operator_models: [{
        model_id: "m",
        provider_id: "p",
        state: "operator_added_unverified",
        decision_tree_selected: true,
        provider_adapter_boot_ready: true,
      }],
    })).toThrow(/invalid operator model authority/);
  });
});
