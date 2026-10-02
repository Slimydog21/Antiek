import { beforeEach, describe, expect, it } from "vitest";

import { MAX_WINDOWS, WINDOW_Z_BASE, useWindows } from "./windowsStore";

const w = () => useWindows.getState();

beforeEach(() => {
  w().reset();
});

describe("windowsStore — open + close", () => {
  it("opens a floating window by default and focuses it", () => {
    const id = w().open("library", {}, { title: "Library" });
    expect(w().windows[id].mode).toBe("floating");
    expect(w().order).toEqual([id]);
    expect(w().focusedId).toBe(id);
    expect(w().windows[id].title).toBe("Library");
  });

  it("opens with a custom id and payload", () => {
    const id = w().open("read", { documentId: "doc-1" }, { id: "read:doc-1" });
    expect(id).toBe("read:doc-1");
    expect(w().windows["read:doc-1"].payload).toEqual({ documentId: "doc-1" });
  });

  it("re-opening an existing id focuses instead of duplicating", () => {
    const a = w().open("stats", {}, { id: "stats" });
    w().open("library", {});
    const again = w().open("stats", {}, { id: "stats" });
    expect(again).toBe(a);
    expect(Object.keys(w().windows)).toHaveLength(2);
    // Re-opening restacks it to the top + focuses it.
    expect(w().focusedId).toBe("stats");
    expect(w().order[w().order.length - 1]).toBe("stats");
  });

  it("closes a window and removes it from order", () => {
    const a = w().open("stats", {});
    const b = w().open("library", {});
    w().close(a);
    expect(w().windows[a]).toBeUndefined();
    expect(w().order).toEqual([b]);
    expect(w().windows[b]).toBeDefined();
  });

  it("focus returns to the next-topmost window when the focused one closes", () => {
    const a = w().open("stats", {});
    const b = w().open("library", {});
    expect(w().focusedId).toBe(b);
    w().close(b);
    // Focus falls back to the remaining topmost (a).
    expect(w().focusedId).toBe(a);
  });

  it("focusedId becomes null when the last window closes", () => {
    const a = w().open("stats", {});
    w().close(a);
    expect(w().focusedId).toBeNull();
    expect(w().order).toEqual([]);
  });
});

describe("windowsStore — focus + z-order", () => {
  it("each opened window gets a strictly higher z than the previous", () => {
    const a = w().open("stats", {});
    const b = w().open("library", {});
    expect(w().windows[a].z).toBeGreaterThanOrEqual(WINDOW_Z_BASE);
    expect(w().windows[b].z).toBeGreaterThan(w().windows[a].z);
  });

  it("focus restacks the window to the top of z + order", () => {
    const a = w().open("stats", {});
    const b = w().open("library", {});
    expect(w().windows[a].z).toBeLessThan(w().windows[b].z);
    w().focus(a);
    expect(w().windows[a].z).toBeGreaterThan(w().windows[b].z);
    expect(w().focusedId).toBe(a);
    expect(w().order[w().order.length - 1]).toBe(a);
  });

  it("windows are independent — focusing one does not move another's rect", () => {
    const a = w().open("stats", {});
    const b = w().open("library", {});
    w().setRect(a, { x: 10, y: 10 });
    const bRectBefore = { ...w().windows[b].rect };
    w().focus(a);
    expect(w().windows[b].rect).toEqual(bRectBefore);
  });

  it("focus on a missing id is a no-op", () => {
    const a = w().open("stats", {});
    const before = w();
    w().focus("nope");
    expect(w()).toEqual(before);
    expect(w().focusedId).toBe(a);
  });

  // AMS2-SPR-04: the full focus-restack lifecycle on the now-default flow —
  // focus A then B then A leaves A topmost (highest z + last in order), and
  // closing the focused window refocuses the next-topmost rather than orphaning.
  it("focus A then B then A makes A topmost; closing the focused window refocuses next-topmost", () => {
    const a = w().open("stats", {}, { id: "A" });
    const b = w().open("library", {}, { id: "B" });

    // focus A then B then A
    w().focus(a);
    w().focus(b);
    w().focus(a);

    // A is topmost: highest z, last in order, and the focused window.
    expect(w().windows[a].z).toBeGreaterThan(w().windows[b].z);
    expect(w().order[w().order.length - 1]).toBe(a);
    expect(w().focusedId).toBe(a);

    // Closing the focused window (A) refocuses the next-topmost (B), not null.
    w().close(a);
    expect(w().windows[a]).toBeUndefined();
    expect(w().focusedId).toBe(b);
    expect(w().order[w().order.length - 1]).toBe(b);
  });
});

