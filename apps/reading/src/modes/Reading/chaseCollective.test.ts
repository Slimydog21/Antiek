import { describe, expect, it } from "vitest";

import {
  canDraftCollective,
  collectiveDraftTitle,
  selectedReadyIds,
  toggleChaseSelection,
} from "./chaseCollective";

describe("chaseCollective pure selection", () => {
  it("toggles membership without duplicates", () => {
    expect(toggleChaseSelection([], "a")).toEqual(["a"]);
    expect(toggleChaseSelection(["a"], "b").sort()).toEqual(["a", "b"]);
    expect(toggleChaseSelection(["a", "b"], "a")).toEqual(["b"]);
    expect(toggleChaseSelection(["a"], "a")).toEqual([]);
  });

  it("defaults empty selection to all ready ids (order preserved)", () => {
    expect(selectedReadyIds([], ["b", "a"])).toEqual(["b", "a"]);
  });

  it("intersects selection with ready, preserving ready order", () => {
    expect(selectedReadyIds(["a", "c", "ghost"], ["b", "a", "c"])).toEqual([
      "a",
      "c",
    ]);
  });

  it("returns empty when nothing ready", () => {
    expect(selectedReadyIds(["a"], [])).toEqual([]);
  });

  it("requires ≥2 members for draft collective", () => {
    expect(canDraftCollective([])).toBe(false);
    expect(canDraftCollective(["a"])).toBe(false);
    expect(canDraftCollective(["a", "b"])).toBe(true);
  });

  it("titles honestly for default vs subset vs too-few", () => {
    expect(collectiveDraftTitle(["a"], 3)).toMatch(/at least two/i);
    expect(collectiveDraftTitle(["a", "b"], 3)).toMatch(/2 selected/i);
    expect(collectiveDraftTitle(["a", "b", "c"], 3)).toMatch(/completed chase artifacts/i);
  });
});
