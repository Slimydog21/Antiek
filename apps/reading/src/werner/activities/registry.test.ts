import { Children, type ReactElement, type ReactNode } from "react";
import { describe, expect, it } from "vitest";

import {
  getActivity,
  getDefaultActivity,
  iceFishingActivity,
  listActivities,
  registerActivity,
  type CursorInstrumentProps,
} from "./index";
import { WernerFishingLayer } from "../WernerFishingLayer";
import { WernerIceBait } from "../WernerIceBait";

/**
 * Registry unit tests — pinned against the REAL ice-fishing activity (no
 * invented placeholder). Importing "./index" self-registers ice-fishing as the
 * default, so these assertions run against the production catalog.
 */
describe("station activity registry", () => {
  it("getActivity('ice-fishing') returns the fishing activity", () => {
    expect(getActivity("ice-fishing")).toBe(iceFishingActivity);
  });

  it("listActivities() includes ice-fishing and is frozen", () => {
    const all = listActivities();
    expect(all).toContain(iceFishingActivity);
    expect(Object.isFrozen(all)).toBe(true);
  });

  it("ice-fishing is the default activity", () => {
    expect(getDefaultActivity()).toBe(iceFishingActivity);
  });

  it("registerActivity is idempotent for the same object", () => {
    const before = listActivities().filter((a) => a.id === "ice-fishing").length;
    // Re-register the SAME id — the catalog must not grow a duplicate entry.
    registerActivity(iceFishingActivity, { default: true });
    const after = listActivities().filter((a) => a.id === "ice-fishing").length;
    expect(before).toBe(1);
    expect(after).toBe(1);
    expect(getActivity("ice-fishing")).toBe(iceFishingActivity);
  });

  it("rejects a conflicting replacement for an existing id", () => {
    const conflicting = {
      ...iceFishingActivity,
      label: "Impostor fishing",
    };
    expect(() => registerActivity(conflicting)).toThrow(
      'Werner station: activity "ice-fishing" is already registered',
    );
    expect(getActivity("ice-fishing")).toBe(iceFishingActivity);
  });

  describe("ice-fishing activity shape (behavior-preservation pins)", () => {
    it("ambient: idleClass is the 'werner-fishing' gag, activeClass is null", () => {
      expect(iceFishingActivity.ambient.idleClass).toBe("werner-fishing");
      expect(iceFishingActivity.ambient.activeClass).toBeNull();
    });

    it("unlock kind is 'default'", () => {
      expect(iceFishingActivity.unlock).toEqual({ kind: "default" });
    });

    it("instrument reads exactly the cursor seam fields (no penguin state)", () => {
      expect(iceFishingActivity.instrument.reads).toEqual([
        "live",
        "pointerIdle",
        "tabHidden",
      ]);
    });

    it("instrument mounts the existing bait + fishing-line layers (reused verbatim)", () => {
      // Invoke the instrument's render and confirm it delegates to the SAME
      // components the shell used to hard-wire — proving reuse, not a rewrite.
      const render = iceFishingActivity.instrument.render as (
        props: CursorInstrumentProps,
      ) => ReactElement;
      const tree = render({ disabled: true });
      const children = Children.toArray(
        (tree.props as { children?: ReactNode }).children,
      ) as ReactElement[];
      const types = children.map((child) => child.type);
      expect(types).toContain(WernerFishingLayer);
      expect(types).toContain(WernerIceBait);
    });
  });
});
