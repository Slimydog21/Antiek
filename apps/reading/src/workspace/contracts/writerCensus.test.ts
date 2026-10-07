/**
 * writerCensus.test.ts — I11 / M3: one writer of the selected project, one
 * persistence writer, and the pre-backend provenance literal confined to the
 * adapter. An fs walk of apps/reading/src excluding tests and stories.
 */
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative, resolve } from "node:path";
import { describe, expect, it } from "vitest";

const SRC = typeof __dirname === "string" ? resolve(__dirname, "../../") : resolve(process.cwd(), "src");

function walk(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) walk(p, out);
    else if (/\.(ts|tsx)$/.test(name) && !/\.test\./.test(name) && !/\.stories\./.test(name)) out.push(p);
  }
  return out;
}

const files = walk(SRC);
const rel = (p: string) => relative(SRC, p).split("\\").join("/");
const grep = (re: RegExp) => files.filter((f) => re.test(readFileSync(f, "utf8"))).map(rel).sort();

describe("writer census", () => {
  it(".selectProject( is called only by the store, the mirror and the picker", () => {
    const hits = grep(/\.selectProject\(/);
    for (const h of hits) {
      expect(["workspace/tabTreeStore.ts", "workspace/contracts/selection.ts", "workspace/ProjectPickerContent.tsx"]).toContain(h);
    }
    expect(hits).toContain("workspace/contracts/selection.ts");
    expect(hits).toContain("workspace/ProjectPickerContent.tsx");
    const picker = readFileSync(join(SRC, "workspace/ProjectPickerContent.tsx"), "utf8");
    const calls = picker.match(/[\w.()]*\.selectProject\(/g) ?? [];
    expect(calls).toEqual(["useSelection.getState().selectProject("]);
  });

  it("writeTabProject/clearTabProject are called only by persistence and tabTreeStore", () => {
    expect(grep(/\b(writeTabProject|clearTabProject)\(/)).toEqual(["workspace/persistence.ts", "workspace/tabTreeStore.ts"]);
  });

  it('the `kind: "investigation"` node-source CONSTRUCTOR lives only in adapters/preBackend.ts under contracts/', () => {
    // The type union in tree.ts declares the member with a `;` separator;
    // only an object literal (`,` or `}` after the value) constructs one.
    const under = files.filter((f) => rel(f).startsWith("workspace/contracts/"));
    const hits = under.filter((f) => /\bkind:\s*"investigation"\s*[,}]/.test(readFileSync(f, "utf8"))).map(rel);
    expect(hits).toEqual(["workspace/contracts/adapters/preBackend.ts"]);
    const tree = readFileSync(join(SRC, "workspace/contracts/tree.ts"), "utf8");
    expect(/\bkind:\s*"investigation";/.test(tree)).toBe(true);
  });

  it("the contracts module never calls setWorkspaceOwner", () => {
    const under = files.filter((f) => rel(f).startsWith("workspace/contracts/"));
    expect(under.filter((f) => /setWorkspaceOwner\(/.test(readFileSync(f, "utf8"))).map(rel)).toEqual([]);
  });

  it("index.ts re-exports no adapter module", () => {
    const index = readFileSync(join(SRC, "workspace/contracts/index.ts"), "utf8");
    const specs = [...index.matchAll(/^\s*export\s[\s\S]*?from\s+["']([^"']+)["']/gm)].map((m) => m[1]).sort();
    expect(specs).toEqual(["./anchor", "./openers", "./selection", "./tree", "./treeStore"]);
    expect(index).not.toMatch(/preBackend|PreBackend/);
  });
});
