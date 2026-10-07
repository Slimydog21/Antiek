/**
 * verify_spec_refs.test — the negative test that proves the anti-fiction gate
 * actually catches v1's class of error (SPR-01, milestone 2).
 *
 * The load-bearing assertion: feed the linter a fixture HTML page citing the
 * known v1 fiction `apps/reading/src/components/FloatingSurface.tsx` and assert
 * it (a) is reported ABSENT/FAIL and (b) flips the file's `failed` flag, i.e.
 * the process would exit non-zero. We also assert the inverse: a real path
 * passes and a `NEW:`-prefixed path is reported as declared-new (never a fail).
 *
 * Existence is checked against the repo's real `origin/main` via
 * `existsOnOriginMain`, so this is a genuine integration check, not a mock.
 */

import { execFileSync, execSync } from "node:child_process";
import { afterEach, describe, expect, it } from "vitest";

import {
  extractPathsFromHtml,
  extractRefsFromHtml,
  existsOnOriginMain,
  createOriginMainResolver,
  lintRefs,
  lintHtmlFile,
  parseNewPrefix,
  looksLikeRepoPath,
  type RefResult,
} from "./verify_spec_refs";
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const REPO_ROOT = execSync("git rev-parse --show-toplevel").toString().trim();
const resolve = (p: string) => existsOnOriginMain(p, REPO_ROOT);

// The exact v1 fiction the post-mortem named.
const FICTION = "apps/reading/src/components/FloatingSurface.tsx";
// A second v1 fiction.
const FICTION2 = "apps/reading/src/components/SubActionLauncher.tsx";
// A real path that resolves on origin/main.
const REAL = "apps/reading/src/scene/Scene.tsx";
// The load-bearing correction: the WRONG launcher path is absent…
const WRONG_LAUNCHER = "apps/reading/src/components/ProductsLauncher.tsx";
// …and the RIGHT one resolves.
const RIGHT_LAUNCHER = "apps/reading/src/shell/ProductsLauncher.tsx";

describe("parseNewPrefix", () => {
  it("strips NEW: and NEW-to-build markers and flags declaredNew", () => {
    expect(parseNewPrefix("NEW: docs/ams-v2/x.md")).toEqual({
      path: "docs/ams-v2/x.md",
      declaredNew: true,
    });
    expect(parseNewPrefix("NEW-to-build: tools/specs/verify_spec_refs.ts")).toEqual({
      path: "tools/specs/verify_spec_refs.ts",
      declaredNew: true,
    });
    expect(parseNewPrefix("apps/reading/src/scene/Scene.tsx")).toEqual({
      path: "apps/reading/src/scene/Scene.tsx",
      declaredNew: false,
    });
  });
});

describe("looksLikeRepoPath", () => {
  it("accepts repo paths and dirs, rejects symbols/classes/prose", () => {
    expect(looksLikeRepoPath("apps/reading/src/scene/Scene.tsx")).toBe(true);
    expect(looksLikeRepoPath("apps/reading/src/components/windows/")).toBe(true);
    expect(looksLikeRepoPath("interfaces/research/api/krea_routes.py")).toBe(true);
    // not paths:
    expect(looksLikeRepoPath("useWindows")).toBe(false);
    expect(looksLikeRepoPath("bg-ice-2")).toBe(false);
    expect(looksLikeRepoPath("git cat-file -e origin/main:<path>")).toBe(false);
    expect(looksLikeRepoPath("--sun")).toBe(false);
  });
});

describe("existsOnOriginMain (ground truth)", () => {
  it("the v1 fiction is ABSENT on origin/main", () => {
    expect(resolve(FICTION)).toBe(false);
    expect(resolve(FICTION2)).toBe(false);
  });
  it("a real path is PRESENT on origin/main", () => {
    expect(resolve(REAL)).toBe(true);
  });
  it("records the load-bearing launcher correction", () => {
    expect(resolve(WRONG_LAUNCHER)).toBe(false);
    expect(resolve(RIGHT_LAUNCHER)).toBe(true);
  });
});

