/**
 * densify: invent polish wave honesty — Flipbook note + densify summary claim
 * the latest complete invent polish wave, and every product invent has a
 * refedit+candidate provenance pair for that wave letter.
 *
 * Prevents invent thrash from claiming "wave complete" without artifacts.
 */
import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const DOCS = join(process.cwd(), "docs/design-assets");
const SESSION = join(DOCS, "session-20260716");
const SUMMARY = join(DOCS, "BRANDING-DENSIFY-SUMMARY.md");
const FLIPBOOK = join(DOCS, "FLIPBOOK-FEEL-HTML-STREAMING-NOTE.md");
const POSES = join(process.cwd(), "src/brand/werner/poses/session");

/** Latest complete invent polish wave letter (advance with each wave). */
const WAVE = "v3n";

/** 18 product invent doors (matches inventProductInventory.densify). */
const PRODUCT_STEMS = [
  "werner_crt_living_tv",
  "werner_igloo_minigame_trio",
  "werner_paperclip_zombies_arcade",
  "werner_igloo_ice_arcade_cursor",
  "werner_clam_catcher_cursor",
  "werner_crt_igloo_cursor_tv",
  "werner_living_tv",
  "werner_thought_partner_desk",
  "werner_cascade_plan",
  "werner_midnight_oil_swarm",
  "werner_arxiv_substack_dens",
  "werner_html_book_float",
  "werner_collective_merge",
  "werner_book_marketplace_port",
  "werner_float_research_merge",
  "werner_knowledge_twin_cursor",
  "werner_antiek_bench_celebrate",
  "werner_model_decision_tree",
] as const;

describe("invent polish wave honesty densify", () => {
  it(`summary + Flipbook note claim invent polish ${WAVE} wave complete`, () => {
    const summary = readFileSync(SUMMARY, "utf8");
    const flipbook = readFileSync(FLIPBOOK, "utf8");
    expect(summary).toMatch(
      new RegExp(`Invent polish ${WAVE} wave complete`, "i"),
    );
    expect(flipbook).toMatch(new RegExp(`Invent polish ${WAVE}`, "i"));
    expect(flipbook).toMatch(/Pure Flipbook sole UI remains \*\*NO-GO\*\*/i);
  });

  it(`all 18 product invents have ${WAVE} refedit + candidate + product webp`, () => {
    const missing: string[] = [];
    for (const stem of PRODUCT_STEMS) {
      const refedit = join(SESSION, `${stem}_refedit_${WAVE}.jpg`);
      const cand = join(SESSION, `${stem}_session_candidate_${WAVE}.webp`);
      const prod = join(POSES, `${stem}_session_v1.webp`);
      if (!existsSync(refedit)) missing.push(`refedit:${stem}`);
      if (!existsSync(cand)) missing.push(`candidate:${stem}`);
      if (!existsSync(prod)) missing.push(`product:${stem}`);
      else if (statSync(prod).size < 10_000) missing.push(`tiny:${stem}`);
    }
    expect(missing, `missing/tiny: ${missing.join(", ")}`).toEqual([]);
  });

  it(`session-20260716 has at least 18 ${WAVE} candidates (no silent truncation)`, () => {
    const files = readdirSync(SESSION);
    const cands = files.filter((f) =>
      f.endsWith(`_session_candidate_${WAVE}.webp`),
    );
    expect(cands.length).toBeGreaterThanOrEqual(18);
  });
});
