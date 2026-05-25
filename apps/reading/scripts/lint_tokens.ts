/**
 * token-lint — the "pattern not tone" enforcer (frontend-design SPR-01).
 *
 * Functional rationale: the design system is good only if it is actually used.
 * A raw hex literal in a component is a colour that serves taste, not the
 * brand — decoration. This lint fails CI on any NEW hardcoded hex outside the
 * token source files, turning "every colour is a token" from a code-review
 * hope into a mechanical guarantee. Existing literals are grandfathered (a
 * baseline) so we enforce forward without a big-bang refactor; the baseline
 * only ever shrinks.
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

/** Files where a raw hex IS the legitimate source of truth. */
const ALLOW_FILES = new Set<string>([
  "src/design/tokens.ts",
  "src/design/tokens.css",
]);

const HEX = /#[0-9a-fA-F]{3,8}\b/g;

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
    const matches = readFileSync(file, "utf8").match(HEX);
    if (matches) for (const m of matches) found.push(`${rel}\t${m.toLowerCase()}`);
  }
  return found.sort();
}

const update = process.argv.includes("--update");
const current = collect();

if (update) {
  writeFileSync(BASELINE, JSON.stringify(current, null, 2) + "\n");
  console.log(
    `token-lint: baseline re-minted — ${current.length} grandfathered hex literals.`,
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
    `\ntoken-lint FAILED: ${fresh.length} new hardcoded hex outside tokens.ts / tokens.css.`,
  );
  console.error(
    "Use a design token instead (Tailwind: border-sun / text-ink / bg-ice-2 …; CSS: var(--ink) …).",
  );
  console.error("New violations:");
  for (const e of fresh) console.error("  " + e.replace("\t", "   →   "));
  console.error(
    "\nIf this is genuinely a new token source, add it to ALLOW_FILES; never --update to silence a regression.\n",
  );
  process.exit(1);
}
console.log(
  `token-lint OK — no new hardcoded hex (${current.length} grandfathered; baseline has ${baseline.length}).`,
);
