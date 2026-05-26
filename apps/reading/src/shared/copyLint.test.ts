/**
 * copyLint.test.ts — the no-jargon guard (U-04 M4).
 *
 * The mechanical half of the language rule (language.ts is the data half).
 * It scans user-facing component source for the banned substrate patterns and
 * fails only on NEW occurrences beyond a grandfathered baseline — exactly the
 * model of scripts/lint_tokens.ts (raw-hex lint). The existing jargon leaks
 * (Wrestle's `inv-` id + `investigation:` label, Speak's `subject_status` /
 * `publish_intent` enums, Write's `block_id`, the chunk-count labels) are the
 * owning products' to fix; they live in the baseline so this lint is green on
 * the current tree and stops the NEXT leak rather than demanding a big-bang
 * cleanup first.
 *
 * Re-mint the baseline deliberately (after a product fixes a leak, the count
 * shrinks):  COPY_LINT_UPDATE=1 npx vitest run src/shared/copyLint.test.ts
 * Never set it to silence a regression — the baseline only ever shrinks.
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

import { BANNED_PATTERNS } from "./language";

const ROOT = join(__dirname, ".."); // apps/reading/src
const APP = join(ROOT, ".."); // apps/reading
const BASELINE = join(__dirname, "copy_lint_baseline.json");

/** User-facing surface roots — where rendered copy lives. */
const SCAN_DIRS = ["modes", "shell", "components"].map((d) => join(ROOT, d));

/** A leak is `relpath:lineno\t<rule>\t<matched>`. Sortable, stable, diffable. */
function walk(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    if (name === "node_modules" || name === "generated") continue;
    const p = join(dir, name);
    const st = statSync(p);
    if (st.isDirectory()) {
      walk(p, out);
    } else if (
      /\.(ts|tsx)$/.test(name) &&
      !/\.test\.|\.stories\./.test(name)
    ) {
      out.push(p);
    }
  }
  return out;
}

/** Every banned-pattern hit across the user-facing surface, as baseline keys. */
function collect(): string[] {
  const found: string[] = [];
  for (const dir of SCAN_DIRS) {
    if (!existsSync(dir)) continue;
    for (const file of walk(dir)) {
      const rel = relative(APP, file).replace(/\\/g, "/");
      const lines = readFileSync(file, "utf8").split("\n");
      lines.forEach((line, i) => {
        for (const rule of BANNED_PATTERNS) {
          // Fresh lastIndex per line — the patterns are global for counting.
          rule.pattern.lastIndex = 0;
          let m: RegExpExecArray | null;
          while ((m = rule.pattern.exec(line)) !== null) {
            found.push(`${rel}:${i + 1}\t${rule.id}\t${m[0].toLowerCase()}`);
            if (m.index === rule.pattern.lastIndex) rule.pattern.lastIndex++;
          }
        }
      });
    }
  }
  return found.sort();
}

describe("copy-lint — no NEW substrate jargon in user-facing copy (U-04 M4)", () => {
  it("introduces no banned pattern beyond the grandfathered baseline", () => {
    const current = collect();

    if (process.env.COPY_LINT_UPDATE) {
      writeFileSync(BASELINE, JSON.stringify(current, null, 2) + "\n");
      // eslint-disable-next-line no-console
      console.log(`copy-lint: baseline re-minted — ${current.length} grandfathered leaks.`);
      return;
    }

    const baseline: string[] = existsSync(BASELINE)
      ? (JSON.parse(readFileSync(BASELINE, "utf8")) as string[])
      : [];
    const baseSet = new Set(baseline);
    const fresh = current.filter((e) => !baseSet.has(e));

    if (fresh.length) {
      const byRule = new Map(BANNED_PATTERNS.map((r) => [r.id, r]));
      const detail = fresh
        .map((e) => {
          const [loc, ruleId, match] = e.split("\t");
          const rule = byRule.get(ruleId);
          return (
            `  ${loc}\n` +
            `    found:   ${match}  (${rule?.description ?? ruleId})\n` +
            `    use:     ${rule?.replacement ?? "see src/shared/language.ts GLOSSARY"}`
          );
        })
        .join("\n");
      throw new Error(
        `copy-lint FAILED: ${fresh.length} NEW substrate string(s) in user-facing copy.\n` +
          `Substrate nouns are correct in code, wrong in front of a user. Translate at the\n` +
          `UI edge using src/shared/language.ts. New leaks:\n${detail}\n\n` +
          `If a product is FIXING an existing leak (the baseline shrinks), re-mint:\n` +
          `  COPY_LINT_UPDATE=1 npx vitest run src/shared/copyLint.test.ts\n`,
      );
    }

    // Green: log the grandfathered count the way token-lint does.
    // eslint-disable-next-line no-console
    console.log(
      `copy-lint OK — no new substrate jargon (${current.length} grandfathered; baseline has ${baseline.length}).`,
    );
    expect(fresh).toEqual([]);
  });
});
