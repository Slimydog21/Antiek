import { beforeEach, describe, expect, it } from "vitest";

import { useWorkspace } from "./WorkspaceStore";

/** Convenience accessor — same pattern the real components use. */
const s = () => useWorkspace.getState();

beforeEach(() => {
  s().reset();
});

describe("WorkspaceStore — open + close", () => {
  it("opens a floating panel by default", () => {
    const id = s().open("FakeSidebar", {});
    expect(s().panels[id].mode).toBe("floating");
    expect(s().floatingIds).toContain(id);
    expect(s().dockLeftIds).not.toContain(id);
  });

  it("opens with explicit mode + custom id", () => {
    s().open("FakeSidebar", {}, { mode: "docked-left", id: "sb" });
    expect(s().panels.sb.mode).toBe("docked-left");
    expect(s().dockLeftIds).toEqual(["sb"]);
  });

  it("ignores duplicate id (does not double-insert)", () => {
    s().open("FakeChat", {}, { id: "chat" });
    s().open("FakeChat", {}, { id: "chat" });
    expect(s().floatingIds.filter((x) => x === "chat")).toHaveLength(1);
    expect(Object.keys(s().panels)).toHaveLength(1);
  });

  it("closes a panel and removes it from every array", () => {
    const a = s().open("FakeChat", {});
    const b = s().open("FakeNotebook", {}, { mode: "docked-right" });
    s().close(a);
    expect(s().panels[a]).toBeUndefined();
    expect(s().floatingIds).not.toContain(a);
    expect(s().panels[b]).toBeDefined();
  });

  it("clears focusedPanelId when the focused panel closes", () => {
    const id = s().open("FakeChat", {});
    s().focus(id);
    expect(s().focusedPanelId).toBe(id);
    s().close(id);
    expect(s().focusedPanelId).toBeNull();
  });

  it("opening a floating panel sets it as focused", () => {
    const id = s().open("FakeNotebook", {});
    expect(s().focusedPanelId).toBe(id);
  });
});

describe("WorkspaceStore — setMode", () => {
  it("moves a floating panel into the left dock", () => {
    const id = s().open("FakeSidebar", {});
    s().setMode(id, "docked-left");
    expect(s().panels[id].mode).toBe("docked-left");
    expect(s().dockLeftIds).toContain(id);
    expect(s().floatingIds).not.toContain(id);
  });

  it("moves a docked panel into floating + z-bumps", () => {
    const id = s().open("FakeChat", {}, { mode: "docked-right" });
    const zBefore = s().zCounter;
    s().setMode(id, "floating");
    expect(s().panels[id].mode).toBe("floating");
    expect(s().panels[id].zIndex).toBeGreaterThan(zBefore);
    expect(s().floatingIds).toContain(id);
    expect(s().dockRightIds).not.toContain(id);
  });

  it("popout removes from in-tab arrays but keeps the descriptor", () => {
    const id = s().open("FakeNotebook", {});
    s().setMode(id, "popout");
    expect(s().panels[id].mode).toBe("popout");
    expect(s().floatingIds).not.toContain(id);
    expect(s().dockLeftIds).not.toContain(id);
    expect(s().dockRightIds).not.toContain(id);
  });

  it("setMode on a missing id is a no-op", () => {
    const before = s();
    s().setMode("nonexistent", "floating");
    expect(s()).toEqual(before);
  });
});

describe("WorkspaceStore — bringToFront + focus", () => {
  it("bringToFront raises the panel above existing floating panels", () => {
    const a = s().open("FakeSidebar", {});
    const b = s().open("FakeNotebook", {});
    expect(s().panels[a].zIndex).toBeLessThan(s().panels[b].zIndex);
    s().bringToFront(a);
    expect(s().panels[a].zIndex).toBeGreaterThan(s().panels[b].zIndex);
    expect(s().focusedPanelId).toBe(a);
    // floatingIds last entry is the topmost
    expect(s().floatingIds[s().floatingIds.length - 1]).toBe(a);
  });

  it("focus on a floating panel raises it", () => {
    const a = s().open("FakeSidebar", {});
    const b = s().open("FakeNotebook", {});
    s().focus(a);
    expect(s().focusedPanelId).toBe(a);
    expect(s().panels[a].zIndex).toBeGreaterThan(s().panels[b].zIndex);
  });

  it("focus on a docked panel sets focus without z-bump", () => {
    const id = s().open("FakeSidebar", {}, { mode: "docked-left" });
    const zBefore = s().panels[id].zIndex;
    s().focus(id);
    expect(s().focusedPanelId).toBe(id);
    expect(s().panels[id].zIndex).toBe(zBefore);
  });
});

describe("WorkspaceStore — setRect, setSize, reorderDock", () => {
  it("setRect updates floating position", () => {
    const id = s().open("FakeNotebook", {});
    s().setRect(id, { x: 50, y: 50 });
    expect(s().panels[id].rect.x).toBe(50);
    expect(s().panels[id].rect.y).toBe(50);
  });

  it("setRect is a no-op on docked panels (rect is floating-only)", () => {
    const id = s().open("FakeSidebar", {}, { mode: "docked-left" });
    const before = s().panels[id].rect;
    s().setRect(id, { x: 999 });
    expect(s().panels[id].rect).toEqual(before);
  });

  it("setSize updates docked size hint", () => {
    const id = s().open("FakeSidebar", {}, { mode: "docked-left" });
    s().setSize(id, { width: 400 });
    expect(s().panels[id].size.width).toBe(400);
  });

  it("reorderDock swaps two items in the left dock", () => {
    s().open("FakeSidebar", {}, { mode: "docked-left", id: "a" });
    s().open("FakeChat", {}, { mode: "docked-left", id: "b" });
    s().open("FakeNotebook", {}, { mode: "docked-left", id: "c" });
    s().reorderDock("left", 0, 2);
    expect(s().dockLeftIds).toEqual(["b", "c", "a"]);
  });
});