describe("windowsStore — rect + expand/restore", () => {
  it("setRect updates floating geometry", () => {
    const id = w().open("library", {});
    w().setRect(id, { x: 200, y: 150, width: 800, height: 600 });
    expect(w().windows[id].rect).toEqual({ x: 200, y: 150, width: 800, height: 600 });
  });

  it("expand moves to full and restore returns to the same floating rect", () => {
    const id = w().open("library", {});
    w().setRect(id, { x: 200, y: 150, width: 800, height: 600 });
    const floatRect = { ...w().windows[id].rect };
    w().expand(id);
    expect(w().windows[id].mode).toBe("full");
    // The floating rect is preserved while expanded (not clobbered).
    expect(w().windows[id].rect).toEqual(floatRect);
    w().restore(id);
    expect(w().windows[id].mode).toBe("floating");
    expect(w().windows[id].rect).toEqual(floatRect);
  });

  it("toggleMode flips floating ⇄ full", () => {
    const id = w().open("library", {});
    expect(w().windows[id].mode).toBe("floating");
    w().toggleMode(id);
    expect(w().windows[id].mode).toBe("full");
    w().toggleMode(id);
    expect(w().windows[id].mode).toBe("floating");
  });

  it("expand is a no-op when already full; restore is a no-op when floating", () => {
    const id = w().open("library", {});
    w().restore(id); // already floating
    expect(w().windows[id].mode).toBe("floating");
    w().expand(id);
    w().expand(id); // already full
    expect(w().windows[id].mode).toBe("full");
  });

  it("can open already-expanded via opts.mode", () => {
    const id = w().open("library", {}, { mode: "full" });
    expect(w().windows[id].mode).toBe("full");
  });
});

describe("windowsStore logical admission", () => {
  it.each([9, 15])("opens the requested %dth identity without changing its peers", (count) => {
    const ids = Array.from({ length: count - 1 }, (_, i) => `existing:${i}`);
    for (const id of ids) w().open("stats", { fixtureId: id }, { id });
    const before = w();
    const id = `requested:${count}`;
    const payload = { fixtureId: id };
    const rect = { x: 200, y: 150, width: 800, height: 600 };
    const returned = w().open("library", payload, { id, title: "Requested window", rect, mode: "full" });

    expect(returned).toBe(id);
    expect(w().windows[id]).toMatchObject({ id, kind: "library", title: "Requested window", payload, rect, mode: "full" });
    expect(w().windows[id].payload).toBe(payload);
    expect(Object.keys(w().windows)).toHaveLength(count);
    expect(w().order).toEqual([...ids, id]);
    expect(w().cycleOrder).toEqual([...ids, id]);
    expect(w().focusedId).toBe(id);
    expect(w().zCounter).toBe(before.zCounter + 1);
    expect(w().windows[id].z).toBe(w().zCounter);
    for (const peer of ids) expect(w().windows[peer]).toBe(before.windows[peer]);
  });

  it.each([9, 15])("reopens an existing identity among %d windows without replacing its content", (count) => {
    for (let i = 0; i < count; i++) w().open("stats", { fixtureIndex: i }, { id: `existing:${i}` });
    const id = "existing:0";
    w().setRect(id, { x: 123, width: 600 });
    w().expand(id);
    const before = w();
    const original = before.windows[id];
    const returned = w().open("library", { replacement: true }, { id, title: "Replacement", mode: "floating" });

    expect(returned).toBe(id);
    expect(Object.keys(w().windows)).toHaveLength(count);
    expect(w().windows[id]).toEqual({ ...original, z: before.zCounter + 1 });
    expect(w().windows[id].payload).toBe(original.payload);
    expect(w().windows[id].rect).toBe(original.rect);
    expect(w().cycleOrder).toEqual(before.cycleOrder);
    expect(w().order).toEqual([...before.order.filter((peer) => peer !== id), id]);
    expect(w().focusedId).toBe(id);
    for (const peer of before.order.filter((peer) => peer !== id)) expect(w().windows[peer]).toBe(before.windows[peer]);
  });

  it.each([false, true])("legacy replacement option %s cannot evict a different identity", (replaceOldestAtLimit) => {
    for (let i = 0; i < 8; i++) w().open("stats", {}, { id: `existing:${i}` });
    w().focus("existing:0");
    const before = w();
    const id = w().open("library", {}, { id: "requested", replaceOldestAtLimit });

    expect(id).toBe("requested");
    expect(w().order).toEqual([...before.order, id]);
    expect(w().cycleOrder).toEqual([...before.cycleOrder, id]);
    expect(w().focusedId).toBe(id);
    expect(Object.keys(w().windows)).toHaveLength(9);
    for (const peer of before.order) expect(w().windows[peer]).toBe(before.windows[peer]);
  });

  it("closing one of fifteen windows preserves its peers and admits a fresh identity", () => {
    for (let i = 0; i < 15; i++) w().open("stats", {}, { id: `existing:${i}` });
    w().close("existing:7");
    const before = w();
    const id = w().open("library", {}, { id: "fresh" });
    expect(id).toBe("fresh");
    expect(w().windows["existing:7"]).toBeUndefined();
    expect(w().order).toEqual([...before.order, id]);
    expect(w().cycleOrder).toEqual([...before.cycleOrder, id]);
    expect(Object.keys(w().windows)).toHaveLength(15);
    for (const peer of before.order) expect(w().windows[peer]).toBe(before.windows[peer]);
  });
});

