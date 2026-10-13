/**
 * token-lint — the "pattern not tone" enforcer (frontend-design SPR-01).
 *
 * Functional rationale: the design system is good only if it is actually used.
 * A raw colour literal in a component is a colour that serves taste, not the
 * brand — decoration. This lint fails CI on any NEW hardcoded colour outside
 * the token source files — hex (`#123abc`) or a numeric-channel functional
 * notation (`rgb(18,52,86)`, `hsl(205 38% 34%)`) — turning "every colour is
 * a token" from a code-review hope into a mechanical guarantee. Existing
 * literals are grandfathered (a baseline) so we enforce forward without a
 * big-bang refactor; the baseline only ever shrinks.
 *
 *   npx tsx scripts/lint_tokens.ts            # check (exit 1 on new violations)
 *   npx tsx scripts/lint_tokens.ts --update   # re-mint the baseline (deliberate)
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
const BASELINE = join(here, "token_lint_baseline.json");

/** Files where a raw colour literal IS the legitimate source of truth. */
const ALLOW_FILES = new Set<string>([
  "src/design/tokens.ts",
  "src/design/tokens.css",
]);

// Match real CSS hex colours, not GitHub issue refs.
//
// The discriminator is CONTEXT, not the digit class. An earlier version
// required an a–f letter in 3/4-digit forms so `#3135` (an issue ref) would
// pass, and accepted the blind spot in its own comment: "all-numeric 3/4-digit
// colours like #333 slip through". But "contains a letter" separates neither
// colours from refs — `#333` is a colour and `#3135` is a ref, and both are
// all-numeric — so the accepted hole was exactly the most common raw greys
// (#000, #333, #888) in a gate whose whole job is "no raw hex".
//
// Issue refs live in COMMENTS; colours live in code. Stripping comment spans
// first lets the full `#[0-9a-fA-F]{3,8}` pattern run with no exceptions.
// Measured on this tree when the change landed: 29 matches before, 28 after —
// zero new catches (no all-numeric grey exists in src today, so the hole was
// latent rather than active) and one FEWER false positive, a `#ffffff` inside
// a comment in LemonTag.tsx.
const HEX = /#[0-9a-fA-F]{3,8}\b/g;

/** Functional colour notations with a NUMERIC first channel: rgb()/rgba()/
 *  hsl()/hsla(). Requiring a digit keeps the token-composing forms legal —
 *  `rgb(var(--x-rgb) / <alpha-value>)` in tailwind.config.js style, or a
 *  runtime-composed `rgba(${r},${g},${b},${a})` built FROM a token — because
 *  those reference a token instead of inventing a colour. (That is exactly
 *  how the pre-widening tree answered the hex gate: 30 rgb()/hsl() literals,
 *  the same escape hatch with a different spelling, all migrated to tokens
 *  when this pattern landed.) Named CSS colours (`red`, `rebeccapurple`)
 *  remain UNSEEN — a known residual, not sanctioned. */
const FUNC_COLOUR = /\b(?:rgb|hsl)a?\(\s*\d[^)]*\)/gi;

/** Comment spans, where issue refs live. `(?<!:)` keeps `https://` intact. */
const BLOCK_COMMENT = /\/\*[\s\S]*?\*\//g;
const LINE_COMMENT = /(?<!:)\/\/[^\n]*/g;

function stripComments(source: string): string {
  return source.replace(BLOCK_COMMENT, "").replace(LINE_COMMENT, "");
}

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

/** Sorted `relpath\t#hex` entries for every hex literal outside the allow-list. */
function collect(): string[] {
  const found: string[] = [];
  for (const file of walk(SRC)) {
    const rel = relative(ROOT, file).replace(/\\/g, "/");
    if (ALLOW_FILES.has(rel)) continue;
    const stripped = stripComments(readFileSync(file, "utf8"));
    const matches = [
      ...(stripped.match(HEX) ?? []),
      ...(stripped.match(FUNC_COLOUR) ?? []),
    ];
    // Whitespace-insensitive so `rgba(10, 10, 18, 0.82)` and
    // `rgba(10,10,18,0.82)` are the same baseline entry.
    for (const m of matches)
      found.push(`${rel}\t${m.replace(/\s+/g, "").toLowerCase()}`);
  }
  return found.sort();
}

const update = process.argv.includes("--update");
const current = collect();

if (update) {
  writeFileSync(BASELINE, JSON.stringify(current, null, 2) + "\n");
  console.log(
    `token-lint: baseline re-minted — ${current.length} grandfathered colour literals.`,
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
    `\ntoken-lint FAILED: ${fresh.length} new hardcoded colour literal(s) outside tokens.ts / tokens.css.`,
  );
  console.error(
    "Use a design token instead (Tailwind: border-sun / text-ink / bg-ice-2 …; CSS: var(--ink) …; an alpha of a token: color-mix(in srgb, var(--x) 35%, transparent); canvas: compose from a tokens.ts value).",
  );
  console.error("New violations:");
  for (const e of fresh) console.error("  " + e.replace("\t", "   →   "));
  console.error(
    "\nIf this is genuinely a new token source, add it to ALLOW_FILES; never --update to silence a regression.\n",
  );
  process.exit(1);
}
console.log(
  `token-lint OK — no new hardcoded colour literals (${current.length} grandfathered; baseline has ${baseline.length}).`,
);