describe("WorkspaceStore — docked-bottom (S5)", () => {
  it("opens a panel directly into the bottom dock", () => {
    const id = s().open("FakeChat", {}, { mode: "docked-bottom" });
    expect(s().panels[id].mode).toBe("docked-bottom");
    expect(s().dockBottomIds).toContain(id);
    expect(s().floatingIds).not.toContain(id);
  });

  it("setMode moves a floating panel to docked-bottom and back", () => {
    const id = s().open("FakeChat", {});
    s().setMode(id, "docked-bottom");
    expect(s().dockBottomIds).toContain(id);
    expect(s().floatingIds).not.toContain(id);
    s().setMode(id, "floating");
    expect(s().floatingIds).toContain(id);
    expect(s().dockBottomIds).not.toContain(id);
  });

  it("close removes a docked-bottom panel from the array", () => {
    const id = s().open("FakeChat", {}, { mode: "docked-bottom" });
    s().close(id);
    expect(s().dockBottomIds).not.toContain(id);
  });

  it("reorderDock('bottom', …) reorders bottom dock entries", () => {
    s().open("FakeChat", {}, { mode: "docked-bottom", id: "x" });
    s().open("FakeChat", {}, { mode: "docked-bottom", id: "y" });
    s().reorderDock("bottom", 0, 1);
    expect(s().dockBottomIds).toEqual(["y", "x"]);
  });

  it("setDockBottomHeight clamps to 120..60% viewport", () => {
    s().setDockBottomHeight(50);
    expect(s().dockBottomHeight).toBe(120);
    s().setDockBottomHeight(100_000);
    // 60% of jsdom default 768 = 460
    expect(s().dockBottomHeight).toBeLessThanOrEqual(800);
    s().setDockBottomHeight(260);
    expect(s().dockBottomHeight).toBe(260);
  });
});

describe("WorkspaceStore — pin + unpin + reset", () => {
  it("pin marks the panel as pinned", () => {
    const id = s().open("FakeChat", {});
    expect(s().panels[id].pinned).toBe(false);
    s().pin(id);
    expect(s().panels[id].pinned).toBe(true);
    s().unpin(id);
    expect(s().panels[id].pinned).toBe(false);
  });

  it("reset clears every panel + arrays + counters", () => {
    s().open("FakeChat", {}, { mode: "docked-bottom" });
    s().open("FakeSidebar", {}, { mode: "docked-left" });
    s().reset();
    expect(Object.keys(s().panels)).toHaveLength(0);
    expect(s().floatingIds).toEqual([]);
    expect(s().dockLeftIds).toEqual([]);
    expect(s().dockRightIds).toEqual([]);
    expect(s().dockBottomIds).toEqual([]);
    expect(s().focusedPanelId).toBeNull();
    expect(s().zCounter).toBe(1);
    expect(s().dockBottomHeight).toBe(220);
  });
});


describe("WorkspaceStore — zoom (herdr transfer P1)", () => {
  it("starts unzoomed", () => {
    expect(s().zoomedPanelId).toBeNull();
  });

  it("toggleZoom focuses and marks a panel", () => {
    const id = s().open("FakeSidebar", {});
    s().toggleZoom(id);
    expect(s().zoomedPanelId).toBe(id);
    expect(s().focusedPanelId).toBe(id);
  });

  it("toggleZoom on the same panel exits zoom", () => {
    const id = s().open("FakeSidebar", {});
    s().toggleZoom(id);
    s().toggleZoom(id);
    expect(s().zoomedPanelId).toBeNull();
  });

  it("toggleZoom(null) exits zoom", () => {
    const id = s().open("FakeSidebar", {});
    s().toggleZoom(id);
    s().toggleZoom(null);
    expect(s().zoomedPanelId).toBeNull();
  });

  it("toggleZoom on a missing panel exits zoom (never dangles)", () => {
    const id = s().open("FakeSidebar", {});
    s().toggleZoom(id);
    s().toggleZoom("nope");
    expect(s().zoomedPanelId).toBeNull();
  });

  it("closing the zoomed panel clears zoom", () => {
    const id = s().open("FakeSidebar", {});
    s().toggleZoom(id);
    s().close(id);
    expect(s().zoomedPanelId).toBeNull();
  });

  it("closing another panel keeps zoom", () => {
    const a = s().open("FakeSidebar", {});
    const b = s().open("FakeChat", {});
    s().toggleZoom(a);
    s().close(b);
    expect(s().zoomedPanelId).toBe(a);
  });

  it("reset clears zoom", () => {
    const id = s().open("FakeSidebar", {});
    s().toggleZoom(id);
    s().reset();
    expect(s().zoomedPanelId).toBeNull();
  });
});
