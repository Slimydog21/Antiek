/**
 * Session scene webp product paths — full-bleed invent must exist and be
 * non-trivial so densify surfaces never import missing invent inventory.
 */
import { readFileSync, statSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

/** UI-consumed full-bleed invent (not alpha character marks). */
const PRODUCT_SCENE_WEBPS = [
  "./poses/session/werner_living_tv_session_v1.webp",
  "./poses/session/werner_crt_living_tv_session_v1.webp",
  "./poses/session/werner_midnight_oil_session_v1.webp",
  "./poses/session/werner_igloo_arcade_session_v1.webp",
  "./poses/session/werner_thought_partner_desk_session_v1.webp",
  "./poses/session/werner_cascade_plan_session_v1.webp",
  // densify product-mapped invents (must exist so surfaces never go inventory-only)
  "./poses/session/werner_midnight_oil_swarm_session_v1.webp",
  "./poses/session/werner_html_book_float_session_v1.webp",
  "./poses/session/werner_float_research_merge_session_v1.webp",
  "./poses/session/werner_knowledge_twin_cursor_session_v1.webp",
  "./poses/session/werner_paperclip_zombies_arcade_session_v1.webp",
  "./poses/session/werner_igloo_ice_arcade_cursor_session_v1.webp",
  "./poses/session/werner_clam_catcher_cursor_session_v1.webp",
  "./poses/session/werner_antiek_bench_celebrate_session_v1.webp",
  "./poses/session/werner_crt_igloo_cursor_tv_session_v1.webp",
  "./poses/session/werner_ice_fishing_cursor_bait_session_v1.webp",
  // craft156 invent polish — collective merge / model decision / marketplace / dens
  "./poses/session/werner_collective_merge_session_v1.webp",
  "./poses/session/werner_model_decision_tree_session_v1.webp",
  "./poses/session/werner_book_marketplace_port_session_v1.webp",
  "./poses/session/werner_arxiv_substack_dens_session_v1.webp",
] as const;

describe("session scene webp product invent", () => {
  for (const rel of PRODUCT_SCENE_WEBPS) {
    it(`${rel} exists and is a real webp (>4KB, RIFF header)`, () => {
      const path = fileURLToPath(new URL(rel, import.meta.url));
      const st = statSync(path);
      expect(st.size).toBeGreaterThan(4_000);
      const head = readFileSync(path).subarray(0, 12);
      // WebP: RIFF....WEBP
      expect(head.subarray(0, 4).toString("ascii")).toBe("RIFF");
      expect(head.subarray(8, 12).toString("ascii")).toBe("WEBP");
    });
  }
});
