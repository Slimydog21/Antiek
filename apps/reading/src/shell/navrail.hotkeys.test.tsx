/**
 * navrail.hotkeys.test.tsx — SPR-08 sharpen (BLOCKING 2 + 3).
 *
 * The verifier-critic found that (2) no on-bar button rendered a KeyChip, so
 * the operator's headline ask — "hotkeys shown on-screen" — was unmet, and (3)
 * no click path emitted the activation event, so click≡hotkey parity (which
 * SPR-10's penguin hard-depends on) was unproven (the old shortcuts test
 * "faked" the click by calling the emitter directly).
 *
 * This file asserts against a REAL rendered NavRail:
 *   - a KeyChip with the correct key text renders for at least one product;
 *   - a real DOM CLICK on a product button fires PRODUCT_ACTIVATE_EVENT on
 *     window with source:"click" and the correct productId;
 *   - each product button carries data-product-id (the SPR-10 geometry
 *     contract: the penguin resolves the button rect via that attribute).
 */
import { afterEach, beforeAll, describe, expect, it } from "vitest";
import { cleanup, render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { NavRail } from "./NavRail";
import {
  PRODUCT_ACTIVATE_EVENT,
  bindingForProduct,
  ariaBinding,
  type ProductActivateDetail,
} from "../components/hotkeys/bindings";

beforeAll(() => {
  if (!window.matchMedia) {
    Object.defineProperty(window, "matchMedia", {
      writable: true,
      configurable: true,
      value: (query: string) => ({
        matches: false,
        media: query,
        onchange: null,
        addEventListener: () => {},
        removeEventListener: () => {},
        addListener: () => {},
        removeListener: () => {},
        dispatchEvent: () => false,
      }),
    });
  }
});

afterEach(cleanup);

describe("NavRail SPR-08 — on-bar chips + click≡hotkey parity", () => {
  it("renders a single ⌘+key chip on the Research door (no chord, no 'then')", () => {
    render(
      <MemoryRouter>
        <NavRail />
      </MemoryRouter>,
    );
    const button = document.querySelector(
      '[data-product-id="research"]',
    ) as HTMLElement;
    expect(button).toBeTruthy();
    // SPR-08: bindingForProduct("research") === "mod+j" (the uniform ⌘+key
    // scheme; the old "g r" chord is gone). The chip announces the spoken
    // combo and renders ONE glyph group (no chord "then" separator).
    expect(bindingForProduct("research")!.spec).toBe("mod+j");
    const expectedAria = ariaBinding(bindingForProduct("research")!.spec);
    expect(expectedAria).toMatch(/^(Meta|Control)\+J$/);
    const chip = button.querySelector('[role="img"]') as HTMLElement;
    expect(chip, "the Research door must render an on-bar hotkey chip").toBeTruthy();
    expect(chip.getAttribute("aria-keyshortcuts")).toBe(expectedAria);
    // The chip is a single combo glyph (⌘J / CtrlJ) — NOT two chord keys,
    // and no "then" separator is rendered.
    expect(button.querySelector(".antiek-keychip__then")).toBeNull();
    expect(button.querySelector(".antiek-keychip__seq")).toBeNull();
    const glyphs = Array.from(
      button.querySelectorAll(".antiek-keychip__key"),
    ).map((k) => k.textContent);
    expect(glyphs).toHaveLength(1);
    expect(glyphs[0]).toContain("J");
  });

  it("stamps data-product-id on all four product doors (SPR-10 geometry contract)", () => {
    render(
      <MemoryRouter>
        <NavRail />
      </MemoryRouter>,
    );
    for (const pid of ["research", "read", "write", "speak"]) {
      expect(
        document.querySelector(`[data-product-id="${pid}"]`),
        `the ${pid} door must carry data-product-id so the penguin can resolve its rect`,
      ).toBeTruthy();
    }
  });

  it("a REAL click on a product door fires PRODUCT_ACTIVATE_EVENT with source:click + the right productId", () => {
    render(
      <MemoryRouter>
        <NavRail />
      </MemoryRouter>,
    );
    const fired: ProductActivateDetail[] = [];
    const listener = (e: Event) =>
      fired.push((e as CustomEvent<ProductActivateDetail>).detail);
    window.addEventListener(PRODUCT_ACTIVATE_EVENT, listener);

    // Click the actual Write button in the DOM (not the emitter directly).
    const writeButton = document.querySelector(
      '[data-product-id="write"]',
    ) as HTMLElement;
    expect(writeButton).toBeTruthy();
    fireEvent.click(writeButton);

    window.removeEventListener(PRODUCT_ACTIVATE_EVENT, listener);

    expect(fired).toHaveLength(1);
    expect(fired[0].source).toBe("click");
    expect(fired[0].productId).toBe("write");
    // The route the click navigated to is the same route the hotkey carries.
    expect(fired[0].route).toBe(bindingForProduct("write")!.route);
  });

  it("clicking More fires a routeless 'more' activation (it opens the launcher, not a nav)", () => {
    render(
      <MemoryRouter>
        <NavRail />
      </MemoryRouter>,
    );
    const fired: ProductActivateDetail[] = [];
    const listener = (e: Event) =>
      fired.push((e as CustomEvent<ProductActivateDetail>).detail);
    window.addEventListener(PRODUCT_ACTIVATE_EVENT, listener);

    fireEvent.click(screen.getByTitle(/More - all products/));

    window.removeEventListener(PRODUCT_ACTIVATE_EVENT, listener);

    expect(fired).toHaveLength(1);
    expect(fired[0].source).toBe("click");
    expect(fired[0].productId).toBe("more");
    expect(fired[0].route).toBeUndefined();
  });
});
