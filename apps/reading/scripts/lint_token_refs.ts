/**
 * token-refs — the referenced-token-resolution guard (Q1).
 *
 * Functional rationale: ~630 call sites referenced `text-ink-soft` /
 * `text-ink-mute` / `text-danger` / `border-danger` / `bg-danger/10` for
 * months while those token families were defined NOWHERE (not tokens.ts, not
 * tokens.css, not tailwind.config.js). Tailwind emitted nothing and the whole
 * muted-text hierarchy + Multimedia's danger boxes silently rendered
 * unstyled — a class of bug invisible to the hex lint (lint_tokens.ts), which
 * only catches raw literals. This guard catches the inverse: a utility that
 * NAMES a design-token family but resolves to nothing.
 *
 * THE RULE. Scan every class token of the form
 * (text|bg|border|ring)-<name> in src (ts/tsx/css; variants stripped,
 * /opacity modifiers and arbitrary values skipped). If <name> looks like a DESIGN-TOKEN reference —
 * i.e. it equals or is a dashed extension of a family the design system owns
 * (a custom color key from tailwind.config.js, or a colour var from
 * tokens.css) — then it MUST resolve in the fully-resolved Tailwind theme
 * (defaults + our extend). Unresolvable → exit 1. Tailwind's default palette
 * (text-slate-500 …) always resolves, and non-token words (text-to-speech,
 * border-radius) match no design root, so both stay out of scope — the guard
 * is deliberately scoped to the design-token families, not all of Tailwind.
 *
 * GRANDFATHERED: pre-existing unresolved references whose fixes are owned by
 * other queue items (see INVENTORY.md); the set only ever shrinks.
 *
 *   npx tsx scripts/lint_token_refs.ts   # exit 1 on any unresolvable token ref
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import resolveConfig from "tailwindcss/resolveConfig";

const here = dirname(fileURLToPath(import.meta.url)); // apps/reading/scripts
const ROOT = join(here, ".."); // apps/reading
const SRC = join(ROOT, "src");

// eslint-disable-next-line @typescript-eslint/no-require-imports
const userConfig = (await import(join(ROOT, "tailwind.config.js"))).default;
const resolved = resolveConfig(userConfig);

/** Flatten a nested Tailwind colour map to dash-joined keys (slate.500 → slate-500). */
function flatten(
  obj: Record<string, unknown> | undefined,
  prefix: string,
  out: Set<string>,
): Set<string> {
  for (const [k, v] of Object.entries(obj ?? {})) {
    if (v && typeof v === "object" && !Array.isArray(v)) {
      flatten(v as Record<string, unknown>, prefix ? `${prefix}-${k}` : k, out);
    } else {
      out.add(k === "DEFAULT" ? prefix : prefix ? `${prefix}-${k}` : k);
    }
  }
  return out;
}

const theme = resolved.theme as Record<string, Record<string, unknown>>;
const COLOR_SETS: Record<string, Set<string>> = {
  text: flatten(theme.textColor ?? theme.colors, "", new Set()),
  bg: flatten(theme.backgroundColor ?? theme.colors, "", new Set()),
  border: flatten(theme.borderColor ?? theme.colors, "", new Set()),
  ring: flatten(theme.ringColor ?? theme.colors, "", new Set()),
};

/** Design-token family roots: the custom colour keys this app owns, plus the
 *  colour-ish CSS vars in tokens.css (so a var with no Tailwind mirror yet —
 *  the exact Q1 bug — still counts as a token reference and fails). */
const customKeys = new Set(Object.keys(userConfig.theme?.extend?.colors ?? {}));
const NONCOLOR_VAR =
  /^(spacing|density|motion-|ease-|radius|edge$|opacity-|glass-blur|akb-|sans|mono|serif|shadow-z|sun-hl)/;
const cssVars = readFileSync(join(SRC, "design/tokens.css"), "utf8");
const roots = new Set<string>(customKeys);
for (const m of cssVars.matchAll(/--([a-z0-9-]+)\s*:/g)) {
  if (!NONCOLOR_VAR.test(m[1])) roots.add(m[1]);
}

function isTokenReference(name: string): boolean {
  for (const r of roots) {
    if (name === r || name.startsWith(`${r}-`) || r.startsWith(`${name}-`)) return true;
  }
  return false;
}

// Numbered ramps resolve through their STEM too: ice-9 / charcoal-3 are token
// references even though only ice-0…ice-4 / charcoal-1/2 exist.
for (const r of [...roots]) {
  const stem = r.replace(/-\d+$/, "");
  if (stem !== r) roots.add(stem);
}

