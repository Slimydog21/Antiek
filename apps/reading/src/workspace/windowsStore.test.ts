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

describe("windowsStore — bounded fan-out (cap)", () => {
  it("caps at MAX_WINDOWS and does not exceed it", () => {
    const ids: string[] = [];
    for (let i = 0; i < MAX_WINDOWS + 4; i++) {
      ids.push(w().open("stats", {}, { id: `s${i}` }));
    }
    expect(w().order.length).toBe(MAX_WINDOWS);
    expect(Object.keys(w().windows).length).toBe(MAX_WINDOWS);
  });

  it("at the cap, opening focuses the oldest rather than creating a new window", () => {
    for (let i = 0; i < MAX_WINDOWS; i++) {
      w().open("stats", {}, { id: `s${i}` });
    }
    const oldest = w().order[0];
    const returned = w().open("library", {}, { id: "overflow" });
    expect(w().windows.overflow).toBeUndefined();
    // The overflow open returns the oldest id and focuses it.
    expect(returned).toBe(oldest);
    expect(w().focusedId).toBe(oldest);
  });

  it("freeing a slot lets a new window open again", () => {
    for (let i = 0; i < MAX_WINDOWS; i++) {
      w().open("stats", {}, { id: `s${i}` });
    }
    w().close("s0");
    const id = w().open("library", {}, { id: "fresh" });
    expect(w().windows.fresh).toBeDefined();
    expect(id).toBe("fresh");
    expect(w().order.length).toBe(MAX_WINDOWS);
  });

  it("can replace the oldest at the cap when exact asset identity is load-bearing", () => {
    for (let i = 0; i < MAX_WINDOWS; i++) {
      w().open("stats", {}, { id: `s${i}` });
    }
    const oldest = w().order[0];
    const returned = w().open(
      "reader",
      { documentId: "doc-9" },
      { id: "reader:doc-9", replaceOldestAtLimit: true },
    );

    expect(returned).toBe("reader:doc-9");
    expect(w().windows[oldest]).toBeUndefined();
    expect(w().windows[returned].payload).toEqual({ documentId: "doc-9" });
    expect(w().focusedId).toBe(returned);
    expect(w().order).toHaveLength(MAX_WINDOWS);
  });

  // AMS2-SPR-04: windows are now the DEFAULT, so the cap must hold on the hot
  // path. The MINIMAL over-cap case (MAX_WINDOWS + 1) is the load-bearing one:
  // the count never exceeds 8 and the over-cap open() returns the focused-oldest
  // id (a REAL id, never a phantom new window).
  it("opening MAX_WINDOWS + 1 never exceeds the cap and the +1 open returns the focused-oldest id", () => {
    const ids: string[] = [];
    for (let i = 0; i < MAX_WINDOWS; i++) {
      ids.push(w().open("stats", {}, { id: `s${i}` }));
    }
    const oldest = w().order[0];
    expect(oldest).toBe(ids[0]);

    // The (MAX_WINDOWS + 1)-th open — a fresh kind/id that WOULD be a new window.
    const returned = w().open("library", {}, { id: "overflow" });

    // No phantom: the over-cap window was never created.
    expect(w().windows.overflow).toBeUndefined();
    // Count is pinned at exactly the cap — never 9.
    expect(w().order.length).toBe(MAX_WINDOWS);
    expect(Object.keys(w().windows).length).toBe(MAX_WINDOWS);
    // open() returns the focused-oldest id (a real, existing id) ...
    expect(returned).toBe(oldest);
    expect(w().windows[returned]).toBeDefined();
    // ... and that oldest is now the focused + topmost window.
    expect(w().focusedId).toBe(oldest);
    expect(w().order[w().order.length - 1]).toBe(oldest);
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
