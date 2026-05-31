/**
 * verify_spec_refs — the AMS-v2 anti-fiction ref-lint (SPR-01, milestone 2).
 *
 * WHY THIS EXISTS
 * ---------------
 * AMS-v1's spec cited interfaces that never existed on `origin/main`
 * (`#scene-root`, `FloatingSurface`, `SubActionLauncher`) and was never
 * reconciled, so nine sprints built against imagination. This script is the
 * mechanical gate that would have caught that at spec-review time instead of
 * at operator-look time.
 *
 * WHAT IT DOES
 * ------------
 * Given a sprint HTML page, it extracts every concrete repo path the page cites
 * as a dependency:
 *   1. `<span class="file">…</span>` chips (the milestone "files it touches"),
 *   2. inline `<code>…</code>` references that look like a repo path.
 * For each extracted path it runs `git cat-file -e origin/main:<path>`.
 *   - A path prefixed `NEW:` / `NEW-to-build` is a DECLARED-NEW deliverable:
 *     it is reported as NEW and never fails the lint (the sprint builds it).
 *   - A bare path that resolves on `origin/main` is PASS.
 *   - A bare path that is ABSENT on `origin/main` is FAIL — this is the v1
 *     fiction class. The process exits non-zero and names every absent path.
 *
 * USAGE
 * -----
 *   tsx tools/specs/verify_spec_refs.ts <path-to-sprint.html> [more.html …]
 *   tsx tools/specs/verify_spec_refs.ts --json <sprint.html>   # machine output
 *
 * It is intentionally NOT a general HTML linter, a CI workflow, or a TS AST
 * parser (RULE: no gold-plating). It extracts paths and checks existence on
 * `origin/main`, nothing more.
 */

import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

export type RefVerdict = "PASS" | "FAIL" | "NEW" | "ADVISORY-ABSENT";

/** Where in the page the path was cited — the chips are the dependency contract. */
export type RefOrigin = "file-chip" | "inline-code";

export interface RefResult {
  /** The repo path as extracted, with any NEW:/NEW-to-build prefix stripped. */
  path: string;
  /** Whether the cite was prefixed NEW:/NEW-to-build (a declared-new deliverable). */
  declaredNew: boolean;
  /** PASS = resolves; FAIL = bare CHIP path absent (gate); NEW = declared-new;
   *  ADVISORY-ABSENT = a bare INLINE-CODE path that is absent (prose, non-failing). */
  verdict: RefVerdict;
  /** file-chip = hard dependency (can FAIL); inline-code = prose (advisory only). */
  origin: RefOrigin;
}

/**
 * A heuristic for "this <code> string is a repo path we should verify."
 * Conservative on purpose: we only verify strings that look like real source
 * paths (a known repo top-level dir + a slash), so prose like `useWindows` or
 * `bg-ice-2` or a bare filename is never falsely flagged. New top-level dirs
 * can be added here; this is the one place the path universe is defined.
 */
const REPO_DIR_PREFIXES = [
  "apps/",
  "interfaces/",
  "tools/",
  "docs/",
  "substrate/",
  "orchestration/",
  "roles/",
  "runtime/",
  "middleware/",
  "processing/",
  "acquisition/",
  "compounding/",
  "benchmarks/",
  "infrastructure/",
  "scripts/",
  "tests/",
  "specs/",
];

/** Strip a leading NEW:/NEW-to-build marker; report whether one was present. */
export function parseNewPrefix(raw: string): { path: string; declaredNew: boolean } {
  const trimmed = raw.trim();
  const m = /^(NEW(?:-to-build)?\s*:?\s*)/i.exec(trimmed);
  if (m) {
    return { path: trimmed.slice(m[0].length).trim(), declaredNew: true };
  }
  return { path: trimmed, declaredNew: false };
}

/** Decode the handful of HTML entities that appear in path-bearing chips/code. */
function decodeEntities(s: string): string {
  return s
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'");
}

/**
 * Does this decoded string look like a concrete repo PATH (vs a symbol, a
 * Tailwind class, a CSS var, or prose)? It must start with a known repo dir
 * prefix and not contain spaces / angle-brackets / template placeholders.
 */
