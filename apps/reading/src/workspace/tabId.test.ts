/**
 * tabId.test.ts — A2b items 1, 3 and 4: every new tab_id is opaque and legal
 * under THREAD-CONTRACT §1.6 ("1 to 64 of [A-Za-z0-9_-]"), minted by one
 * helper, and the model refuses anything else.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

import { newTabId } from "./tabId";
import {
  emptyTabTree,
  fromSnapshot,
  isLegalTabId,
  spawnChild,
  toSnapshot,
  type TabTree,
} from "./tabTree";
import { fromWire } from "./tabTreeWire";

const LEGAL = /^[A-Za-z0-9_-]{1,64}$/;

afterEach(() => {
  vi.restoreAllMocks();
});

describe("newTabId (A2b item 1)", () => {
  it("is 't' + base64url of 16 random bytes: 23 characters of [A-Za-z0-9_-]", () => {
    for (let i = 0; i < 200; i++) {
      const id = newTabId();
      expect(id).toMatch(/^t[A-Za-z0-9_-]{22}$/);
      expect(id).toHaveLength(23);
      expect(isLegalTabId(id)).toBe(true);
    }
  });

  it("draws its 16 bytes from crypto.getRandomValues and encodes them as base64url", () => {
    const spy = vi.spyOn(globalThis.crypto, "getRandomValues").mockImplementation(<T extends ArrayBufferView | null>(arr: T): T => {
      const bytes = arr as unknown as Uint8Array;
      for (let i = 0; i < bytes.length; i++) bytes[i] = 0xfb + (i % 5); // 0xfb..0xff: exercises '-' and '_'
      return arr;
    });
    const id = newTabId();
    expect(spy).toHaveBeenCalledTimes(1);
    const arg = spy.mock.calls[0][0] as unknown as Uint8Array;
    expect(arg).toBeInstanceOf(Uint8Array);
    expect(arg.length).toBe(16);
    const expected = btoa(String.fromCharCode(...arg)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
    expect(id).toBe(`t${expected}`);
    expect(id).toMatch(/[-_]/);
  });

  it("encodes nothing about the tab: two calls never agree", () => {
    const seen = new Set<string>();
    for (let i = 0; i < 1000; i++) seen.add(newTabId());
    expect(seen.size).toBe(1000);
  });
});

describe("uniqueness (A2b item 4)", () => {
  it("re-draws when the bytes land on an id the tree already holds, open or retired", () => {
    let call = 0;
    vi.spyOn(globalThis.crypto, "getRandomValues").mockImplementation(<T extends ArrayBufferView | null>(arr: T): T => {
      const bytes = arr as unknown as Uint8Array;
      bytes.fill(call < 2 ? 7 : 9); // the first two draws collide, the third does not
      call++;
      return arr;
    });
    const taken = `t${btoa(String.fromCharCode(...new Uint8Array(16).fill(7))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "")}`;
    const spawned = spawnChild(emptyTabTree("reading"), null, { tab_id: taken, kind: "reader", ref: "doc-1", mothership: "reading" });
    expect(spawned.ok).toBe(true);
    const tree = (spawned as { tree: TabTree }).tree;
    const id = newTabId(tree);
    expect(id).not.toBe(taken);
    expect(call).toBe(3);
    // The model's own guard: the same id cannot be spawned twice.
    const again = spawnChild(tree, null, { tab_id: taken, kind: "reader", ref: "doc-2", mothership: "reading" });
    expect(again.ok).toBe(false);
    if (!again.ok) expect(again.error.code).toBe("duplicate_tab_id");
  });
});

describe("the model refuses an illegal tab_id (A2b item 3)", () => {
  const spawn = (tab_id: string) =>
    spawnChild(emptyTabTree("reading"), null, { tab_id, kind: "reader", ref: "doc-1", mothership: "reading" });

  it.each([
    ["the old structural root id", "root:reader:doc-1"],
    ["a structural child id", "child:root:reader:doc-1:reader:doc-2"],
    ["a reseed suffix", "root:reader:doc-1~2"],
    ["a route ref", "root:research:/inv/inv-1"],
    ["65 characters", "a".repeat(65)],
    ["a space", "tab one"],
    ["a non-ASCII letter", "tabé"],
    ["the empty string", ""],
  ])("spawn refuses %s with invalid_tab_id", (_label, id) => {
    const r = spawn(id);
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.error.code).toBe("invalid_tab_id");
  });

  it("spawn admits 64 characters of the contract's alphabet", () => {
    const id = `${"A".repeat(20)}${"z".repeat(20)}${"0".repeat(20)}_-_-`;
    expect(id).toHaveLength(64);
    expect(spawn(id).ok).toBe(true);
  });

  it("fromSnapshot refuses a snapshot holding a structural id, open or retired", () => {
    const good = spawn("t1");
    if (!good.ok) throw new Error(good.error.message);
    const snap = toSnapshot(good.tree);
    const openBad = JSON.parse(JSON.stringify(snap).split('"t1"').join('"root:reader:doc-1"'));
    const r1 = fromSnapshot(openBad);
    expect(r1.ok).toBe(false);
    if (!r1.ok) expect(r1.error.code).toBe("invalid_tab_id");
  });

  it("a server snapshot with a structural id, read through fromWire, is refused before it reaches the store", () => {
    const wire = {
      tree: {
        nodes: {
          "root:reader:doc-1": {
            tab_id: "root:reader:doc-1", parent_tab_id: null, side: "left" as const, kind: "reader" as const,
            ref: "doc-1", title: "", mothership: "reading" as const, public_number: null, hier_number: "1", child_order: [],
          },
        },
        root_order: ["root:reader:doc-1"],
      },
      active: { left: null, right: null },
      version: 1,
      next_child_index: { root: 2 },
      retired: [],
    };
    const r = fromSnapshot(toSnapshot(fromWire(wire, "reading")));
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.error.code).toBe("invalid_tab_id");
  });

  it("the contract's own pattern and the model's agree", () => {
    for (const id of ["t", "t-doc", "A_b-9", "a".repeat(64)]) expect(isLegalTabId(id)).toBe(LEGAL.test(id));
    for (const id of ["", "a:b", "a/b", "a~2", "a".repeat(65), "__proto__"]) expect(isLegalTabId(id)).toBe(false);
  });
});
