/**
 * token-parity — the "lived feel == designed feel" guard (CFEEL-FIX-1, widened
 * for the semantic layer).
 *
 * Antiek has three sibling colour sources: `src/design/tokens.ts` (TS mirror,
 * read by canvases and tests), `src/design/tokens.css` (the runtime truth) and
 * `tailwind.config.js` (the utilities ~2,800 call sites consume). When they
 * drifted, components rendered values nobody designed (the loud #B89A00 sun
 * after the SPR-09 re-tone; the night rule that 0 call sites could reach;
 * `moonlight` at 3.50:1). This guard makes that drift impossible to ship:
 *
 *   1. SEMANTIC PARITY. Every token in tokens.ts `semantic` equals the value
 *      tokens.css resolves to, per theme (var() chains followed), and every
 *      `-rgb` channel triplet equals its hex. One colour, one value.
 *   2. NIGHT FALLBACK IDENTITY. The no-JS `@media (prefers-color-scheme: dark)`
 *      block declares exactly what `:root[data-theme="dark"]` declares.
 *   3. NO LITERAL COLOURS IN TAILWIND. Every key in colors / textColor /
 *      backgroundColor / borderColor resolves to a CSS var that exists in both
 *      themes: `rgb(var(--x-rgb) / <alpha-value>)` or `var(--x)`.
 *   4. THE CONSUMED CONTRACTS the call sites rely on: `text-sun-deep` renders
 *      the brand-as-text (--sun-ink) while `border-sun-deep` stays the edge;
 *      `moonlight` renders the night --text-3; `border-charcoal-1` renders the
 *      rule; `emperor` text is --danger; the `*-night` shadows cast
 *      var(--sun-deep); the muted-ink / danger / success keys read channels.
 *   5. The weathered sun values and the AA-cleared state colours have not
 *      regressed (EXPECTED below; change only for a deliberate re-tone).
 *
 *   npx tsx scripts/check_token_parity.ts   # exit 1 on any drift
 */
import { readFileSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

import { semantic, type SemanticTokens, type Theme } from "../src/design/tokens";
import { parseTokensCss, resolveVar, toRgba, type Rgba } from "../src/design/tokenCss";

const here = dirname(fileURLToPath(import.meta.url)); // apps/reading/scripts
const ROOT = join(here, ".."); // apps/reading
const sheet = parseTokensCss(readFileSync(join(ROOT, "src/design/tokens.css"), "utf8"));
const tw = (await import(join(ROOT, "tailwind.config.js"))).default;
const ext = tw.theme.extend as Record<string, Record<string, string>>;

const failures: string[] = [];
const THEMES: Theme[] = ["light", "dark"];

const same = (a: Rgba | null, b: Rgba | null) =>
  !!a && !!b && a.r === b.r && a.g === b.g && a.b === b.b && Math.abs(a.a - b.a) < 0.005;

// ── 1. semantic parity: tokens.ts == tokens.css, per theme ────────────────
const CSS_NAME: Record<keyof SemanticTokens, string> = {
  bgPage: "--bg-page",
  bgCard: "--bg-card",
  bgInset: "--bg-inset",
  borderHairline: "--border-hairline",
  borderRule: "--border-rule",
  text1: "--text-1",
  text2: "--text-2",
  text3: "--text-3",
  sunInk: "--sun-ink",
  sunDeep: "--sun-deep",
  keycapEdge: "--keycap-edge",
  teal: "--teal",
  aurora: "--aurora",
  danger: "--danger",
  success: "--success",
  stale: "--stale",
  notRun: "--not-run",
  focus: "--focus",
  wash: "--wash",
};
for (const theme of THEMES) {
  for (const [key, cssName] of Object.entries(CSS_NAME) as Array<[keyof SemanticTokens, string]>) {
    const want = toRgba(semantic[theme][key]);
    const got = resolveVar(sheet, theme, cssName);
    if (!same(want, got === null ? null : toRgba(got))) {
      failures.push(`${theme} ${cssName}: tokens.css resolves to ${got ?? "(missing)"}, tokens.ts semantic.${theme}.${key} is ${semantic[theme][key]}.`);
    }
    const rgbName = `${cssName}-rgb`;
    if (sheet.root.has(rgbName) || sheet.night.has(rgbName)) {
      const triplet = resolveVar(sheet, theme, rgbName);
      if (!same(want, triplet === null ? null : toRgba(triplet))) {
        failures.push(`${theme} ${rgbName} = ${triplet ?? "(missing)"} does not match ${cssName} (${semantic[theme][key]}).`);
      }
    }
  }
}
// Every other *-rgb triplet must match its sibling hex too (primitives, legacy).
for (const theme of THEMES) {
  for (const name of new Set([...sheet.root.keys(), ...sheet.night.keys()])) {
    if (!name.endsWith("-rgb")) continue;
    const base = name.slice(0, -4);
    const hexVal = resolveVar(sheet, theme, base);
    if (hexVal === null) continue;
    const triplet = resolveVar(sheet, theme, name);
    if (!same(toRgba(hexVal), triplet === null ? null : toRgba(triplet))) {
      failures.push(`${theme} ${name} = ${triplet} does not match ${base} = ${hexVal}.`);
    }
  }
}

// ── 2. the no-JS fallback declares exactly the night block ────────────────
if (sheet.nightList.join("\n") !== sheet.fallbackList.join("\n")) {
  failures.push(
    `tokens.css: the @media (prefers-color-scheme: dark) fallback (${sheet.fallbackList.length} declarations) ` +
      `differs from :root[data-theme="dark"] (${sheet.nightList.length}). Keep them byte-identical.`,
  );
}

// ── 3. no literal colours in the Tailwind colour maps ─────────────────────
const CHANNEL = /^rgb\(var\((--[\w-]+)\) \/ <alpha-value>\)$/;
const PLAIN = /^var\((--[\w-]+)\)$/;
for (const map of ["colors", "textColor", "backgroundColor", "borderColor"]) {
  for (const [key, raw] of Object.entries(ext[map] ?? {})) {
    // A nested key (teal) keeps Tailwind's own palette steps; ours is DEFAULT.
    const value = typeof raw === "object" && raw !== null ? (raw as Record<string, string>).DEFAULT : raw;
    const ref = String(value).match(CHANNEL)?.[1] ?? String(value).match(PLAIN)?.[1];
    if (!ref) {
      failures.push(`tailwind.config.js ${map}["${key}"] = "${value}": a colour key must resolve to a tokens.css var, never a literal.`);
      continue;
    }
    for (const theme of THEMES) {
      if (resolveVar(sheet, theme, ref) === null) {
        failures.push(`tailwind.config.js ${map}["${key}"] reads ${ref}, which tokens.css does not define (${theme}).`);
      }
    }
  }
}

// ── 4. the consumed contracts ─────────────────────────────────────────────
const expectValue = (label: string, got: unknown, want: string) => {
  if (got !== want) failures.push(`tailwind.config.js ${label} = ${String(got)}; expected ${want}.`);
};
const ch = (v: string) => `rgb(var(--${v}-rgb) / <alpha-value>)`;
expectValue(`colors["sun-deep"]`, ext.colors["sun-deep"], ch("sun-deep"));
expectValue(`textColor["sun-deep"]`, ext.textColor["sun-deep"], ch("sun-ink"));
expectValue(`colors["sun-glow"]`, ext.colors["sun-glow"], "var(--sun-glow)");
for (const k of ["sun-light", "sun-light-soft", "sun-light-deep"]) expectValue(`colors["${k}"]`, ext.colors[k], `var(--${k})`);
expectValue(`colors["ink-soft"]`, ext.colors["ink-soft"], ch("ink-soft"));
expectValue(`colors["ink-mute"]`, ext.colors["ink-mute"], ch("ink-mute"));
expectValue(`colors.danger`, ext.colors.danger, ch("danger"));
expectValue(`colors.success`, ext.colors.success, ch("success"));
expectValue(`colors.emperor`, ext.colors.emperor, ch("danger"));
expectValue(`colors.moonlight`, ext.colors.moonlight, ch("moonlight"));
expectValue(`borderColor["charcoal-1"]`, ext.borderColor["charcoal-1"], ch("border-rule"));
expectValue(`borderColor.DEFAULT`, ext.borderColor.DEFAULT, ch("border-rule"));
expectValue(`textColor.aurora`, ext.textColor.aurora, ch("teal"));
if (resolveVar(sheet, "dark", "--moonlight") !== resolveVar(sheet, "dark", "--text-3")) {
  failures.push("tokens.css: night --text-3 must be the moonlight primitive (dark:text-moonlight == night text-3).");
}
const shadows = (tw.theme.extend.boxShadow ?? {}) as Record<string, string>;
for (const key of ["z1-night", "z2-night", "z3-night", "lift-night"]) {
  if (!String(shadows[key] ?? "").includes("var(--sun-deep)")) {
    failures.push(`tailwind.config.js boxShadow["${key}"] must cast var(--sun-deep) (got ${shadows[key]}).`);
  }
}

// ── 5. the pinned values (deliberate re-tones only) ────────────────────────
const EXPECTED: Array<[Theme, string, string]> = [
  ["light", "--sun", "#F5DF24"],
  ["dark", "--sun", "#F5DF24"],
  ["light", "--sun-deep", "#9C8636"],
  ["dark", "--sun-deep", "#84722F"],
  ["light", "--sun-glow", "#F1E08F"],
  ["dark", "--sun-glow", "#F2DE9A"],
  ["light", "--danger", "#B82E1C"],
  ["dark", "--danger", "#FF6155"],
  ["light", "--success", "#237242"],
  ["dark", "--success", "#6ECB8F"],
];
for (const [theme, name, want] of EXPECTED) {
  const got = resolveVar(sheet, theme, name);
  if (got?.toLowerCase() !== want.toLowerCase()) {
    failures.push(`tokens.css ${theme} ${name} = ${got ?? "(missing)"}; expected ${want}. Update EXPECTED only for a deliberate re-tone.`);
  }
}

if (failures.length) {
  console.error(`\ntoken-parity FAILED: ${failures.length} drift(s) between tokens.ts, tokens.css and tailwind.config.js.\n`);
  for (const f of failures) console.error("  • " + f);
  console.error("\nSee this file's header for the parity rules.\n");
  process.exit(1);
}

const keyCount = ["colors", "textColor", "backgroundColor", "borderColor"].reduce(
  (n, m) => n + Object.keys(ext[m] ?? {}).length,
  0,
);
console.log(
  `token-parity OK — ${Object.keys(CSS_NAME).length} semantic tokens agree across tokens.ts and tokens.css in both themes; ` +
    `the night fallback matches the night block (${sheet.nightList.length} declarations); ` +
    `all ${keyCount} Tailwind colour keys resolve to tokens.css vars (sun-deep day ${semantic.light.sunDeep} / night ${semantic.dark.sunDeep}; ` +
    `text-3 day ${semantic.light.text3} / night ${semantic.dark.text3}).`,
);
