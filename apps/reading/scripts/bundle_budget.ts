/**
 * Which built file a bundle budget measures. Pure (no fs) so the choice is
 * unit-tested; scripts/check_bundle.ts does the reading and gzipping.
 */

export type BudgetEntry = {
  chunk: string;
  /** Hard gzipped ceiling in bytes. */
  maxBytes: number;
  /**
   * Measure the file `dist/index.html` loads as its module script rather
   * than matching by prefix. Lazy routes whose module file is `index.tsx`
   * emit their own `index-<hash>.js` chunks, so the prefix alone cannot say
   * which one is the entry.
   */
  entry?: boolean;
};

export type Resolution = { file: string } | { error: string };

/** Basename of the module script `index.html` loads, or null if none. */
export function entryScriptFromIndexHtml(html: string): string | null {
  for (const tag of html.match(/<script\b[^>]*>/gi) ?? []) {
    if (!/\btype\s*=\s*["']module["']/i.test(tag)) continue;
    const src = tag.match(/\bsrc\s*=\s*["']([^"']+)["']/i)?.[1];
    if (src) return src.split(/[?#]/)[0].split("/").pop() ?? null;
  }
  return null;
}

export function resolveChunk(
  budget: BudgetEntry,
  assets: readonly string[],
  indexHtml: string | null,
): Resolution {
  const matches = assets.filter(
    (f) => f.endsWith(".js") && f.startsWith(budget.chunk + "-"),
  );
  if (budget.entry) {
    const entry = indexHtml === null ? null : entryScriptFromIndexHtml(indexHtml);
    if (entry === null) {
      return {
        error:
          "dist/index.html names no module script, so the entry chunk " +
          "cannot be identified.",
      };
    }
    if (!matches.includes(entry)) {
      return {
        error:
          `dist/index.html loads ${entry}, which is not a \`${budget.chunk}-*.js\` ` +
          "file in dist/assets. Repoint this budget at the entry's new name.",
      };
    }
    return { file: entry };
  }
  if (matches.length === 0) {
    return {
      error:
        `NO CHUNK MATCHED prefix \`${budget.chunk}-\` in dist/assets. Either ` +
        "repoint this budget at the chunk's new name, or fix the build that " +
        "stopped emitting it.",
    };
  }
  if (matches.length > 1) {
    return {
      error:
        `${matches.length} chunks match prefix \`${budget.chunk}-\` ` +
        `(${matches.join(", ")}), so the budget cannot tell which one it ` +
        "governs. Give the chunk a unique name or mark the budget `entry`.",
    };
  }
  return { file: matches[0] };
}
