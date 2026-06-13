/**
 * token-parity — the "lived feel == designed feel" guard (CFEEL-FIX-1).
 *
 * Why this exists: Antiek has THREE sibling sources of truth for the sun
 * accent/shadow family — `src/design/tokens.ts` (the canonical TS), its CSS
 * sibling `src/design/tokens.css` (the `var(--…)`-driven runtime), and
 * `tailwind.config.js` (the `text-sun-deep` / `bg-sun-glow` / `*-night`
 * utilities ~45 components consume). When AMS-SPR-09 re-toned tokens.css /
 * tokens.ts to the weathered values but tailwind.config.js kept the OLD loud
 * hexes, the two silently disagreed: components rendered the loud values on
 * screen ("lived feel ≠ designed feel") with no CI guard. This guard makes the
 * disagreement impossible to ship.
 *
 * THE PARITY RULE (which families, and why each is checked the way it is):
 *
 *   ACCENT family — `sun-deep`, `sun-glow`:
 *     tokens.css owns the value (day `:root` + the night media block). The
 *     Tailwind keys are consumed in BOTH themes (text-sun-deep dark:text-sun,
 *     and several un-overridden text-sun-deep that render in night too), so the
 *     ONLY correct, drift-proof Tailwind value is the CSS var itself —
 *     `var(--sun-deep)` / `var(--sun-glow)` — which cascades to the right token
 *     per theme. The guard therefore asserts the Tailwind side REFERENCES the
 *     var (not any hardcoded hex). It additionally asserts tokens.css still
 *     carries the re-toned weathered values (the source of truth itself hasn't
 *     regressed back to the loud hexes).
 *
 *   SHADOW family — `z1-night`, `z2-night`, `z3-night`, `lift-night`:
 *     Every consumer applies these only behind `dark:`, so they fire only in
 *     the night subtree where `--sun-deep` cascades to its night value. The
 *     correct, drift-proof Tailwind cast is `var(--sun-deep)`, byte-identical
 *     to how tokens.css `--shadow-z*` read it. The guard asserts the cast
 *     colour of each *-night boxShadow REFERENCES `var(--sun-deep)`.
 *
 * If a future dev re-hardcodes any of these to a hex (the original drift), or
 * lets tokens.css regress off the weathered values, this guard EXITS NON-ZERO.
 *
 * Out of scope (other FEEL-FIX passes own these): spacing/density, type scale,
 * z-index, modal enter wiring. Brand constant `--sun` (#F5DF24) is intentionally
 * a static hex in both files and is NOT a parity target.
 *
 *   npx tsx scripts/check_token_parity.ts   # exit 1 on any drift
 */
import { readFileSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url)); // apps/reading/scripts
const ROOT = join(here, ".."); // apps/reading
const TOKENS_CSS = join(ROOT, "src/design/tokens.css");
const TAILWIND = join(ROOT, "tailwind.config.js");

const css = readFileSync(TOKENS_CSS, "utf8");
const tw = readFileSync(TAILWIND, "utf8");

const failures: string[] = [];

/** The weathered values tokens.css MUST still carry (source-of-truth has not
 *  regressed back to the loud SPR-09-superseded hexes). Day `:root` block +
 *  night `@media (prefers-color-scheme: dark)` block. */
const EXPECTED_CSS = {
  daySunDeep: "#9C8636",
  daySunGlow: "#F1E08F",
  nightSunDeep: "#84722F", // == tokens.ts shadow.night cast + sun.deep.night
  nightSunGlow: "#F2DE9A",
} as const;

/** Drop `/* … *\/` comments so a commented-out declaration (e.g. a left-behind
 *  `/* --sun-deep: #XXXX; *\/` AFTER the live one) can never be matched as the
 *  "last" value. Fail-safe today (a stray comment would force a FALSE FAILURE,
 *  never a false pass) — stripped anyway so the parser reads only live CSS. */