describe("lintRefs — the gate logic", () => {
  it("FAILS a bare CHIP fiction, PASSES a real path, marks NEW as declared-new", () => {
    // bare strings are treated as file-chip origin (the strict gate).
    const results = lintRefs(
      [FICTION, REAL, `NEW: ${FICTION}`, "NEW: docs/ams-v2/verified-interfaces.md"],
      resolve,
    );
    const byPath = (p: string) => results.filter((r) => r.path === p);

    // bare chip fiction → FAIL
    const bareFiction = byPath(FICTION).find((r) => !r.declaredNew);
    expect(bareFiction?.verdict).toBe("FAIL");

    // real → PASS
    expect(byPath(REAL)[0].verdict).toBe("PASS");

    // NEW-prefixed fiction → NEW (declared-new, not a fail)
    const declaredFiction = byPath(FICTION).find((r) => r.declaredNew);
    expect(declaredFiction?.verdict).toBe("NEW");

    // a genuinely-new deliverable → NEW
    expect(byPath("docs/ams-v2/verified-interfaces.md")[0].verdict).toBe("NEW");
  });

  it("a CHIP fiction FAILS but the SAME fiction in inline prose is only ADVISORY-ABSENT", () => {
    const results = lintRefs(
      [
        { raw: FICTION, origin: "file-chip" },
        { raw: FICTION2, origin: "inline-code" },
      ],
      resolve,
    );
    expect(results.find((r) => r.path === FICTION)?.verdict).toBe("FAIL");
    expect(results.find((r) => r.path === FICTION2)?.verdict).toBe("ADVISORY-ABSENT");
    // only the chip fiction gates the exit code.
    expect(results.some((r) => r.verdict === "FAIL")).toBe(true);
  });
});

describe("extractPathsFromHtml", () => {
  it("pulls .file chips and inline <code> paths, decodes entities", () => {
    const html = `
      <span class="file">NEW: docs/ams-v2/x.md</span>
      <span class="file">apps/reading/src/scene/Scene.tsx</span>
      <p>import from <code>apps/reading/src/lib/auth.tsx</code> and call <code>useAuth</code>.</p>
      <code>git cat-file -e origin/main:&lt;path&gt;</code>
    `;
    const got = extractPathsFromHtml(html);
    expect(got).toContain("NEW: docs/ams-v2/x.md");
    expect(got).toContain("apps/reading/src/scene/Scene.tsx");
    expect(got).toContain("apps/reading/src/lib/auth.tsx");
    // prose symbol + the command template are NOT extracted as paths
    expect(got).not.toContain("useAuth");
    expect(got.some((p) => p.includes("<path>"))).toBe(false);
  });

  it("tags chip vs inline origin, and chip origin wins on a dup", () => {
    const html = `
      <span class="file">apps/reading/src/scene/Scene.tsx</span>
      <p>see <code>apps/reading/src/scene/Scene.tsx</code> and <code>apps/reading/src/lib/api.ts</code></p>
    `;
    const refs = extractRefsFromHtml(html);
    const scene = refs.find((r) => r.raw.includes("Scene.tsx"));
    const api = refs.find((r) => r.raw.includes("api.ts"));
    // Scene is cited as BOTH a chip and inline → chip origin wins.
    expect(scene?.origin).toBe("file-chip");
    // api.ts is inline-only → inline origin.
    expect(api?.origin).toBe("inline-code");
  });
});

