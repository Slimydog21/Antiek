/**
 * motion.guard.test.ts — the anti-noise guard (U-05 M4).
 *
 * Motion lives in defined slots: the base interactions (the Tailwind
 * `transition-*` utilities routed through the motion tokens — see
 * src/design/motion.ts), the four signature beats (src/shared/delight),
 * and Werner's four pose keyframes (src/brand/werner/animated/animations.css,
 * U-02). The sprawl this guards against is a NEW raw `@keyframes` — a
 * fresh, untokenised motion vocabulary — declared somewhere outside those
 * homes. That's the mechanical signal a contributor is improvising motion
 * instead of reaching for the system.
 *
 * Why @keyframes specifically (intellectual honesty about the limit): a
 * keyframe block is the one motion construct that's both unambiguous to
 * detect statically and almost always a new vocabulary rather than a base
 * interaction. Raw `transition:` declarations are NOT flagged — they're
 * everywhere as legitimate Tailwind base interactions, so flagging them
 * would be noise, not signal. So this is a real but bounded guard: it
 * catches the high-signal case (a hand-rolled keyframe) and steers the
 * author to the system; it does not claim to catch every possible
 * ad-hoc transition. The README documents the slots the guard can't
 * mechanically enforce (which beat, how long) as a review checklist.
 *
 * Baselined exactly like scripts/lint_tokens.ts + src/shared/copyLint.test.ts:
 * every existing keyframe is grandfathered in a baseline json; the test
 * fails only on a NEW keyframe outside the sanctioned files, and is green
 * on the current tree. The baseline only ever shrinks.
 *
 * Re-mint deliberately (after a keyframe is removed, the count shrinks):
 *   MOTION_GUARD_UPDATE=1 npx vitest run src/design/motion/motion.guard.test.ts
 * Never set it to silence a regression.
 */
import { describe, expect, it } from "vitest";
import {
  readFileSync,
  writeFileSync,
  readdirSync,
  statSync,
  existsSync,
} from "node:fs";
import { join, relative } from "node:path";

const HERE = __dirname; // apps/reading/src/design/motion
const SRC = join(HERE, "..", ".."); // apps/reading/src
const APP = join(SRC, ".."); // apps/reading
const BASELINE = join(HERE, "motion_guard_baseline.json");

/**
 * Files allowed to declare raw @keyframes — the motion system's own homes.
 * Werner's pose keyframes (U-02) and the motion-system files. A NEW
 * keyframe anywhere else is the sprawl signal.
 */
const SANCTIONED = new Set<string>([
  // The brain mascot's living presence (blink overlay + breathing sway) —
  // the U-02 slot's brain edition; same kind of dedicated motion home as
  // animations.css. See brand/BrainMascot.tsx + brand/README.md.
  "src/brand/mascot-brain/brainMascot.css",
  "src/brand/werner/animated/animations.css",
  // Semantic reactions are a single, token-driven Werner motion home. Keep
  // their seven one-shot beats consolidated here instead of baselining them
  // as unrelated ad-hoc motion.
  "src/brand/werner/reactions/semantic-reactions.css",
  "src/design/motion.css",
  "src/design/motion.ts",
  // The reactive Werner mascot's waddle/bump poses (AMS SPR-05/10) — a
  // dedicated motion home, the same kind of slot as animations.css above.
  "src/werner/waddle.css",
  // The living-mountainscape scene's consolidated keyframes (AMS SPR-04):
  // krea crossfade + the scenery penguin's journey/bob. One motion home, not
  // sprawled inline across the layer components.
  "src/scene/scene.css",
]);

/** `@keyframes <name>` — the high-signal "new motion vocabulary" marker. */
const KEYFRAMES = /@keyframes\s+([A-Za-z_][\w-]*)/g;

function walk(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    if (name === "node_modules" || name === "generated") continue;
    const p = join(dir, name);
    const st = statSync(p);
    if (st.isDirectory()) walk(p, out);
    // Tests + stories describe motion in prose ("@keyframes …"); they
    // don't ship it. Skip them so the guard reads declarations, not docs.
    else if (/\.(ts|tsx|css)$/.test(name) && !/\.(test|stories)\./.test(name)) {
      out.push(p);
    }
  }
  return out;
}

/** Every keyframe declaration outside the sanctioned homes, as baseline keys. */
function collect(): string[] {
  const found: string[] = [];
  for (const file of walk(SRC)) {
    const rel = relative(APP, file).replace(/\\/g, "/");
    if (SANCTIONED.has(rel)) continue;
    const lines = readFileSync(file, "utf8").split("\n");
    lines.forEach((line, i) => {
      KEYFRAMES.lastIndex = 0;
      let m: RegExpExecArray | null;
      while ((m = KEYFRAMES.exec(line)) !== null) {
        found.push(`${rel}:${i + 1}\t${m[1]}`);
        if (m.index === KEYFRAMES.lastIndex) KEYFRAMES.lastIndex++;
      }
    });
  }
  return found.sort();
}

describe("motion anti-noise guard — no NEW ad-hoc @keyframes (U-05 M4)", () => {
  it("introduces no keyframe outside the motion system beyond the baseline", () => {
    const current = collect();

    if (process.env.MOTION_GUARD_UPDATE) {
      writeFileSync(BASELINE, JSON.stringify(current, null, 2) + "\n");
      // eslint-disable-next-line no-console
      console.log(
        `motion-guard: baseline re-minted — ${current.length} grandfathered keyframes.`,
      );
      return;
    }

    const baseline: string[] = existsSync(BASELINE)
      ? (JSON.parse(readFileSync(BASELINE, "utf8")) as string[])
      : [];
    const baseSet = new Set(baseline);
    const fresh = current.filter((e) => !baseSet.has(e));

    if (fresh.length) {
      const detail = fresh
        .map((e) => {
          const [loc, name] = e.split("\t");
          return `  ${loc}   →   @keyframes ${name}`;
        })
        .join("\n");
      throw new Error(
        `motion-guard FAILED: ${fresh.length} NEW @keyframes outside the motion system.\n` +
          `Motion belongs in defined slots — base interactions via the tokens\n` +
          `(src/design/motion.ts), the signature beats (src/shared/delight), or\n` +
          `Werner's poses (src/brand/werner/animated/animations.css). A hand-rolled\n` +
          `keyframe is the sprawl this guards against. New keyframes:\n${detail}\n\n` +
          `See src/design/motion/README.md for the allowed slots. If this is a\n` +
          `genuine new motion-system home, add it to SANCTIONED here — never\n` +
          `MOTION_GUARD_UPDATE to silence a regression.\n`,
      );
    }

    // Green: log the grandfathered count the way token-lint / copy-lint do.
    // eslint-disable-next-line no-console
    console.log(
      `motion-guard OK — no new ad-hoc keyframes (${current.length} grandfathered; baseline has ${baseline.length}).`,
    );
    expect(fresh).toEqual([]);
  });
});
