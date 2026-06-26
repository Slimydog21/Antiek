import { describe, expect, it } from "vitest";

import { condenseKbArtifactHtml, hasExecutableScripts } from "./kbArtifactCondense";

const FIXTURE = `<!doctype html><html><body>
<section id="findings"><div data-node-id="n-1">Finding</div></section>
<script type="application/json" id="antiek-artifact-v1">{
  "schema_version": 1,
  "investigation_id": "inv-ui",
  "problem_question": "Q",
  "insights": [{"node_id": "n-1", "text": "Finding", "confidence": "high"}],
  "open_questions": [],
  "synthesis_excerpt": "Synth",
  "agent_notes": []
}</script>
</body></html>`;

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