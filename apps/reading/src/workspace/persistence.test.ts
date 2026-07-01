import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  applyOver,
  buildShareableUrl,
  clearAll,
  clearScope,
  decodeWsParam,
  encodeWsParam,
  project,
  readCustomHotkeys,
  readScope,
  readWsFromUrl,
  writeCustomHotkeys,
  writeScope,
} from "./persistence";
import type { PersistedSnapshot } from "./persistence";
import { EMPTY_SNAPSHOT } from "./panel.types";
import { installLocalStorageMock } from "../test/localStorage";

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

let restoreLocalStorage: (() => void) | null = null;

beforeEach(() => {
  restoreLocalStorage = installLocalStorageMock();
  clearAll();
});

afterEach(() => {
  clearAll();
  vi.restoreAllMocks();
  restoreLocalStorage?.();
  restoreLocalStorage = null;
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

  it("rejects structurally malformed workspace snapshots from the URL", () => {
    const malformed = {
      ...SAMPLE,
      panels: {
        "demo:one": {
          ...SAMPLE.panels["demo:one"],
          rect: { x: 0, y: 0, width: "wide", height: 300 },
        },
      },
    };
    expect(decodeWsParam(btoa(JSON.stringify(malformed)))).toBeNull();
  });

  it("tolerates unknown future fields on valid URL snapshots", () => {
    const raw = btoa(
      JSON.stringify({
        ...SAMPLE,
        futureField: "kept by newer code",
        panels: {
          "demo:one": {
            ...SAMPLE.panels["demo:one"],
            futureField: "kept by newer code",
          },
        },
      }),
    );
    expect(decodeWsParam(raw)?.panels["demo:one"].title).toBe("One");
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

  it("drops malformed localStorage snapshots instead of hydrating corrupt panels", () => {
    window.localStorage.setItem(
      "antiek.workspace.global",
      JSON.stringify({
        ...SAMPLE,
        dockLeftIds: ["demo:one", 7],
      }),
    );
    expect(readScope({ kind: "global" })).toBeNull();
  });

  it("drops snapshots with unknown panel kinds before registry render", () => {
    window.localStorage.setItem(
      "antiek.workspace.global",
      JSON.stringify({
        ...SAMPLE,
        panels: {
          "demo:one": {
            ...SAMPLE.panels["demo:one"],
            kind: "FuturePanel",
          },
        },
      }),
    );
    expect(readScope({ kind: "global" })).toBeNull();
  });

  it("drops snapshots with dangling dock ids", () => {
    window.localStorage.setItem(
      "antiek.workspace.global",
      JSON.stringify({
        ...SAMPLE,
        dockLeftIds: ["demo:one", "missing"],
      }),
    );
    expect(readScope({ kind: "global" })).toBeNull();
  });

  it("drops snapshots when a dock id points at a panel in the wrong mode", () => {
    window.localStorage.setItem(
      "antiek.workspace.global",
      JSON.stringify({
        ...SAMPLE,
        dockLeftIds: ["demo:one", "demo:two"],
      }),
    );
    expect(readScope({ kind: "global" })).toBeNull();
  });

  it("drops snapshots when a docked panel is missing from its dock array", () => {
    window.localStorage.setItem(
      "antiek.workspace.global",
      JSON.stringify({
        ...SAMPLE,
        dockLeftIds: [],
      }),
    );
    expect(readScope({ kind: "global" })).toBeNull();
  });

  it("writes + reads route scope independently of global", () => {
    writeScope({ kind: "global" }, SAMPLE);
    writeScope({ kind: "route", route: "/wrestle" }, {
      ...SAMPLE,
      panels: {
        ...SAMPLE.panels,
        "other:notes": {
          ...SAMPLE.panels["demo:one"],
          id: "other:notes",
          mode: "docked-right",
          title: "Notes",
        },
      },
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

describe("persistence — custom hotkeys blob", () => {
  it("reads a valid custom-hotkeys blob", () => {
    writeCustomHotkeys({
      schemaVersion: 1,
      bindings: [
        {
          id: "hk-1",
          spec: "mod+.",
          route: "/inv/inv-1",
          entityId: "inv-1",
          entityKind: "investigation",
          label: "Investigation",
        },
      ],
    });

    expect(readCustomHotkeys().bindings[0]?.route).toBe("/inv/inv-1");
  });

  it("drops malformed custom-hotkey bindings instead of seeding bad shortcuts", () => {
    window.localStorage.setItem(
      "antiek.workspace.custom-hotkeys",
      JSON.stringify({
        schemaVersion: 1,
        bindings: [
          {
            id: "hk-bad",
            spec: "mod+.",
            route: "/inv/inv-1",
            entityId: "inv-1",
            entityKind: "spaceship",
            label: "Investigation",
          },
        ],
      }),
    );

    expect(readCustomHotkeys()).toEqual({ schemaVersion: 1, bindings: [] });
  });

  it("drops structurally valid but off-policy custom-hotkey specs", () => {
    window.localStorage.setItem(
      "antiek.workspace.custom-hotkeys",
      JSON.stringify({
        schemaVersion: 1,
        bindings: [
          {
            id: "hk-alt",
            spec: "alt+j",
            route: "/inv/inv-1",
            entityId: "inv-1",
            entityKind: "investigation",
            label: "Investigation",
          },
        ],
      }),
    );

    expect(readCustomHotkeys()).toEqual({ schemaVersion: 1, bindings: [] });
  });

  it("drops custom-hotkey blobs with duplicate specs", () => {
    window.localStorage.setItem(
      "antiek.workspace.custom-hotkeys",
      JSON.stringify({
        schemaVersion: 1,
        bindings: [
          {
            id: "hk-1",
            spec: "mod+.",
            route: "/inv/inv-1",
            entityId: "inv-1",
            entityKind: "investigation",
            label: "Investigation 1",
          },
          {
            id: "hk-2",
            spec: "Mod+.",
            route: "/inv/inv-2",
            entityId: "inv-2",
            entityKind: "investigation",
            label: "Investigation 2",
          },
        ],
      }),
    );

    expect(readCustomHotkeys()).toEqual({ schemaVersion: 1, bindings: [] });
  });

  it("drops custom-hotkey blobs with duplicate binding ids", () => {
    window.localStorage.setItem(
      "antiek.workspace.custom-hotkeys",
      JSON.stringify({
        schemaVersion: 1,
        bindings: [
          {
            id: "hk-same",
            spec: "mod+.",
            route: "/inv/inv-1",
            entityId: "inv-1",
            entityKind: "investigation",
            label: "Investigation 1",
          },
          {
            id: "hk-same",
            spec: "mod+,",
            route: "/inv/inv-2",
            entityId: "inv-2",
            entityKind: "investigation",
            label: "Investigation 2",
          },
        ],
      }),
    );

    expect(readCustomHotkeys()).toEqual({ schemaVersion: 1, bindings: [] });
  });

  it("drops custom-hotkey blobs with duplicate entity ids", () => {
    window.localStorage.setItem(
      "antiek.workspace.custom-hotkeys",
      JSON.stringify({
        schemaVersion: 1,
        bindings: [
          {
            id: "hk-1",
            spec: "mod+.",
            route: "/inv/inv-1",
            entityId: "inv-1",
            entityKind: "investigation",
            label: "Investigation 1",
          },
          {
            id: "hk-2",
            spec: "mod+,",
            route: "/inv/inv-1",
            entityId: "inv-1",
            entityKind: "investigation",
            label: "Investigation 1 again",
          },
        ],
      }),
    );

    expect(readCustomHotkeys()).toEqual({ schemaVersion: 1, bindings: [] });
  });

  it("tolerates unknown future fields on valid custom-hotkey bindings", () => {
    window.localStorage.setItem(
      "antiek.workspace.custom-hotkeys",
      JSON.stringify({
        schemaVersion: 1,
        bindings: [
          {
            id: "hk-1",
            spec: "mod+.",
            route: "/inv/inv-1",
            entityId: "inv-1",
            entityKind: "investigation",
            label: "Investigation",
            futureField: "kept by newer code",
          },
        ],
        futureField: "kept by newer code",
      }),
    );

    expect(readCustomHotkeys().bindings[0]?.spec).toBe("mod+.");
  });

  it("the localStorage test helper coerces stored values like browser Storage", () => {
    window.localStorage.setItem("coerced", undefined as unknown as string);
    expect(window.localStorage.getItem("coerced")).toBe("undefined");
  });
});
