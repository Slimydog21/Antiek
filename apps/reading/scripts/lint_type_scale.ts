/**
 * type-scale lint — the "24px chrome ceiling" enforcer (CFEEL-S2 M2).
 *
 * Sibling of scripts/lint_tokens.ts (the "no raw hex" enforcer). Same shape,
 * same baseline-grandfather discipline, same exit-code contract.
 *
 * Functional rationale: PostHog's app type scale tops out at a 24px CHROME
 * ceiling — no piece of in-app chrome (buttons, labels, headers, panel titles,
 * toolbar text) renders larger than 2xl (24px). Antiek now carries the same
 * named scale (tailwind.config.js fontSize: xxs..2xl, 2xl == 24px). This lint
 * makes the ceiling mechanical: it fails CI on any NEW chrome font-size above
 * 24px expressed as one of the two SCALE-BYPASS escape hatches —
 *
 *   • a raw CSS declaration   `font-size: NNpx`   with NN > 24, or
 *   • a Tailwind arbitrary    `text-[NNpx]`        with NN > 24.
 *
 * These are exactly the hatches that route AROUND the named fontSize tokens
 * (mirroring how lint_tokens.ts targets the raw-hex hatch that routes around
 * the colour tokens). A named utility (`text-3xl` etc.) is a deliberate,
 * design-system-sanctioned size and is intentionally NOT scanned here — it is
 * not an ad-hoc escape; it is the scale. The lint is about the escape hatch.
 *
 * Known residual (accepted): the named keys ABOVE the 2xl ceiling (`text-3xl`+
 * = 30px+) still resolve via Tailwind's own defaults — no `text-3xl`+ key is
 * defined in our `fontSize` config — so chrome reaching for them bypasses the
 * ceiling unscanned. That hatch is narrow and low-traffic; governing named
 * utilities too is a deliberate follow-up, not shipped here. The high-value
 * catch (arbitrary `text-[NNpx]` / raw `font-size: NNpx`) is what routes around
 * the design system, and that is what this lint enforces.
 *
 * CONTENT vs CHROME: reading-body / document-content components are EXEMPT —
 * a book's heading is content the operator reads, not product chrome, and may
 * legitimately render large. Those subtrees are listed in ALLOW_DIRS.
 *
 * Existing violations are grandfathered in a baseline JSON (the baseline only
 * ever shrinks); the lint enforces forward without a big-bang refactor —
 * identical policy to lint_tokens.ts.
 *
 *   npx tsx scripts/lint_type_scale.ts            # check (exit 1 on new violations)
 *   npx tsx scripts/lint_type_scale.ts --update   # re-mint the baseline (deliberate)
 */
import {
  readFileSync,
  writeFileSync,
  readdirSync,
  statSync,
  existsSync,
} from "node:fs";
import { join, relative, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url)); // apps/reading/scripts
const ROOT = join(here, ".."); // apps/reading
const SRC = join(ROOT, "src");
const BASELINE = join(here, "type_scale_lint_baseline.json");

/** The chrome ceiling, in px. PostHog's app scale tops out at 2xl == 24px
 *  (tailwind.config.js fontSize["2xl"]). Anything strictly larger is a chrome
 *  ceiling violation. Reading-body CONTENT is exempt (see ALLOW_DIRS). */
const CEILING_PX = 24;

/** Reading-body / document-content subtrees. A heading INSIDE the rendered
 *  document is content the operator reads, not product chrome, so a large
 *  size there is legitimate. Path prefixes (relative to apps/reading), matched
 *  with a trailing slash so `src/modes/Reading` does not also exempt a
 *  hypothetical `src/modes/ReadingChrome`. */
const ALLOW_DIRS = [
  "src/modes/Reading/", // the document reader surface (content, not chrome)
  "src/reading-physics/", // the Physics-of-Reading augmentation/content layer
];

/** Raw CSS `font-size: NNpx` and Tailwind arbitrary `text-[NNpx]`. The two
 *  scale-bypass escape hatches. The capture group is the pixel integer. */
const RAW_FONT_SIZE = /font-size:\s*(\d+)px/g;
const ARBITRARY_TEXT = /text-\[(\d+)px\]/g;

function walk(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    if (name === "node_modules") continue;
    const p = join(dir, name);
    const st = statSync(p);
    if (st.isDirectory()) walk(p, out);
    else if (/\.(ts|tsx|css)$/.test(name)) out.push(p);
  }
  return out;
}

/** True if `rel` is under a reading-content (exempt) subtree. */
function isContent(rel: string): boolean {
  return ALLOW_DIRS.some((d) => rel.startsWith(d));
}

/** Sorted `relpath\ttext-[NNpx]` / `relpath\tfont-size:NNpx` entries for every
 *  chrome (non-content) font size strictly above the 24px ceiling. The entry
 *  records the offending token verbatim so the baseline reads like the source.*/
function collect(): string[] {
  const found: string[] = [];
  for (const file of walk(SRC)) {
    const rel = relative(ROOT, file).replace(/\\/g, "/");
    if (isContent(rel)) continue; // reading-body content is exempt
    const text = readFileSync(file, "utf8");

    let m: RegExpExecArray | null;
    RAW_FONT_SIZE.lastIndex = 0;
    while ((m = RAW_FONT_SIZE.exec(text)) !== null) {
      if (Number(m[1]) > CEILING_PX) found.push(`${rel}\tfont-size:${m[1]}px`);
    }
    ARBITRARY_TEXT.lastIndex = 0;
    while ((m = ARBITRARY_TEXT.exec(text)) !== null) {
      if (Number(m[1]) > CEILING_PX) found.push(`${rel}\ttext-[${m[1]}px]`);
    }
  }
  return found.sort();
}

const update = process.argv.includes("--update");
const current = collect();

if (update) {
  writeFileSync(BASELINE, JSON.stringify(current, null, 2) + "\n");
  console.log(
    `type-scale lint: baseline re-minted — ${current.length} grandfathered ` +
      `chrome font-size(s) above the ${CEILING_PX}px ceiling.`,
  );
  process.exit(0);
}

const baseline: string[] = existsSync(BASELINE)
  ? (JSON.parse(readFileSync(BASELINE, "utf8")) as string[])
  : [];
const baseSet = new Set(baseline);
const fresh = current.filter((e) => !baseSet.has(e));

if (fresh.length) {
  console.error(
    `\ntype-scale lint FAILED: ${fresh.length} new chrome font-size(s) above ` +
      `the ${CEILING_PX}px ceiling (PostHog's app type scale tops out at ` +
      `2xl == 24px).`,
  );
  console.error(
    "Use a named fontSize token (Tailwind: text-2xl / text-xl / text-lg …) " +
      "instead of a raw px or text-[NNpx]. If this is genuinely reading-body " +
      "CONTENT (not chrome), it belongs under a reading-content subtree — see " +
      "ALLOW_DIRS in this file.",
  );
  console.error("New violations:");
  for (const e of fresh) console.error("  " + e.replace("\t", "   →   "));
  console.error(
    "\nNever --update to silence a regression; --update is for a deliberate, " +
      "reviewed baseline change.\n",
  );
  process.exit(1);
}
console.log(
  `type-scale lint OK — no new chrome font-size above the ${CEILING_PX}px ` +
    `ceiling (${current.length} grandfathered; baseline has ${baseline.length}).`,
);
