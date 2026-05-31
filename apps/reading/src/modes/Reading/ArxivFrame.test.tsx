/**
 * ArxivFrame.test.tsx — Read SPR-05 M2 acceptance.
 *
 * The T2/T3 link-back surface. These tests pin the RELIABLE invariants:
 *  - the link card (button + anchor) is the primary surface and is always
 *    rendered, pointing at the gate-served canonical arxiv.org URL;
 *  - the iframe src, if present, is the arxiv.org URL DIRECTLY — Antiek never
 *    proxies arXiv bytes (no Antiek-origin URL is ever the frame/link target);
 *  - the best-effort frame falls back to the card on timeout (arxiv.org
 *    generally refuses framing). We inject a tiny frameTimeoutMs and assert the
 *    component settles to the `fallback` state, hiding the iframe.
 *
 * HONESTY: real cross-origin framing cannot be exercised under jsdom (no
 * network, no real frame navigation). We test the STATE MACHINE (trying →
 * fallback on timeout) deterministically with a fake timer + an injected
 * timeout; live arxiv.org framing is an operator live-check, not a unit test.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, render } from "@testing-library/react";

import ArxivFrame from "./ArxivFrame";

// Timer isolation (defensive, both directions). ArxivFrame mounts a real
// setTimeout(frameTimeoutMs) settle. Under vitest's parallel worker pool a
// SIBLING test file that installs vi.useFakeTimers() and exits a path without
// restoring can leak a faked clock into this file's worker, which would let the
// component's settle pre-fire (or never fire) and flap the "trying"-state iframe
// assertions — a cross-file flake, not a component defect. beforeEach pins REAL
// timers so every test starts from a known clock regardless of a sibling's leak;
// afterEach restores real timers so this file never leaks fake timers outward
// (the one fake-timer test below also restores in its own finally). This makes
// the file deterministic in isolation and under any co-scheduling.
beforeEach(() => {
  vi.useRealTimers();
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

const ARXIV = "https://arxiv.org/abs/2401.12345";

describe("ArxivFrame", () => {
  it("renders the reliable link card pointing at the canonical arxiv.org URL", () => {
    const { container, getByText } = render(
      <ArxivFrame canonicalUrl={ARXIV} title="A Paper" author="Dr. X" tier="T2" />,
    );
    // The frame container exists and carries the canonical target on a DOM-
    // inspectable data attr (the rights/network invariant point — the bare
    // full-URL anchor was trimmed, so this + the CTA are how the target shows).
    const section = container.querySelector("[data-arxiv-frame]") as HTMLElement;
    expect(section).toBeTruthy();
    expect(section.getAttribute("data-canonical-url")).toBe(ARXIV);
    // The "Read on arXiv" CTA is present (the single surfaced arXiv link here).
    expect(getByText(/Read on arXiv/)).toBeTruthy();
  });

  it("the iframe src is arxiv.org directly — Antiek never proxies the bytes", () => {
    const { container } = render(
      <ArxivFrame canonicalUrl={ARXIV} title="A Paper" author={null} tier="T3" />,
    );
    // On the initial "trying" render the iframe IS mounted (hidden) — assert it
    // UNCONDITIONALLY so a missing iframe FAILS the test (the prior `if (iframe)`
    // wrapper made this assertion vacuous: it passed if the iframe was absent).
    const iframe = container.querySelector("iframe") as HTMLIFrameElement;
    expect(iframe).toBeTruthy();
    // Its src is the arxiv URL — never an Antiek-origin proxy URL.
    expect(iframe.getAttribute("src")).toBe(ARXIV);
    expect(iframe.getAttribute("src")).not.toContain("antiek");
    expect(iframe.getAttribute("src")).not.toMatch(/\/api\//);
    // The canonical target on the section also points at arxiv.org, not a proxy.
    const target = (container.querySelector("[data-arxiv-frame]") as HTMLElement).getAttribute(
      "data-canonical-url",
    );
    expect(target).toBe(ARXIV);
    expect(target).not.toContain("antiek");
  });

  it("settles to the fallback card (frame hidden) on an iframe error event", () => {
    const { container } = render(
      <ArxivFrame canonicalUrl={ARXIV} title="A Paper" author={null} tier="T2" />,
    );
    const iframe = container.querySelector("iframe") as HTMLIFrameElement;
    expect(iframe).toBeTruthy();
    // The browser failing to load the frame (e.g. arxiv.org's X-Frame-Options
    // refusal surfacing as an error) settles to the reliable card.
    act(() => {
      iframe.dispatchEvent(new Event("error"));
    });
    expect(
      container.querySelector("[data-frame-state]")?.getAttribute("data-frame-state"),
    ).toBe("fallback");
    // The iframe is removed; the link card (CTA + canonical target) remains.
    expect(container.querySelector("iframe")).toBeNull();
    expect(
      (container.querySelector("[data-arxiv-frame]") as HTMLElement).getAttribute(
        "data-canonical-url",
      ),
    ).toBe(ARXIV);
  });

  it("falls back to the link card (hides the iframe) when the frame does not load in time", () => {
    vi.useFakeTimers();
    try {
      const { container, getByText } = render(
        <ArxivFrame canonicalUrl={ARXIV} title="A Paper" author={null} tier="T2" frameTimeoutMs={50} />,
      );
      // Initially trying (iframe mounted hidden).
      expect(container.querySelector("[data-frame-state]")?.getAttribute("data-frame-state")).toBe(
        "trying",
      );
      // Advance past the grace period → settle on the card, iframe removed.
      act(() => {
        vi.advanceTimersByTime(60);
      });
      expect(container.querySelector("[data-frame-state]")?.getAttribute("data-frame-state")).toBe(
        "fallback",
      );
      expect(container.querySelector("iframe")).toBeNull();
      // The link card is still the surface: the CTA + the canonical target on
      // the section persist (the bare full-URL anchor was trimmed).
      expect(getByText(/Read on arXiv/)).toBeTruthy();
      expect(
        (container.querySelector("[data-arxiv-frame]") as HTMLElement).getAttribute(
          "data-canonical-url",
        ),
      ).toBe(ARXIV);
    } finally {
      vi.useRealTimers();
    }
  });

  it("reveals the frame when it genuinely loads (the rare success path)", () => {
    const { container } = render(
      <ArxivFrame canonicalUrl={ARXIV} title="A Paper" author={null} tier="T3" />,
    );
    const iframe = container.querySelector("iframe") as HTMLIFrameElement;
    expect(iframe).toBeTruthy();
    act(() => {
      iframe.dispatchEvent(new Event("load"));
    });
    expect(container.querySelector("[data-frame-state]")?.getAttribute("data-frame-state")).toBe(
      "loaded",
    );
    // The iframe is now visible (not hidden) and still points at arxiv.org.
    const shown = container.querySelector("iframe") as HTMLIFrameElement;
    expect(shown.className).not.toContain("hidden");
    expect(shown.getAttribute("src")).toBe(ARXIV);
  });
});
