import { afterEach, beforeEach, describe, expect, it } from "vitest";

import {
  applyOver,
  buildShareableUrl,
  clearAll,
  clearScope,
  decodeWsParam,
  encodeWsParam,
  project,
  readScope,
  readWsFromUrl,
  writeScope,
} from "./persistence";
import type { PersistedSnapshot } from "./persistence";
import { EMPTY_SNAPSHOT } from "./panel.types";

const SAMPLE: PersistedSnapshot = {
  schemaVersion: 1,
  panels: {
    "demo:one": {
      id: "demo:one",
      kind: "FakeSidebar",
      props: {},
      mode: "docked-left",
      zIndex: 1,
      rect: { x: 100, y: 100, width: 400, height: 300 },
      size: { width: 320, height: 0 },
      pinned: true,
      title: "One",
    },
    "demo:two": {
      id: "demo:two",
      kind: "FakeNotebook",
      props: {},
      mode: "floating",
      zIndex: 5,
      rect: { x: 200, y: 200, width: 600, height: 480 },
      size: { width: 320, height: 0 },
      pinned: false,
      title: "Two",
    },
  },
  dockLeftIds: ["demo:one"],
  dockRightIds: [],
  dockBottomIds: [],
  dockBottomHeight: 220,
};

beforeEach(() => {
  clearAll();
});

afterEach(() => {
  clearAll();
});

describe("persistence — encode/decode URL", () => {
  it("encode + decode round-trips the snapshot", () => {
    const raw = encodeWsParam(SAMPLE);
    expect(raw).toBeTruthy();
    expect(typeof raw).toBe("string");
    const back = decodeWsParam(raw);
    expect(back).not.toBeNull();
    expect(back?.dockLeftIds).toEqual(["demo:one"]);
    expect(back?.panels["demo:one"].title).toBe("One");
  });

  it("rejects malformed base64", () => {
    expect(decodeWsParam("not-base64!@#$")).toBeNull();
  });

  it("rejects mismatched schemaVersion", () => {
    const raw = btoa(JSON.stringify({ ...SAMPLE, schemaVersion: 99 }));
    expect(decodeWsParam(raw)).toBeNull();
  });

  it("buildShareableUrl includes ?ws= and pathname", () => {
    const url = buildShareableUrl(SAMPLE);
    expect(url).toContain("?ws=");
    expect(url).toContain(window.location.pathname);
  });

  it("readWsFromUrl returns null when no ws param", () => {
    expect(readWsFromUrl()).toBeNull();
  });
});

describe("persistence — localStorage scopes", () => {
  it("writes + reads the global scope", () => {
    writeScope({ kind: "global" }, SAMPLE);
    const back = readScope({ kind: "global" });
    expect(back?.dockLeftIds).toEqual(["demo:one"]);
  });

  it("writes + reads route scope independently of global", () => {
    writeScope({ kind: "global" }, SAMPLE);
    writeScope({ kind: "route", route: "/wrestle" }, {
      ...SAMPLE,
      dockRightIds: ["other:notes"],
    });
    expect(readScope({ kind: "global" })?.dockRightIds).toEqual([]);
    expect(readScope({ kind: "route", route: "/wrestle" })?.dockRightIds).toEqual([
      "other:notes",
    ]);
  });

  it("clearScope removes only the targeted scope", () => {
    writeScope({ kind: "global" }, SAMPLE);
    writeScope({ kind: "route", route: "/r" }, SAMPLE);
    clearScope({ kind: "global" });
    expect(readScope({ kind: "global" })).toBeNull();
    expect(readScope({ kind: "route", route: "/r" })).not.toBeNull();
  });

  it("clearAll wipes every antiek.workspace.* key", () => {
    writeScope({ kind: "global" }, SAMPLE);
    writeScope({ kind: "route", route: "/r" }, SAMPLE);
    writeScope({ kind: "investigation", id: "inv-1" }, SAMPLE);
    const n = clearAll();
    expect(n).toBe(3);
    expect(readScope({ kind: "global" })).toBeNull();
  });
});

describe("persistence — project + applyOver", () => {
  it("project strips transient state", () => {
    const fully = { ...EMPTY_SNAPSHOT, ...SAMPLE, focusedPanelId: "demo:one", zCounter: 99 };
    const persisted = project(fully);
    expect("focusedPanelId" in persisted).toBe(false);
    expect("zCounter" in persisted).toBe(false);
    expect(persisted.schemaVersion).toBe(1);
  });

  it("applyOver merges panels + re-derives floatingIds + zCounter", () => {
    const layered = applyOver({ ...EMPTY_SNAPSHOT }, SAMPLE);
    // demo:two is floating with z=5 → should appear in floatingIds
    expect(layered.floatingIds).toContain("demo:two");
    // zCounter re-derived from max(z) = 5
    expect(layered.zCounter).toBe(5);
  });

  it("applyOver returns base unchanged on schemaVersion mismatch", () => {
    const layered = applyOver(
      { ...EMPTY_SNAPSHOT },
      { ...SAMPLE, schemaVersion: 99 as 1 },
    );
    expect(Object.keys(layered.panels)).toHaveLength(0);
  });
});
