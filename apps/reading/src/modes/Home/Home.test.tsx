/**
 * Home.test.tsx — SPR-12 M1 acceptance.
 *
 * Load-bearing claims:
 *  - a real branded home renders (not a placeholder);
 *  - ONE click reaches each of the four surfaces, at each surface's
 *    canonical door route (read from workflowTaxonomy, so a door re-home
 *    is honoured automatically);
 *  - biographies are featured AND the CTA opens the dedicated /biography
 *    landing (SPR-11) — a template over research + writing + voices, not a
 *    separate place.
 */
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import Home from "./Home";
import { WORKFLOWS, WORKFLOW_ORDER } from "../../shell/workflowTaxonomy";

// Home now lands through GlassSurface (SPR-03 M2 landing-glass), which reads
// prefers-reduced-motion via usePrefersReducedMotion → window.matchMedia.
// jsdom lacks matchMedia; stub the default (motion allowed → the glass variant
// renders). Mirrors the AppShell/GlassSurface suites' stub; weakens nothing.
beforeEach(() => {
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
});

afterEach(cleanup);

function mount() {
  return render(
    <MemoryRouter initialEntries={["/home"]}>
      <Routes>
        <Route path="/home" element={<Home />} />
        {/* Targets every door could land on — each renders a sentinel so
            we can assert the navigation actually happened in one click. */}
        <Route path="/" element={<div>RESEARCH SURFACE</div>} />
        <Route path="/library" element={<div>READ SURFACE</div>} />
        <Route path="/write" element={<div>WRITE SURFACE</div>} />
        <Route path="/speak" element={<div>SPEAK SURFACE</div>} />
        <Route path="/biography" element={<div>BIOGRAPHY SURFACE</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("Home (SPR-12 M1)", () => {
  it("renders a real branded home, not a placeholder", () => {
    mount();
    // The brand statement is present (a crafted sentence, not "TODO").
    expect(
      screen.getByText(/One workspace for everything you read/i),
    ).toBeTruthy();
    // Four equal door cards.
    const cards = screen.getByTestId("home-workflow-cards");
    expect(cards.querySelectorAll("button").length).toBe(WORKFLOW_ORDER.length);
    expect(cards.getAttribute("data-campus-map")).not.toBeNull();
  });

  it("keeps taxonomy order as DOM and keyboard order regardless of desktop placement", () => {
    const { container } = mount();
    const buttons = Array.from(
      container.querySelectorAll<HTMLButtonElement>(
        '[data-campus-map] button[data-workflow]',
      ),
    );
    expect(buttons.map((button) => button.dataset.workflow)).toEqual([
      ...WORKFLOW_ORDER,
    ]);
    expect(buttons.every((button) => button.tabIndex === 0)).toBe(true);
    expect(buttons.map((button) => button.textContent)).toEqual(
      expect.arrayContaining([
        expect.stringContaining("Research"),
        expect.stringContaining("Read"),
        expect.stringContaining("Write"),
        expect.stringContaining("Speak"),
      ]),
    );
  });

  it("treats the authored campus as decorative and keeps every door usable if it fails", () => {
    const { container } = mount();
    const image = container.querySelector<HTMLImageElement>(
      '[data-campus-map] img',
    );
    expect(image).toBeTruthy();
    expect(image!.alt).toBe("");
    expect(image!.getAttribute("aria-hidden")).toBe("true");
    expect(image!.className).toContain("pointer-events-none");

    fireEvent.error(image!);
    expect(container.querySelector('[data-campus-map] img')).toBeNull();
    expect(
      container.querySelectorAll('[data-campus-map] button[data-workflow]'),
    ).toHaveLength(WORKFLOW_ORDER.length);

    fireEvent.click(
      container.querySelector<HTMLButtonElement>(
        '[data-campus-map] button[data-workflow="research"]',
      )!,
    );
    expect(screen.getByText(/RESEARCH SURFACE/)).toBeTruthy();
  });

  it("lands the front door as a LANDING-GLASS surface (SPR-03 M2 occlusion contract)", () => {
    // The occlusion audit (docs/ams-v2/spr-03-occlusion-audit.md §3, item 2)
    // classifies Home landing-glass: the scene must show through. A refactor that
    // swapped it back to an opaque body (or to variant="solid") would re-occlude
    // the mountain on /home and this assertion catches it (rigor #5 — the variant
    // contract is enforced per-route, not only on / by the scene gate). With
    // motion allowed (the matchMedia stub above), the glass variant renders glass.
    const { container } = mount();
    const surface = container.querySelector("[data-glass-surface]");
    expect(surface, "Home must render through GlassSurface").toBeTruthy();
    expect(surface!.getAttribute("data-glass-variant")).toBe("glass");
    expect(surface!.getAttribute("data-glass-surface")).toBe("glass");
  });

  it("one click reaches each of the four surfaces at its canonical door", () => {
    // research → "/", read → "/library", write → "/write", speak → "/speak"
    const expectedSentinel: Record<string, RegExp> = {
      research: /RESEARCH SURFACE/,
      read: /READ SURFACE/,
      write: /WRITE SURFACE/,
      speak: /SPEAK SURFACE/,
    };
    for (const wf of WORKFLOW_ORDER) {
      cleanup();
      const { container } = mount();
      const card = container.querySelector<HTMLButtonElement>(
        `button[data-workflow="${wf}"]`,
      );
      expect(card, `the ${wf} door card must render`).toBeTruthy();
      fireEvent.click(card!);
      expect(
        screen.getByText(expectedSentinel[wf]),
        `clicking ${wf} must land on ${WORKFLOWS[wf].defaultRoute} in one click`,
      ).toBeTruthy();
    }
  });

  it("features biographies and opens the dedicated /biography landing (SPR-11)", () => {
    mount();
    const bio = screen.getByTestId("home-biographies");
    expect(bio).toBeTruthy();
    // The CTA opens the dedicated biography landing in one click.
    fireEvent.click(screen.getByTestId("home-biographies-cta"));
    expect(screen.getByText(/BIOGRAPHY SURFACE/)).toBeTruthy();
  });
});