describe("glob dependencies", () => {
  const dirs: string[] = [];
  const MATCHING_GLOB = "apps/reading/src/AppShell.*.test.tsx";
  const ABSENT_GLOB = "apps/reading/src/__ref_lint_absent_parent__/*.tsx";

  afterEach(() => {
    for (const dir of dirs.splice(0)) rmSync(dir, { recursive: true, force: true });
  });

  function lintChip(raw: string) {
    const dir = mkdtempSync(join(tmpdir(), "ams-reflint-glob-"));
    dirs.push(dir);
    const fixture = join(dir, "glob.html");
    writeFileSync(fixture, `<span class="file">${raw}</span>`);
    return lintHtmlFile(fixture, REPO_ROOT);
  }

  it("PASSES a glob with tracked matches", () => {
    const report = lintChip(MATCHING_GLOB);
    expect(report.failed).toBe(false);
    expect(report.results).toEqual([
      { path: MATCHING_GLOB, declaredNew: false, verdict: "PASS", origin: "file-chip" },
    ]);
    expect(resolve("apps/reading/src/**/*.stories.tsx")).toBe(true);
    expect(resolve("apps/reading/src/scene/Scen?.tsx")).toBe(true);
    expect(resolve("apps/reading/src/scene/[S]cene.tsx")).toBe(true);
  });

  it("FAILS an undeclared glob under an absent parent", () => {
    const report = lintChip(ABSENT_GLOB);
    expect(report.failed).toBe(true);
    expect(report.results).toEqual([
      { path: ABSENT_GLOB, declaredNew: false, verdict: "FAIL", origin: "file-chip" },
    ]);
  });

  it("preserves NEW: glob declarations and skips resolution", () => {
    const report = lintChip(`NEW: ${ABSENT_GLOB}`);
    expect(report.failed).toBe(false);
    expect(report.results).toEqual([
      { path: ABSENT_GLOB, declaredNew: true, verdict: "NEW", origin: "file-chip" },
    ]);
    const results = lintRefs(
      extractRefsFromHtml(`<span class="file">NEW: ${MATCHING_GLOB}</span>`),
      () => { throw new Error("declared-new globs must not be resolved"); },
    );
    expect(results[0].verdict).toBe("NEW");
  });

  it("keeps unmatched inline globs advisory", () => {
    const results = lintRefs(extractRefsFromHtml(`<code>${ABSENT_GLOB}</code>`), resolve);
    expect(results).toEqual([
      { path: ABSENT_GLOB, declaredNew: false, verdict: "ADVISORY-ABSENT", origin: "inline-code" },
    ]);
  });

  it("uses the pinned main tree, not the working tree or a later HEAD", () => {
    const dir = mkdtempSync(join(tmpdir(), "ams-reflint-git-"));
    dirs.push(dir);
    const git = (...args: string[]) => execFileSync("git", args, {
      cwd: dir,
      encoding: "utf8",
      stdio: ["ignore", "pipe", "pipe"],
    }).trim();
    const commit = () => git(
      "-c", "user.name=Ref lint test", "-c", "user.email=ref-lint@example.invalid",
      "-c", "commit.gpgsign=false", "-c", "core.hooksPath=/dev/null",
      "commit", "-m", "fixture",
    );
    git("init");
    mkdirSync(join(dir, "apps/main-only"), { recursive: true });
    writeFileSync(join(dir, "apps/main-only/kept.ts"), "export {};\n");
    git("add", ".");
    commit();
    git("update-ref", "refs/remotes/origin/main", "HEAD");
    const pinned = createOriginMainResolver(dir);

    rmSync(join(dir, "apps/main-only"), { recursive: true });
    mkdirSync(join(dir, "apps/head-only"), { recursive: true });
    writeFileSync(join(dir, "apps/head-only/added.ts"), "export {};\n");
    git("add", "-A");
    commit();
    mkdirSync(join(dir, "apps/untracked-only"), { recursive: true });
    writeFileSync(join(dir, "apps/untracked-only/local.ts"), "export {};\n");

    // Move the ref before the lazy tree read: this resolver keeps its snapshot.
    git("update-ref", "refs/remotes/origin/main", "HEAD");
    expect(pinned("apps/main-only/*.ts")).toBe(true);
    expect(pinned("apps/head-only/*.ts")).toBe(false);
    expect(pinned("apps/untracked-only/*.ts")).toBe(false);
    expect(pinned("apps/main-only/kept.ts")).toBe(true);
    expect(pinned("apps/head-only/added.ts")).toBe(false);
    expect(createOriginMainResolver(dir)("apps/head-only/*.ts")).toBe(true);
  });
});