// Non-colour utilities that share the text-/bg-/border-/ring- prefixes
// (typography scale, alignment, background geometry, border widths/sides/styles).
const fontSizeKeys = new Set(Object.keys(theme.fontSize ?? {}));
const borderWidthKeys = Object.keys(theme.borderWidth ?? {}).filter(
  (k) => k !== "DEFAULT",
);
const TEXT_NONCOLOR = new Set([
  "left", "center", "right", "justify", "start", "end",
  "ellipsis", "clip", "wrap", "nowrap", "balance", "pretty",
  ...fontSizeKeys,
]);
const BG_NONCOLOR = new Set([
  "fixed", "local", "scroll",
  "bottom", "center", "left", "left-bottom", "left-top",
  "right", "right-bottom", "right-top", "top",
  "repeat", "no-repeat", "repeat-x", "repeat-y", "repeat-round", "repeat-space",
  "auto", "cover", "contain", "none",
  "clip-border", "clip-padding", "clip-content", "clip-text",
  "origin-border", "origin-padding", "origin-content",
]);
const BORDER_NONCOLOR = new Set([
  "solid", "dashed", "dotted", "double", "hidden", "none",
  "collapse", "separate",
  ...borderWidthKeys,
]);

/** Pre-existing unresolved references owned by other queue items
 *  (INVENTORY.md). Grandfathered so the guard can enforce FORWARD without a
 *  big-bang refactor; this set only ever shrinks. Never add to it to silence
 *  a NEW reference — define the token instead. */
const GRANDFATHERED = new Set([
  "bg-card", // ResearchLensCursor.stories + mascot stories — card alias mirror; Q13 lint hardening
  "bg-card-soft", // ResearchLensCursor.stories + mascot stories — same
]);

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

const TOKEN = /[A-Za-z0-9_!:/-]+/g;
const violations = new Map<string, string>(); // utility → first file seen

for (const file of walk(SRC)) {
  const rel = relative(ROOT, file).replace(/\\/g, "/");
  const text = readFileSync(file, "utf8");
  for (const m of text.match(TOKEN) ?? []) {
    // Strip variant prefixes (dark:, hover:, max-md: …) and !important.
    const base = m.split(":").pop()!.replace(/^!+/, "");
    const mm = base.match(/^(text|bg|border|ring)-(.+)$/);
    if (!mm) continue;
    const [, prefix, raw] = mm;
    if (raw.includes("[")) continue; // arbitrary value: text-[#fff], bg-[var(--x)]
    const name = raw.replace(/\/\d+$/, ""); // opacity modifier: bg-danger/10
    if (/^\d+(\.\d+)?$/.test(name)) continue; // ring-2, border-2 widths
    if (prefix === "border") {
      if (/^[trblxyse]$/.test(name)) continue; // border-t sides
      // border-t-2 / border-b-edge side+width combos
      if ([...borderWidthKeys].some((w) => new RegExp(`^[trblxyse]-${w}$`).test(name)))
        continue;
    }
    if (prefix === "ring" && (name === "inset" || name.startsWith("offset-"))) continue;
    if (prefix === "bg" && name.startsWith("gradient-")) continue;
    if (prefix === "text" && TEXT_NONCOLOR.has(name)) continue;
    if (prefix === "bg" && BG_NONCOLOR.has(name)) continue;
    if (prefix === "border" && BORDER_NONCOLOR.has(name)) continue;

    const utility = `${prefix}-${name}`;
    if (GRANDFATHERED.has(utility)) continue;
    if (!COLOR_SETS[prefix].has(name) && isTokenReference(name)) {
      if (!violations.has(utility)) violations.set(utility, rel);
    }
  }
}

if (violations.size) {
  console.error(
    `\ntoken-refs FAILED: ${violations.size} utilit${
      violations.size === 1 ? "y" : "ies"
    } reference a design-token family that resolves to NOTHING.`,
  );
  console.error(
    "Tailwind emits no CSS for these — the elements render unstyled (the Q1 bug class).",
  );
  console.error("Unresolved references:");
  for (const [u, f] of [...violations.entries()].sort()) {
    console.error(`  ${u}   (first seen: ${f})`);
  }
  console.error(
    "\nFix by DEFINING the token (tokens.ts + tokens.css + tailwind.config.js —\n" +
      "check:tokens enforces the three-way sync), not by renaming call sites or\n" +
      "growing GRANDFATHERED (reserved for pre-existing refs owned by other queue items).\n",
  );
  process.exit(1);
}
console.log(
  `token-refs OK — every design-token utility reference resolves ` +
    `(${roots.size} token families; ${GRANDFATHERED.size} grandfathered, owned by Q7/Q13).`,
);
