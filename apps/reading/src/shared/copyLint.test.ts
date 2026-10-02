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

/** A leak is `relpath:lineno\t<rule>\t<matched>`. Sortable, stable, diffable.
 *
 * The LINE NUMBER is for humans only. It is deliberately NOT part of the comparison
 * key: keying on it meant any insertion above a grandfathered leak re-reported that
 * leak as new. The F7 change to modes/Write/Outline.tsx shifted a grandfathered
 * `block_id` from :235 to :243, and CI called it a regression, which cost a cycle and
 * told a lane it had broken the copy standard when it had not.
 *
 * Comparison is by `(relpath, rule, matched)` with MULTIPLICITY preserved: the first N
 * occurrences of a triple are grandfathered and any beyond are new, so a genuinely
 * duplicated leak still fails.
 *
 * ── WHAT THIS DOES *NOT* MAKE INSENSITIVE, stated because a critic found the header
 *    narrower than the behaviour ────────────────────────────────────────────────
 * The PATH is still part of the key. Moving a grandfathered leak from one file to
 * another therefore still reports it as NEW, and that is deliberate: relocating a
 * leak is a different decision about a different file, and silently following it
 * would let a leak migrate into a file with no baseline entry. It is only the LINE
 * that is ignored. A reader who takes "line-insensitive" to mean "location-
 * insensitive" will be surprised, so it is said here instead of inferred.
 *
 * A TAB inside a matched value would truncate the key and the report line, as the
 * same critic noted. No live baseline entry contains one; if the patterns ever
 * start matching across a tab, re-mint and split on the first two tabs instead.
 */

/**
 * The line-insensitive key: `relpath\t<rule>\t<matched>`.
 *
 * Splits on the LAST colon, which is correct for a POSIX `path:line` locator and
 * would be wrong for a path containing a colon. The scan roots are relative paths
 * under src/, so none does; noted rather than guarded.
 */
function keyOf(entry: string): string {
  const [loc, ruleId, matched] = entry.split("\t");
  const path = loc.slice(0, loc.lastIndexOf(":"));
  return `${path}\t${ruleId}\t${matched}`;
}

/** Count per key, so identical leaks on different lines keep their multiplicity. */
function countsByKey(entries: string[]): Map<string, number> {
  const out = new Map<string, number>();
  for (const e of entries) {
    const k = keyOf(e);
    out.set(k, (out.get(k) ?? 0) + 1);
  }
  return out;
}

/** Entries beyond what the baseline grandfathers for their key. */
function freshEntries(current: string[], baseline: string[]): string[] {
  const allowed = countsByKey(baseline);
  const used = new Map<string, number>();
  const fresh: string[] = [];
  for (const e of current) {
    const k = keyOf(e);
    const n = (used.get(k) ?? 0) + 1;
    used.set(k, n);
    if (n > (allowed.get(k) ?? 0)) fresh.push(e);
  }
  return fresh;
}
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
    const fresh = freshEntries(current, baseline);

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
