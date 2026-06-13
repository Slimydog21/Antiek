/**
 * sceneMotion.guard.test.ts — the scene-surface token gate (ALC SPR-06 M2).
 *
 * The sibling motion.guard.test.ts catches a NEW raw `@keyframes` (a fresh,
 * untokenised motion vocabulary). This guard catches the OTHER way scene motion
 * sprawls: a raw DURATION or EASING LITERAL (an `Nms`/`Ns` time or a `cubic-
 * bezier(...)` / `ease-*` curve) baked inline into scene ANIMATION code instead
 * of being sourced from the scene motion vocabulary (src/design/motion/
 * sceneMotion.ts) or the canonical CSS `var(--motion-*)`/`var(--ease-*)` tokens.
 *
 * WHY THIS GUARD (the M2 acceptance criterion, made mechanical): SPR-06 adds
 * drift / crossfade / parallax / state-transition motion to the scene. The AC is
 * "0 raw duration/easing literals in scene animation code (outside the token
 * file)." A grep is the honest enforcement: every scene timing must trace to a
 * named token with a rationale, so SPR-07 (Werner) and SPR-08 (shell) inherit a
 * vocabulary, not a pile of magic numbers.
 *
 * SCOPE — scene animation code only: the scene layer/hook .ts(x) files. NOT
 * scene.css (that is the sanctioned @keyframes home — its keyframe step % and
 * the reduced-motion `0.01ms` collapse are the keyframe definition itself, the
 * thing the OTHER guard governs; durations applied to those keyframes come from
 * tokens at the call site, which IS what this guard checks). NOT the token file
 * (sceneMotion.ts is where the literals legitimately live). NOT tests/stories.
 *
 * Baselined like its siblings (lint_tokens / copyLint / motion.guard): every
 * pre-existing literal is grandfathered; the test fails only on a NEW one and is
 * green on the current tree. The baseline only ever SHRINKS — SPR-06 drove it to
 * empty by tokenising PenguinJourney's last two inline literals.
 *
 * Re-mint deliberately (after a literal is tokenised, the count shrinks):
 *   SCENE_MOTION_GUARD_UPDATE=1 npx vitest run src/design/motion/sceneMotion.guard.test.ts
 * Never set it to silence a regression.
 */
import { describe, expect, it } from "vitest";
import { readFileSync, readdirSync, statSync, existsSync, writeFileSync } from "node:fs";
import { join, relative } from "node:path";

const HERE = __dirname; // apps/reading/src/design/motion
const SRC = join(HERE, "..", ".."); // apps/reading/src
const APP = join(SRC, ".."); // apps/reading
const SCENE = join(SRC, "scene"); // apps/reading/src/scene
const BASELINE = join(HERE, "scene_motion_guard_baseline.json");

/**
 * A raw motion literal in scene animation code:
 *   • a CSS time literal in an animation/transition context — `<num>ms` or
 *     `<num>s` (e.g. "38s", "200ms"); we require it to look like a time, not an
 *     arbitrary number, by the unit suffix.
 *   • a `cubic-bezier(...)` easing literal.
 *   • a Tailwind/CSS `ease-*` easing keyword used as a value (`ease-in`,
 *     `ease-out`, `ease-in-out`, `linear` inside an animation string).
 *
 * We flag the literal ONLY when it is NOT part of a `var(--…)` reference (those
 * ARE the tokens). The high-signal markers below match the literal forms; the
 * var() form contains no bare number+unit / bare cubic-bezier, so it never trips.
 */
const TIME = /\b\d+(?:\.\d+)?m?s\b/; // 38s, 0.9s, 200ms, 1ms
const CUBIC = /cubic-bezier\s*\(/;
const EASEKW = /\b(?:ease-in-out|ease-in|ease-out|ease|linear)\b/;

/** Walk the scene dir for animation-bearing source (.ts/.tsx), skipping
 *  tests/stories. CSS is governed by the @keyframes guard, not this one. */
function walk(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    if (name === "node_modules" || name === "generated") continue;
    const p = join(dir, name);
    if (statSync(p).isDirectory()) {
      walk(p, out);
    } else if (/\.(ts|tsx)$/.test(name) && !/\.(test|stories)\./.test(name)) {
      out.push(p);
    }
  }
  return out;
}

/**
 * A line is a candidate only if it is plausibly applying motion (an `animation`
 * or `transition` property/string). We then flag the raw literal forms on it,
 * EXCEPT where the value is a `var(--…)` token reference. This keeps the guard
 * high-signal: it reads animation CALL SITES, not every number in the file (the
 * clock's `64ms` comment, particle counts, etc. are not animation timings).
 */
function literalsOnLine(line: string): string[] {
  const isMotionContext = /\b(?:animation|transition)\b/.test(line);
  if (!isMotionContext) return [];
  // Strip out var(--…) references so a tokenised line is never flagged.
  const stripped = line.replace(/var\(--[\w-]+\)/g, "");
  const hits: string[] = [];
  if (TIME.test(stripped)) hits.push("time-literal");
  if (CUBIC.test(stripped)) hits.push("cubic-bezier-literal");
  if (EASEKW.test(stripped)) hits.push("ease-keyword-literal");
  return hits;
}

/** Every raw motion literal in scene animation code, as baseline keys. */
function collect(): string[] {
  const found: string[] = [];
  for (const file of walk(SCENE)) {
    const rel = relative(APP, file).replace(/\\/g, "/");
    const lines = readFileSync(file, "utf8").split("\n");
    lines.forEach((line, i) => {
      for (const kind of literalsOnLine(line)) {
        found.push(`${rel}:${i + 1}\t${kind}`);
      }
    });
  }
  return found.sort();
}

describe("scene-motion token gate — 0 raw duration/easing literals in scene animation code (SPR-06 M2)", () => {
  it("introduces no raw motion literal on a scene animation surface beyond the baseline", () => {
    const current = collect();

    if (process.env.SCENE_MOTION_GUARD_UPDATE) {
      writeFileSync(BASELINE, JSON.stringify(current, null, 2) + "\n");
      // eslint-disable-next-line no-console
      console.log(
        `scene-motion-guard: baseline re-minted — ${current.length} grandfathered literals.`,
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
          const [loc, kind] = e.split("\t");
          return `  ${loc}   →   ${kind}`;
        })
        .join("\n");
      throw new Error(
        `scene-motion-guard FAILED: ${fresh.length} NEW raw motion literal(s) in scene animation code.\n` +
          `Scene timing/easing must come from the scene motion vocabulary\n` +
          `(src/design/motion/sceneMotion.ts) or the canonical var(--motion-*)/\n` +
          `var(--ease-*) tokens — never an inline Nms/Ns / cubic-bezier / ease-*.\n` +
          `New literals:\n${detail}\n\n` +
          `Add a named, rationale-commented token to sceneMotion.ts and consume it.\n` +
          `Never SCENE_MOTION_GUARD_UPDATE to silence a regression.\n`,
      );
    }

    // eslint-disable-next-line no-console
    console.log(
      `scene-motion-guard OK — no new raw scene-motion literals (${current.length} grandfathered; baseline has ${baseline.length}).`,
    );
    expect(fresh).toEqual([]);
  });

  it("the baseline is EMPTY — SPR-06 tokenised every scene animation literal (the gate's intent)", () => {
    // The AC is "0 raw duration/easing literals in scene animation code." The
    // strongest form of the gate is a baseline of zero: every scene animation
    // call site sources its timing from a token. If this ever needs to grow,
    // that growth must be a reviewed, justified exception — not a silent UPDATE.
    const current = collect();
    expect(current).toEqual([]);
  });
});