function stripComments(src: string): string {
  return src.replace(/\/\*[\s\S]*?\*\//g, "");
}

/** Split tokens.css into its day (`:root { … }`) and night (dark media) halves
 *  so a `--sun-deep:` declaration is attributed to the right theme. */
function splitDayNight(src: string): { day: string; night: string } {
  const nightStart = src.search(/@media\s*\(prefers-color-scheme:\s*dark\)/);
  if (nightStart === -1) return { day: src, night: "" };
  return { day: src.slice(0, nightStart), night: src.slice(nightStart) };
}

/** Last live `--name: <value>;` declaration in a block (so a later override
 *  wins, matching CSS cascade). Comment-safe. Returns the trimmed value or null. */
function cssVar(block: string, name: string): string | null {
  const re = new RegExp(`--${name}\\s*:\\s*([^;]+);`, "g");
  let m: RegExpExecArray | null;
  let last: string | null = null;
  const live = stripComments(block);
  while ((m = re.exec(live)) !== null) last = m[1].trim();
  return last;
}

const { day, night } = splitDayNight(css);

// --- tokens.css source-of-truth assertions (weathered values intact) ---
const cssChecks: Array<[string, string | null, string]> = [
  ["day :root --sun-deep", cssVar(day, "sun-deep"), EXPECTED_CSS.daySunDeep],
  ["day :root --sun-glow", cssVar(day, "sun-glow"), EXPECTED_CSS.daySunGlow],
  ["night --sun-deep", cssVar(night, "sun-deep"), EXPECTED_CSS.nightSunDeep],
  ["night --sun-glow", cssVar(night, "sun-glow"), EXPECTED_CSS.nightSunGlow],
];
for (const [label, got, want] of cssChecks) {
  const norm = got?.toLowerCase() ?? null;
  if (norm !== want.toLowerCase()) {
    failures.push(
      `tokens.css ${label} = ${got ?? "(missing)"} — expected the re-toned ${want}. ` +
        `The source of truth regressed; fix tokens.css (and update EXPECTED_CSS only for a DELIBERATE re-tone).`,
    );
  }
}

// --- tailwind.config.js parity assertions (references the var, no hardcoded hex) ---

/** Extract the value string for a quoted Tailwind color key, e.g. "sun-deep". */
function twColorValue(key: string): string | null {
  const re = new RegExp(`["']${key}["']\\s*:\\s*["']([^"']+)["']`);
  const m = tw.match(re);
  return m ? m[1].trim() : null;
}

const ACCENT_KEYS = ["sun-deep", "sun-glow"] as const;
for (const key of ACCENT_KEYS) {
  const val = twColorValue(key);
  if (val === null) {
    failures.push(`tailwind.config.js colors["${key}"] not found.`);
    continue;
  }
  const expectedVar = `var(--${key})`;
  if (val !== expectedVar) {
    failures.push(
      `tailwind.config.js colors["${key}"] = "${val}" — expected "${expectedVar}". ` +
        `Accent utilities must reference the CSS var so they cascade per theme and never drift ` +
        `from tokens.css. (Re-hardcoding a hex here is the exact CFEEL-FIX-1 bug.)`,
    );
  }
}

const SHADOW_KEYS = ["z1-night", "z2-night", "z3-night", "lift-night"] as const;
for (const key of SHADOW_KEYS) {
  const val = twColorValue(key);
  if (val === null) {
    failures.push(`tailwind.config.js boxShadow["${key}"] not found.`);
    continue;
  }
  if (!val.includes("var(--sun-deep)")) {
    failures.push(
      `tailwind.config.js boxShadow["${key}"] = "${val}" — expected the cast colour to be ` +
        `var(--sun-deep) (these utilities fire only under dark:, where --sun-deep is the night value). ` +
        `A hardcoded hex (e.g. #8A7300) is the CFEEL-FIX-1 drift.`,
    );
  }
}

if (failures.length) {
  console.error(
    `\ntoken-parity FAILED: ${failures.length} sun accent/shadow drift(s) between ` +
      `tokens.css and tailwind.config.js.\n`,
  );
  for (const f of failures) console.error("  • " + f);
  console.error(
    "\nThe sun-deep/sun-glow accent + *-night shadow families must agree across " +
      "tokens.css and tailwind.config.js, or 'lived feel' ≠ 'designed feel'. See this " +
      "file's header for the parity rule.\n",
  );
  process.exit(1);
}

console.log(
  "token-parity OK — sun accent (sun-deep/sun-glow) + *-night shadows agree: " +
    "tailwind.config.js references the CSS vars; tokens.css carries the re-toned " +
    `weathered values (day ${EXPECTED_CSS.daySunDeep}/${EXPECTED_CSS.daySunGlow}, ` +
    `night ${EXPECTED_CSS.nightSunDeep}/${EXPECTED_CSS.nightSunGlow}).`,
);
