/**
 * Static AMS harness contract.
 *
 * The capstone state is: the five ams-shell anchors are live Playwright tests,
 * not skipped fixtures. This fast Vitest guard keeps the run note and shell
 * spec from drifting back to the pre-SPR-10 "all anchors are fixme" story.
 */

import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const repoRoot = resolve(__dirname, "../../../..");

function readRepo(path: string): string {
  return readFileSync(resolve(repoRoot, path), "utf8");
}

describe("AMS-v2 harness contract", () => {
  it("keeps the five shell anchors executable", () => {
    const shellSpec = readRepo("apps/reading/e2e/ams-shell.spec.ts");

    expect(shellSpec).not.toMatch(/\btest\.fixme\s*\(/);
    expect(shellSpec.match(/test\(["']anchor\[/g) ?? []).toHaveLength(5);
  });

  it("keeps the run note reconciled to the SPR-10 capstone state", () => {
    const runNote = readRepo("docs/ams-v2/e2e-harness.md");

    expect(runNote).toContain("The 5 `ams-shell.spec.ts` anchors are no longer `test.fixme`");
    expect(runNote).toContain("operator-only custom-hotkey OS/browser collision");
  });
});
