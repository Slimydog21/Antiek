/** threadScroll.test.ts — SPR-07 invariant 19 (patterns 13/16). */
import { describe, expect, it } from "vitest";

import { NEAR_END_PX, nearEnd, reduceFollow } from "./threadScroll";

describe("threadScroll", () => {
  it("nearEnd is strictly under 80 px from the bottom", () => {
    expect(NEAR_END_PX).toBe(80);
    expect(nearEnd({ scrollHeight: 1000, clientHeight: 400, scrollTop: 521 })).toBe(true); // 79 left
    expect(nearEnd({ scrollHeight: 1000, clientHeight: 400, scrollTop: 520 })).toBe(false); // 80 left
  });

  it("unfollows on pointerdown, touchstart and an upward wheel", () => {
    expect(reduceFollow(true, { type: "pointerdown" })).toBe(false);
    expect(reduceFollow(true, { type: "touchstart" })).toBe(false);
    expect(reduceFollow(true, { type: "wheel", deltaY: -1 })).toBe(false);
    expect(reduceFollow(true, { type: "wheel", deltaY: 1 })).toBe(true);
  });

  it("re-follows only on a downward scroll into nearEnd", () => {
    const far = { scrollHeight: 1000, clientHeight: 400, scrollTop: 100 };
    const near = { scrollHeight: 1000, clientHeight: 400, scrollTop: 560 };
    expect(reduceFollow(false, { type: "scroll", direction: "down", metrics: far })).toBe(false);
    expect(reduceFollow(false, { type: "scroll", direction: "up", metrics: near })).toBe(false);
    expect(reduceFollow(false, { type: "scroll", direction: "down", metrics: near })).toBe(true);
  });

  it("an upward scroll unfollows even inside the 80 px band (repair C8): a scrollbar or keyboard peek is a peek", () => {
    const near = { scrollHeight: 1000, clientHeight: 400, scrollTop: 590 }; // 10 px from the end
    expect(reduceFollow(true, { type: "scroll", direction: "up", metrics: near })).toBe(false);
    const far = { scrollHeight: 1000, clientHeight: 400, scrollTop: 100 };
    expect(reduceFollow(true, { type: "scroll", direction: "up", metrics: far })).toBe(false);
  });

  it("jump ⇒ following", () => {
    expect(reduceFollow(false, { type: "jump" })).toBe(true);
  });
});
