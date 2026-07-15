/**
 * choreography.test.ts — the SPR-10 wiring (PRODUCT_ACTIVATE → waddle).
 *
 * Load-bearing claims:
 *  - a PRODUCT_ACTIVATE event is resolved to a control via data-product-id and
 *    drives stage.waddleToEl;
 *  - click === hotkey is STRUCTURAL: the SAME event with source:"click" and
 *    source:"hotkey" produces the IDENTICAL stage call (one event, one path);
 *  - a missing target resolves to null → waddleToEl(null) (the stage no-ops);
 *  - rapid activations all reach the stage (latest-wins is the stage's job,
 *    proven in WernerStage.test.ts) — the listener never drops or batches;
 *  - teardown removes the listener (no leak after unmount).
 *
 * The resolution-via-DOM contract is proven two ways: (1) a real injected
 * element carrying data-product-id resolved by the default DOM querySelector,
 * and (2) an injected resolver for the parity/interruption assertions.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  emitProductActivate,
  type ProductActivateDetail,
} from "../components/hotkeys";
import {
  installChoreography,
  installTargetChoreography,
  productSelector,
  WERNER_TARGET_ATTR,
} from "./choreography";
import type { WernerStageController } from "./WernerStage";

function fakeStage(): {
  stage: WernerStageController;
  waddleToEl: ReturnType<typeof vi.fn>;
} {
  const waddleToEl = vi.fn();
  const stage = {
    moveTo: vi.fn(),
    waddleToEl,
    emote: vi.fn(),
    follow: vi.fn(),
    idle: vi.fn(),
    freeze: vi.fn(),
    unfreeze: vi.fn(),
    getState: vi.fn(() => ({ name: "idle", resume: "idle" }) as const),
    dispose: vi.fn(),
  } as unknown as WernerStageController;
  return { stage, waddleToEl };
}

let teardown: () => void = () => {};

afterEach(() => {
  teardown();
  teardown = () => {};
  document.body.innerHTML = "";
});

describe("installChoreography — target resolution", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
  });

  it("resolves the activated control via [data-product-id] and waddles to it (real DOM)", () => {
    // A real injected element carrying the attribute the concurrent NavRail
    // sprint adds — this proves the document.querySelector contract.
    const btn = document.createElement("button");
    btn.setAttribute("data-product-id", "research");
    document.body.appendChild(btn);

    const { stage, waddleToEl } = fakeStage();
    teardown = installChoreography(stage);

    emitProductActivate({ productId: "research", source: "click" });
    expect(waddleToEl).toHaveBeenCalledTimes(1);
    expect(waddleToEl.mock.calls[0][0]).toBe(btn); // resolved the real element
  });

  it("productSelector builds the documented [data-product-id] contract", () => {
    expect(productSelector({ productId: "read", source: "click" })).toBe(
      '[data-product-id="read"]',
    );
  });

  it("missing target resolves to null → waddleToEl(null) (stage no-ops, no throw)", () => {
    const { stage, waddleToEl } = fakeStage();
    teardown = installChoreography(stage);
    expect(() =>
      emitProductActivate({ productId: "does-not-exist", source: "click" }),
    ).not.toThrow();
    expect(waddleToEl).toHaveBeenCalledTimes(1);
    expect(waddleToEl.mock.calls[0][0]).toBeNull();
  });
});

describe("installChoreography — click === hotkey parity (structural)", () => {
  it("a click and a hotkey produce the IDENTICAL stage call (same event, same path)", () => {
    const el = document.createElement("button");
    const { stage, waddleToEl } = fakeStage();
    const resolveTarget = vi.fn(() => el);
    teardown = installChoreography(stage, { resolveTarget });

    const detailClick: ProductActivateDetail = { productId: "write", source: "click" };
    const detailHotkey: ProductActivateDetail = { productId: "write", source: "hotkey" };

    emitProductActivate(detailClick);
    emitProductActivate(detailHotkey);

    expect(waddleToEl).toHaveBeenCalledTimes(2);
    // Both go to the SAME element with the SAME emote — identical reaction.
    // Write door → happy (living-TV product map).
    expect(waddleToEl.mock.calls[0]).toEqual([el, "happy"]);
    expect(waddleToEl.mock.calls[1]).toEqual([el, "happy"]);
    expect(waddleToEl.mock.calls[0]).toEqual(waddleToEl.mock.calls[1]);
  });

  it("maps product doors to distinct living-TV emotes", () => {
    const el = document.createElement("button");
    const { stage, waddleToEl } = fakeStage();
    teardown = installChoreography(stage, { resolveTarget: () => el });
    emitProductActivate({ productId: "research", source: "click" });
    emitProductActivate({ productId: "read", source: "click" });
    emitProductActivate({ productId: "home", source: "click" });
    expect(waddleToEl.mock.calls[0][1]).toBe("thinking");
    expect(waddleToEl.mock.calls[1][1]).toBe("curious");
    expect(waddleToEl.mock.calls[2][1]).toBe("happy");
  });
});

describe("installChoreography — interruption + teardown", () => {
  it("rapid activations each reach the stage (latest-wins handled downstream)", () => {
    const el = document.createElement("button");
    const { stage, waddleToEl } = fakeStage();
    teardown = installChoreography(stage, { resolveTarget: () => el });

    emitProductActivate({ productId: "research", source: "click" });
    emitProductActivate({ productId: "read", source: "hotkey" });
    emitProductActivate({ productId: "write", source: "click" });
    // The listener forwards every activation; the stage's single-timer
    // latest-wins (proven in WernerStage.test.ts) is what cancels the
    // in-flight walk. The listener must not drop or batch.
    expect(waddleToEl).toHaveBeenCalledTimes(3);
  });

  it("teardown removes the listener — no reaction after unmount", () => {
    const el = document.createElement("button");
    const { stage, waddleToEl } = fakeStage();
    const remove = installChoreography(stage, { resolveTarget: () => el });
    remove();
    emitProductActivate({ productId: "research", source: "click" });
    expect(waddleToEl).not.toHaveBeenCalled();
  });

  it("an activation with no productId is ignored", () => {
    const { stage, waddleToEl } = fakeStage();
    teardown = installChoreography(stage, { resolveTarget: () => null });
    // Dispatch a malformed event directly (no detail).
    window.dispatchEvent(new CustomEvent("antiek:product:activate"));
    expect(waddleToEl).not.toHaveBeenCalled();
  });
});

describe("installTargetChoreography — opt-in data-werner-target (SPR-10 M4)", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
  });

  it("clicking a [data-werner-target] element waddles to it (default hit emote)", () => {
    const { stage, waddleToEl } = fakeStage();
    const btn = document.createElement("button");
    btn.setAttribute(WERNER_TARGET_ATTR, "");
    document.body.appendChild(btn);
    teardown = installTargetChoreography(stage, { target: document });

    btn.click();
    expect(waddleToEl).toHaveBeenCalledTimes(1);
    expect(waddleToEl.mock.calls[0]).toEqual([btn, "hit"]);
  });

  it("a click on a DESCENDANT of an opt-in element resolves the opt-in ancestor + its named emote", () => {
    const { stage, waddleToEl } = fakeStage();
    const wrap = document.createElement("div");
    wrap.setAttribute(WERNER_TARGET_ATTR, "curious");
    const inner = document.createElement("span");
    wrap.appendChild(inner);
    document.body.appendChild(wrap);
    teardown = installTargetChoreography(stage, { target: document });

    inner.click(); // bubbles; closest() finds the opt-in ancestor
    expect(waddleToEl).toHaveBeenCalledTimes(1);
    expect(waddleToEl.mock.calls[0]).toEqual([wrap, "curious"]);
  });

  it("an unknown attribute value falls back to the hit emote", () => {
    const { stage, waddleToEl } = fakeStage();
    const btn = document.createElement("button");
    btn.setAttribute(WERNER_TARGET_ATTR, "not-an-emote");
    document.body.appendChild(btn);
    teardown = installTargetChoreography(stage, { target: document });

    btn.click();
    expect(waddleToEl.mock.calls[0]).toEqual([btn, "hit"]);
  });

  it("clicks outside any opt-in element are ignored", () => {
    const { stage, waddleToEl } = fakeStage();
    const plain = document.createElement("button");
    document.body.appendChild(plain);
    teardown = installTargetChoreography(stage, { target: document });

    plain.click();
    expect(waddleToEl).not.toHaveBeenCalled();
  });

  it("teardown removes the click listener", () => {
    const { stage, waddleToEl } = fakeStage();
    const btn = document.createElement("button");
    btn.setAttribute(WERNER_TARGET_ATTR, "");
    document.body.appendChild(btn);
    const remove = installTargetChoreography(stage, { target: document });
    remove();

    btn.click();
    expect(waddleToEl).not.toHaveBeenCalled();
  });
});
