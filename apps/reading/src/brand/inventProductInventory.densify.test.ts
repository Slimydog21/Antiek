/**
 * densify: invent polish v2d product inventory — every product-mapped invent webp
 * exists with non-trivial size so Flipbook-feel invent reframe has real art.
 */
import { existsSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const POSES = join(process.cwd(), "src/brand/werner/poses/session");

/** Product invent doors refreshed through invent polish v2d. */
const PRODUCT_INVENT_WEBP = [
  "werner_crt_living_tv_session_v1.webp",
  "werner_igloo_minigame_trio_session_v1.webp",
  "werner_paperclip_zombies_arcade_session_v1.webp",
  "werner_igloo_ice_arcade_cursor_session_v1.webp",
  "werner_clam_catcher_cursor_session_v1.webp",
  "werner_crt_igloo_cursor_tv_session_v1.webp",
  "werner_living_tv_session_v1.webp",
  "werner_thought_partner_desk_session_v1.webp",
  "werner_cascade_plan_session_v1.webp",
  "werner_midnight_oil_swarm_session_v1.webp",
  "werner_arxiv_substack_dens_session_v1.webp",
  "werner_html_book_float_session_v1.webp",
  "werner_collective_merge_session_v1.webp",
  "werner_book_marketplace_port_session_v1.webp",
  "werner_float_research_merge_session_v1.webp",
  "werner_knowledge_twin_cursor_session_v1.webp",
  "werner_antiek_bench_celebrate_session_v1.webp",
  "werner_model_decision_tree_session_v1.webp",
] as const;

describe("invent product inventory densify", () => {
  it("all 18 invent polish v2d product invent webps exist with non-trivial size", () => {
    expect(PRODUCT_INVENT_WEBP).toHaveLength(18);
    const missing: string[] = [];
    const tiny: string[] = [];
    for (const name of PRODUCT_INVENT_WEBP) {
      const abs = join(POSES, name);
      if (!existsSync(abs)) {
        missing.push(name);
        continue;
      }
      // Real invent art is well above 10KB at q88 banner scale.
      if (statSync(abs).size < 10_000) tiny.push(name);
    }
    expect(missing, `missing: ${missing.join(", ")}`).toEqual([]);
    expect(tiny, `too small: ${tiny.join(", ")}`).toEqual([]);
  });
});
