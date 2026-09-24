/**
 * Never quietly disabled (audit B1, design spec §4): every LemonButton and
 * LemonMenuItem that can be disabled says why, through `disabledReason`.
 * The census before wave 2: 135 of 200 LemonButtons passed `disabled` and
 * none carried a reason (4 had a native title, unreachable behind
 * pointer-events:none).
 *
 * The one call site left is in modes/Sources (owned by open PR #3416); it
 * is pinned here and the list can only shrink.
 */
import ts from "typescript";
import { readFileSync, readdirSync } from "node:fs";
import { join, relative, resolve } from "node:path";
import { describe, expect, it } from "vitest";

const SRC = resolve(import.meta.dirname, "..", "..");
const OWNED_ELSEWHERE = new Set(["modes/Sources/ConnectedToolSearch.tsx LemonButton"]);

function files(dir: string): string[] {
  const out: string[] = [];
  for (const e of readdirSync(dir, { withFileTypes: true })) {
    const p = join(dir, e.name);
    if (e.isDirectory()) out.push(...files(p));
    else if (/\.tsx$/.test(e.name) && !/\.(test|stories)\.tsx$/.test(e.name)) out.push(p);
  }
  return out;
}

function census() {
  const quiet: string[] = [];
  let withReason = 0;
  for (const file of files(SRC)) {
    const src = readFileSync(file, "utf8");
    if (!/LemonButton|LemonMenuItem/.test(src)) continue;
    const sf = ts.createSourceFile(file, src, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
    const visit = (n: ts.Node) => {
      if ((ts.isJsxOpeningElement(n) || ts.isJsxSelfClosingElement(n))) {
        const tag = n.tagName.getText(sf);
        if (tag === "LemonButton" || tag === "LemonMenuItem") {
          const names = n.attributes.properties.filter(ts.isJsxAttribute).map((a) => a.name.getText(sf));
          if (names.includes("disabledReason")) withReason++;
          if (names.includes("disabled")) {
            const line = sf.getLineAndCharacterOfPosition(n.getStart(sf)).line + 1;
            quiet.push(`${relative(SRC, file)} ${tag}:${line}`);
          }
        }
      }
      ts.forEachChild(n, visit);
    };
    visit(sf);
  }
  return { quiet, withReason };
}

describe("disabledReason guard", () => {
  const { quiet, withReason } = census();
  const key = (q: string) => q.replace(/:\d+$/, "");

  it("no LemonButton or LemonMenuItem is disabled without saying why", () => {
    expect(quiet.filter((q) => !OWNED_ELSEWHERE.has(key(q)))).toEqual([]);
  });

  it("the owned-elsewhere list names only call sites that still exist", () => {
    for (const k of OWNED_ELSEWHERE) expect(quiet.map(key)).toContain(k);
  });

  it("the migration is real: the reasons are there", () => {
    expect(withReason).toBeGreaterThanOrEqual(130);
  });
});