describe("windowsStore — cascade + reset", () => {
  it("cascades successive windows so they do not stack exactly", () => {
    const a = w().open("stats", {});
    const b = w().open("library", {});
    expect(w().windows[b].rect.x).not.toBe(w().windows[a].rect.x);
    expect(w().windows[b].rect.y).not.toBe(w().windows[a].rect.y);
  });

  it("reset wipes every window + resets focus + zCounter", () => {
    w().open("stats", {});
    w().open("library", {});
    w().reset();
    expect(Object.keys(w().windows)).toHaveLength(0);
    expect(w().order).toEqual([]);
    expect(w().focusedId).toBeNull();
    expect(w().zCounter).toBe(WINDOW_Z_BASE);
  });
});


describe("windowsStore stable cycle order", () => {
  function openIds(ids: string[]) { for (const id of ids) w().open("stats", { id }, { id }); }
  it("cycles backward across every member independently of z-order", () => {
    openIds(["10", "2", "é:opaque"]);
    for (const id of ["2", "10", "é:opaque", "2"]) {
      expect(w().cycleFocus(-1)).toBe(true); expect(w().focusedId).toBe(id);
      expect(w().cycleOrder).toEqual(["10", "2", "é:opaque"]);
      expect(w().order.at(-1)).toBe(id);
    }
  });
  it("preserves stable order on focus/reopen/geometry/mode and cycles forward", () => {
    openIds(["a", "b", "c", "d"]); w().focus("b"); w().open("stats", {}, { id: "a" });
    w().setRect("a", { x: 123 }); w().expand("a"); w().restore("a");
    expect(w().cycleOrder).toEqual(["a", "b", "c", "d"]);
    for (const id of ["b", "c", "d", "a"]) { expect(w().cycleFocus(1)).toBe(true); expect(w().focusedId).toBe(id); }
    expect(w().windows.a.rect.x).toBe(123);
  });
  it("removes closed members, appends reopens, and clears on reset", () => {
    openIds(["a", "b", "c"]); w().close("b"); expect(w().cycleOrder).toEqual(["a", "c"]);
    w().close("c"); expect(w().focusedId).toBe("a"); expect(w().cycleOrder).toEqual(["a"]);
    w().open("stats", {}, { id: "b" }); expect(w().cycleOrder).toEqual(["a", "b"]);
    w().close("absent"); expect(w().cycleOrder).toEqual(["a", "b"]);
    w().reset(); expect(w().cycleOrder).toEqual([]); expect(w().cycleFocus(1)).toBe(false);
  });
  it("appends new identities beyond eight without phantom or evicted cycle members", () => {
    const ids = Array.from({ length: MAX_WINDOWS }, (_, i) => `id:${i}`); openIds(ids);
    w().focus(ids[0]); const before = w();
    const result = w().open("stats", {}, { id: "new-window" });
    expect(result).toBe("new-window"); expect(w().cycleOrder).toEqual([...ids, "new-window"]);
    const legacy = w().open("stats", {}, { id: "legacy-window", replaceOldestAtLimit: true });
    expect(legacy).toBe("legacy-window");
    expect(w().cycleOrder).toEqual([...ids, "new-window", "legacy-window"]);
    expect(new Set(w().cycleOrder).size).toBe(ids.length + 2);
    expect([...w().cycleOrder].sort()).toEqual(Object.keys(w().windows).sort());
    for (const id of ids) expect(w().windows[id]).toBe(before.windows[id]);
    expect(w().cycleFocus(1)).toBe(true); expect(w().focusedId).toBe(ids[0]);
  });
  it("refuses empty/single/absent cursors without changing focus or z", () => {
    expect(w().cycleFocus(-1)).toBe(false); openIds(["a"]);
    const before = w().zCounter; expect(w().cycleFocus(1)).toBe(false); expect(w().zCounter).toBe(before);
    openIds(["b"]); useWindows.setState({ focusedId: null }); expect(w().cycleFocus(1)).toBe(false);
    useWindows.setState({ focusedId: "absent" }); expect(w().cycleFocus(-1)).toBe(false);
    expect(w().focusedId).toBe("absent");
  });
});
