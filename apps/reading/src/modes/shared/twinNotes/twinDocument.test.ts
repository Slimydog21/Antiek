import { describe, expect, it } from "vitest";

import {
  demoTwinForAsset,
  emptyTwin,
  isTwinnableAsset,
  mergeTwinDocuments,
} from "./twinDocument";

describe("twinDocument", () => {
  it("marks twins non-twinnable", () => {
    expect(isTwinnableAsset({ isTwin: true })).toBe(false);
    expect(isTwinnableAsset({ twinOf: "a" })).toBe(false);
    expect(isTwinnableAsset({})).toBe(true);
  });

  it("empty twin is advisory and isTwin", () => {
    const t = emptyTwin("doc-1", "t1");
    expect(t.isTwin).toBe(true);
    expect(t.authority).toBe("advisory");
    expect(t.status).toBe("empty");
  });

  it("merges same-parent twins without twin-of-twin", () => {
    const a = demoTwinForAsset("doc");
    const b = {
      ...emptyTwin("doc", "t2"),
      status: "ready" as const,
      insights: [{ id: "x", text: "A third insight" }],
      questions: a.questions,
    };
    const m = mergeTwinDocuments(a, b);
    expect("ok" in m && m.ok === false).toBe(false);
    if ("ok" in m) return;
    expect(m.isTwin).toBe(true);
    expect(m.insights.length).toBeGreaterThanOrEqual(3);
    expect(m.parentAssetId).toBe("doc");
  });

  it("rejects cross-parent merge", () => {
    const m = mergeTwinDocuments(
      demoTwinForAsset("a"),
      demoTwinForAsset("b"),
    );
    expect(m).toEqual({ ok: false, reason: "parent_mismatch" });
  });
});
