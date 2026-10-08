/** paneWidthStore.test.ts — SPR-07 invariant 27 (patterns 4/5/6): an account-scoped width blob and a 424 px main minimum. */
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { accountStorageKey, awaitWorkspaceOwnerSession, setWorkspaceOwner, workspaceOwnerSession } from "../../lib/accountWorkspaceOwner";
import { COLLAPSE_THRESHOLD, MAIN_MIN, PANE_MIN, PANE_WIDTH_KEY, STEP, clearPaneWidth, effectiveWidth, paneWidthMax, readPaneWidth, usePaneWidthStore, writePaneWidth } from "./paneWidthStore";

beforeEach(async () => { setWorkspaceOwner(null); setWorkspaceOwner("owner-a"); await awaitWorkspaceOwnerSession(workspaceOwnerSession()); window.localStorage.clear(); usePaneWidthStore.getState().reset(); });
afterEach(() => { try { window.localStorage.clear(); } finally { setWorkspaceOwner(null); } });

describe("effectiveWidth", () => {
  it("null preferred ⇒ the tier default; otherwise clamped between 240 and the main-minimum bound", () => {
    expect(PANE_MIN).toBe(240); expect(MAIN_MIN).toBe(424); expect(STEP).toBe(32); expect(COLLAPSE_THRESHOLD).toBe(244);
    expect(effectiveWidth({ preferred: null, containerWidth: 1280, leftDockWidth: 0, defaultWidth: 320 })).toBe(320);
    expect(effectiveWidth({ preferred: null, containerWidth: 800, leftDockWidth: 0, defaultWidth: 280 })).toBe(280);
    expect(effectiveWidth({ preferred: 600, containerWidth: 1280, leftDockWidth: 0, defaultWidth: 320 })).toBe(600);
    expect(effectiveWidth({ preferred: 100, containerWidth: 1280, leftDockWidth: 0, defaultWidth: 320 })).toBe(240);
  });

  it("containerWidth 768 with no left dock leaves a 308 px maximum (768 - 36 - 424)", () => {
    expect(paneWidthMax(768, 0)).toBe(308);
    expect(effectiveWidth({ preferred: 900, containerWidth: 768, leftDockWidth: 0, defaultWidth: 280 })).toBe(308);
    expect(paneWidthMax(1280, 320)).toBe(1280 - 36 - 320 - 424);
  });

  it("when nothing fits (containerWidth - 36 < 664) the right pane wins down to 240", () => {
    expect(paneWidthMax(600, 0)).toBe(240);
    expect(effectiveWidth({ preferred: 500, containerWidth: 600, leftDockWidth: 0, defaultWidth: 280 })).toBe(240);
  });
});

describe("persistence", () => {
  it("writes a schemaVersion 1 blob under the account-scoped key; mismatched version or null key reads null", () => {
    setWorkspaceOwner("owner-a");
    const key = accountStorageKey(PANE_WIDTH_KEY)!;
    expect(PANE_WIDTH_KEY).toBe("antiek.agent.pane-width.v1");
    writePaneWidth(400);
    expect(JSON.parse(window.localStorage.getItem(key)!)).toEqual({ schemaVersion: 1, width: 400 });
    expect(readPaneWidth()).toBe(400);
    window.localStorage.setItem(key, JSON.stringify({ schemaVersion: 2, width: 400 }));
    expect(readPaneWidth()).toBeNull();
    writePaneWidth(416);
    clearPaneWidth();
    expect(window.localStorage.getItem(key)).toBeNull();
    setWorkspaceOwner(null);
    writePaneWidth(400);
    expect(readPaneWidth()).toBeNull();
    expect(window.localStorage.length).toBe(0);
  });

  it("owner b reads null while owner a's value survives; the layout-preset key stays unscoped", () => {
    setWorkspaceOwner("owner-a");
    writePaneWidth(400);
    const keyA = accountStorageKey(PANE_WIDTH_KEY)!;
    setWorkspaceOwner("owner-b");
    expect(readPaneWidth()).toBeNull();
    expect(window.localStorage.getItem(keyA)).not.toBeNull();
    expect(keyA).not.toBe(PANE_WIDTH_KEY);
  });

  it("the store hydrates from storage on demand and writes through setPreferred", () => {
    setWorkspaceOwner("owner-a");
    writePaneWidth(352);
    usePaneWidthStore.getState().hydrate();
    expect(usePaneWidthStore.getState().preferred).toBe(352);
    usePaneWidthStore.getState().setPreferred(384);
    expect(readPaneWidth()).toBe(384);
    usePaneWidthStore.getState().setPreferred(null);
    expect(readPaneWidth()).toBeNull();
  });
});
