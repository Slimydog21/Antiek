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

import { execSync } from "node:child_process";
import { describe, expect, it } from "vitest";

import {
  extractPathsFromHtml,
  extractRefsFromHtml,
  existsOnOriginMain,
  lintRefs,
  lintHtmlFile,
  parseNewPrefix,
  looksLikeRepoPath,
  type RefResult,
} from "./verify_spec_refs";
import { mkdtempSync, writeFileSync } from "node:fs";
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
