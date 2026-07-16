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
