import { describe, expect, it } from "vitest";
import { collectiveContinueUnitReadiness } from "./collectiveContinueUnitReadiness";

describe("collectiveContinueUnitReadiness (aul)", () => {
  it("is not ready when prompt empty", () => {
    const r = collectiveContinueUnitReadiness({});
    expect(r.unit_continue_ready).toBe(false);
    expect(r.seamless_unit_continue).toBe(false);
    expect(r.l6_live_multiagent).toBe("deferred");
    expect(r.html_first).toBe(true);
    expect(r.never_pdf_view).toBe(true);
  });

  it("is ready when prompt present and seamless with id + parent", () => {
    const r = collectiveContinueUnitReadiness({
      prompt_block: "## Cohesive unit\n- claim A",
      collective_id: "col_1",
      parent_asset_id: "paper",
      spawn_count: 3,
    });
    expect(r.unit_continue_ready).toBe(true);
    expect(r.seamless_unit_continue).toBe(true);
    expect(r.spawn_count).toBe(3);
    expect(r.open_title_float).toMatch(/never PDF/i);
    expect(r.open_title_full).toMatch(/L6/i);
  });

  it("counts spawn_ids when spawn_count omitted", () => {
    const r = collectiveContinueUnitReadiness({
      prompt_block: "x",
      spawn_ids: ["a", "b", ""],
    });
    expect(r.spawn_count).toBe(2);
    expect(r.unit_continue_ready).toBe(true);
    expect(r.seamless_unit_continue).toBe(false);
  });
});