export function looksLikeRepoPath(s: string): boolean {
  const t = s.trim();
  if (!t) return false;
  if (/[\s<>{}()`]/.test(t)) return false; // no spaces / placeholders / template <path>
  if (t.endsWith("/")) {
    // A directory chip (e.g. `components/windows/`) — still verifiable.
    return REPO_DIR_PREFIXES.some((p) => t.startsWith(p) || `${p}` === `${t.split("/")[0]}/`);
  }
  return REPO_DIR_PREFIXES.some((p) => t.startsWith(p));
}

/** One extracted citation, tagged with where it came from. */
export interface ExtractedRef {
  raw: string;
  origin: RefOrigin;
}

/**
 * Extract candidate dependency paths from a sprint HTML page, tagged by origin:
 *   - `<span class="file">…</span>` chips   → origin "file-chip" (the HARD gate;
 *      this is where a sprint DECLARES "I depend on this path", exactly the
 *      v1-fiction surface — `FloatingSurface`/`SubActionLauncher` would live here),
 *   - inline `<code>…</code>` repo paths   → origin "inline-code" (ADVISORY only;
 *      prose legitimately discusses fictions-as-warnings and not-yet-created dirs,
 *      so an absent inline path is reported but never fails the lint).
 *
 * Returns de-duplicated refs (NEW: prefix preserved). If a path appears as BOTH
 * a chip and inline code, the chip (hard) origin wins; if either cite declared
 * it NEW, the NEW framing wins.
 */
export function extractRefsFromHtml(html: string): ExtractedRef[] {
  const raw: ExtractedRef[] = [];

  // 1. .file chips — the dependency contract.
  const fileChip = /<span\s+class="file"\s*>([\s\S]*?)<\/span>/gi;
  for (let m: RegExpExecArray | null; (m = fileChip.exec(html)); ) {
    const inner = decodeEntities(m[1]).trim();
    if (inner) raw.push({ raw: inner, origin: "file-chip" });
  }

  // 2. inline <code>…</code> repo paths — advisory.
  const codeTag = /<code\s*>([\s\S]*?)<\/code>/gi;
  for (let m: RegExpExecArray | null; (m = codeTag.exec(html)); ) {
    const inner = decodeEntities(m[1]).trim();
    if (looksLikeRepoPath(inner)) raw.push({ raw: inner, origin: "inline-code" });
  }

  // De-dupe on the post-NEW-strip path. Chip origin and NEW framing both win.
  const byPath = new Map<string, ExtractedRef>();
  for (const r of raw) {
    const { path } = parseNewPrefix(r.raw);
    if (!path) continue;
    const existing = byPath.get(path);
    if (!existing) {
      byPath.set(path, r);
      continue;
    }
    const existingNew = parseNewPrefix(existing.raw).declaredNew;
    const incomingNew = parseNewPrefix(r.raw).declaredNew;
    const origin: RefOrigin =
      existing.origin === "file-chip" || r.origin === "file-chip" ? "file-chip" : "inline-code";
    // Keep a NEW-marked raw if either declared it new.
    const winnerRaw = incomingNew && !existingNew ? r.raw : existing.raw;
    byPath.set(path, { raw: winnerRaw, origin });
  }
  return [...byPath.values()];
}

/** Back-compat: just the raw path strings (chip + inline), NEW: preserved. */
export function extractPathsFromHtml(html: string): string[] {
  return extractRefsFromHtml(html).map((r) => r.raw);
}

/** Resolve a single path against origin/main. */
export function existsOnOriginMain(path: string, cwd: string): boolean {
  try {
    execFileSync("git", ["cat-file", "-e", `origin/main:${path}`], {
      cwd,
      stdio: ["ignore", "ignore", "ignore"],
    });
    return true;
  } catch {
    return false;
  }
}

/**
 * Lint extracted refs. The existence check is injectable for tests.
 *   - declared-new (any origin)        → NEW (never fails)
 *   - bare path that resolves          → PASS
 *   - bare CHIP path absent            → FAIL (sets the exit code — the gate)
 *   - bare INLINE-CODE path absent     → ADVISORY-ABSENT (reported, never fails;
 *                                         prose may discuss fictions/new dirs)
 *
 * Accepts either tagged `ExtractedRef[]` or, for convenience in tests, bare
 * strings (treated as file-chip origin, i.e. the strict gate).
 */
export function lintRefs(
  refs: (ExtractedRef | string)[],
  resolver: (path: string) => boolean,
): RefResult[] {
  return refs.map((r) => {
    const ref: ExtractedRef = typeof r === "string" ? { raw: r, origin: "file-chip" } : r;
    const { path, declaredNew } = parseNewPrefix(ref.raw);
    if (declaredNew) {
      return { path, declaredNew: true, verdict: "NEW" as const, origin: ref.origin };
    }
    const exists = resolver(path);
    const verdict: RefVerdict = exists
      ? "PASS"
      : ref.origin === "file-chip"
        ? "FAIL"
        : "ADVISORY-ABSENT";
    return { path, declaredNew: false, verdict, origin: ref.origin };
  });
}

const MARK: Record<RefVerdict, string> = {
  PASS: "PASS",
  NEW: "NEW ",
  FAIL: "FAIL",
  "ADVISORY-ABSENT": "ADVZ",
};

/** Render the per-path PASS/FAIL/NEW/advisory table as text. */
export function formatTable(results: RefResult[]): string {
  const width = Math.max(4, ...results.map((r) => r.path.length));
  const lines = results.map(
    (r) =>
      `  [${MARK[r.verdict]}] ${r.path.padEnd(width)} ${r.origin === "inline-code" ? "(prose)" : ""}`.trimEnd(),
  );
  const n = (v: RefVerdict) => results.filter((r) => r.verdict === v).length;
  lines.push(
    `  ── ${results.length} paths · ${n("PASS")} PASS · ${n("NEW")} declared-new · ${n("ADVISORY-ABSENT")} prose-absent · ${n("FAIL")} FAIL ──`,
  );
  return lines.join("\n");
}

export interface LintFileReport {
  file: string;
  results: RefResult[];
  failed: boolean;
}

/** Lint one HTML file against origin/main. Only chip-origin FAILs gate. */
export function lintHtmlFile(file: string, cwd: string): LintFileReport {
  const html = readFileSync(file, "utf8");
  const refs = extractRefsFromHtml(html);
  const results = lintRefs(refs, (p) => existsOnOriginMain(p, cwd));
  return { file, results, failed: results.some((r) => r.verdict === "FAIL") };
}

/** Find the repo root (the dir containing .git) starting from cwd, walking up. */
function findRepoRoot(start: string): string {
  try {
    return execFileSync("git", ["rev-parse", "--show-toplevel"], {
      cwd: start,
      stdio: ["ignore", "pipe", "ignore"],
    })
      .toString()
      .trim();
  } catch {
    return start;
  }
}

function main(argv: string[]): number {
  const args = argv.slice(2);
  const json = args.includes("--json");
  const files = args.filter((a) => !a.startsWith("--"));
  if (files.length === 0) {
    console.error(
      "usage: tsx tools/specs/verify_spec_refs.ts [--json] <sprint.html> [more.html …]",
    );
    return 2;
  }
  const cwd = findRepoRoot(process.cwd());
  const reports = files.map((f) => lintHtmlFile(f, cwd));

  if (json) {
    console.log(JSON.stringify(reports, null, 2));
  } else {
    for (const rep of reports) {
      console.log(`\nverify_spec_refs · ${rep.file}`);
      console.log(formatTable(rep.results));
      const absent = rep.results.filter((r) => r.verdict === "FAIL");
      if (absent.length) {
        console.log(
          "\n  FICTION DETECTED — these DEPENDENCY (.file chip) paths are ABSENT on origin/main:",
        );
        for (const a of absent) {
          console.log(`    ✗ ${a.path}  (cite it as NEW: <path> if it is a new deliverable)`);
        }
      }
      const advisory = rep.results.filter((r) => r.verdict === "ADVISORY-ABSENT");
      if (advisory.length) {
        console.log(
          "\n  advisory — inline-prose paths absent on origin/main (NOT a failure; prose may name fictions/new dirs):",
        );
        for (const a of advisory) console.log(`    · ${a.path}`);
      }
    }
  }
  return reports.some((r) => r.failed) ? 1 : 0;
}

// Run only when invoked directly (so the test file can import the pure fns).
const isDirect = process.argv[1] === fileURLToPath(import.meta.url);
if (isDirect) {
  process.exit(main(process.argv));
}
