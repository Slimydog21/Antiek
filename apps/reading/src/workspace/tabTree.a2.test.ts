import { describe, expect, it } from "vitest";
import fixture from "../lib/api/__fixtures__/projectTabs.snapshot.json";
import { parseTabsSnapshot } from "../lib/api/projectTabs";
import { closeTab, emptyTabTree, setActive, spawnChild, undo } from "./tabTree";
import { fromWire, toWire } from "./tabTreeWire";

describe("A2 wire boundaries and pane selection", () => {
  it("right focus preserves the selected left document through save/reload", () => {
    const tree = fromWire(parseTabsSnapshot(fixture.expected), "research");
    const focused = setActive(tree, "t-thread");
    if (!focused.ok) throw new Error(focused.error.message);
    expect(toWire(focused.tree).active).toEqual(fixture.expected.active);
    const closed = closeTab(focused.tree, "t-thread", "lift_children", "2026-09-27T10:00:00Z");
    if (!closed.ok) throw new Error(closed.error.message);
    expect(toWire(closed.tree).active.left).toBe("t-agent-doc");
    const restored = undo(closed.tree, closed.undo);
    if (!restored.ok) throw new Error(restored.error.message);
    expect(toWire(restored.tree).active).toEqual(fixture.expected.active);
  });
  it.each(["root", "__proto__", "illegal:tab"])("refuses ambiguous or illegal id %s at fromWire", (id) => {
    const wire = structuredClone(fixture.expected);
    const node = wire.tree.nodes["t-agent-doc"];
    Object.defineProperty(wire.tree.nodes, id, { value: { ...node, tab_id: id }, enumerable: true });
    expect(() => fromWire(parseTabsSnapshot(wire), "research")).toThrow();
  });
  it("reserves root for the counter namespace when spawning", () => {
    expect(spawnChild(emptyTabTree("reading"), null, {
      tab_id: "root", kind: "reader", ref: "doc", mothership: "reading",
    }).ok).toBe(false);
  });
});