describe("lintHtmlFile — end-to-end on a planted-fiction fixture", () => {
  it("flips `failed` true and names the fiction (proves it would exit non-zero)", () => {
    const dir = mkdtempSync(join(tmpdir(), "ams-reflint-"));
    const fixture = join(dir, "planted-fiction.html");
    writeFileSync(
      fixture,
      `<!doctype html><html><body>
        <div class="files">
          <span class="file">apps/reading/src/scene/Scene.tsx</span>
          <span class="file">${FICTION}</span>
          <span class="file">NEW: docs/ams-v2/verified-interfaces.md</span>
        </div>
      </body></html>`,
    );

    const report = lintHtmlFile(fixture, REPO_ROOT);

    // The whole file is marked failed because of the planted fiction.
    expect(report.failed).toBe(true);

    const fail = report.results.find((r) => r.verdict === "FAIL");
    expect(fail).toBeDefined();
    expect(fail!.path).toBe(FICTION);

    // The real path still passes; the NEW one is declared-new.
    expect(report.results.find((r) => r.path === REAL)?.verdict).toBe("PASS");
    expect(
      report.results.find((r) => r.path === "docs/ams-v2/verified-interfaces.md")?.verdict,
    ).toBe("NEW");
  });

  it("a clean fixture (only real + NEW paths) does NOT fail", () => {
    const dir = mkdtempSync(join(tmpdir(), "ams-reflint-ok-"));
    const fixture = join(dir, "clean.html");
    writeFileSync(
      fixture,
      `<!doctype html><html><body>
        <span class="file">${REAL}</span>
        <span class="file">${RIGHT_LAUNCHER}</span>
        <span class="file">NEW: tools/specs/verify_spec_refs.ts</span>
      </body></html>`,
    );
    const report = lintHtmlFile(fixture, REPO_ROOT);
    expect(report.failed).toBe(false);
    const verdicts = report.results.map((r: RefResult) => r.verdict);
    expect(verdicts).not.toContain("FAIL");
  });
});

// ---------------------------------------------------------------------------
// Regression: a `.file` chip is a PATH, not a text container.
//
// Measured over the real 125-file spec corpus (specs/**/*.html +
// docs/htmlspec/**/*.html), the chip branch reported 161 "fiction" entries, of
// which 93 were prose fragments - "(per branch)", "call sites", "see each
// wave's brief in the design workflow script" - pulled out of chips that never
// contained a path. Only 22 were literal repo paths.
//
// The <code> branch has always applied looksLikeRepoPath(); the chip branch did
// not. These cases pin that asymmetry shut from both directions: prose must be
// rejected, and REAL paths - including ones under a directory that does not
// exist - must still be extracted.
// ---------------------------------------------------------------------------
describe("chip extraction: prose is not a path, absent paths still are", () => {
  const chip = (t: string) => `<p><span class="file">${t}</span></p>`;

  it.each([
    "(per branch)",
    "call sites",
    "see each wave&#x27;s brief in the design workflow script",
    "(worktree setup only)",
  ])("rejects prose inside a .file chip: %s", (prose) => {
    const refs = extractRefsFromHtml(chip(decodeEntitiesish(prose)));
    expect(refs.map((r) => r.raw)).toEqual([]);
  });

  it("still extracts a path under a directory that does NOT exist", () => {
    // services/ is absent from the repository. Listing it in REPO_DIR_PREFIXES
    // is what makes this VERIFIABLE, so the fictional tree is reported as
    // fiction rather than silently dropped as a non-path.
    const refs = extractRefsFromHtml(chip("services/mcp_server/server.py"));
    expect(refs.map((r) => r.raw)).toContain("services/mcp_server/server.py");
  });

  it("still extracts the known fiction constant", () => {
    const refs = extractRefsFromHtml(chip(FICTION));
    expect(refs.map((r) => r.raw)).toContain(FICTION);
  });

  it("looksLikeRepoPath keeps rejecting prose and accepting paths", () => {
    expect(looksLikeRepoPath("(per branch)")).toBe(false);
    expect(looksLikeRepoPath("call sites")).toBe(false);
    expect(looksLikeRepoPath("services/mcp_server/server.py")).toBe(true);
  });
});

// The harness decodes entities the same way the extractor does, so prose that
// arrives HTML-escaped is tested as prose rather than as a decoded path.
function decodeEntitiesish(s: string): string {
  return s.replace(/&#x27;/g, "'").replace(/&amp;/g, "&").replace(/&lt;/g, "<").replace(/&gt;/g, ">");
}
