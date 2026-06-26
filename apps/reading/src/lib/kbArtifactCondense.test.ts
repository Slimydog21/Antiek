import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

import {
  condenseKbArtifactHtml,
  hasExecutableScripts,
  KB_ARTIFACT_MINIMAL_FIXTURE,
} from "./kbArtifactCondense";

const __dir = dirname(fileURLToPath(import.meta.url));
const FIXTURE_PATH = join(__dir, "../../../../", KB_ARTIFACT_MINIMAL_FIXTURE);
const FIXTURE = readFileSync(FIXTURE_PATH, "utf-8");

describe("kbArtifactCondense", () => {
  it("rejects executable scripts", () => {
    expect(hasExecutableScripts('<script>alert(1)</script>')).toBe(true);
    expect(hasExecutableScripts(FIXTURE)).toBe(false);
  });

  it("condenses graph node ids from JSON island", () => {
    const v = condenseKbArtifactHtml(FIXTURE);
    expect(v.investigationId).toBe("inv-ui");
    expect(v.findings[0]?.nodeId).toBe("n-1");
    expect(v.synthesisExcerpt).toBe("Synth");
    expect(v.scriptFree).toBe(true);
  });
});