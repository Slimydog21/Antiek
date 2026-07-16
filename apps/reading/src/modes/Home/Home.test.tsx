/**
 * Home.test.tsx — SPR-12 M1 acceptance + Cycle 7 authored atmosphere.
 *
 * Load-bearing claims:
 *  - a real branded home renders (not a placeholder);
 *  - ONE click reaches each of the four surfaces, at each surface's
 *    canonical door route (read from workflowTaxonomy, so a door re-home
 *    is honoured automatically);
 *  - biographies are featured AND the CTA opens the dedicated /biography
 *    landing (SPR-11) — a template over research + writing + voices, not a
 *    separate place;
 *  - the knowledge-home artwork is wired as a decorative pointer-inert
 *    layer behind the GlassSurface (Cycle 7 authored atmosphere).
 */
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import Home from "./Home";
import { WORKFLOWS, WORKFLOW_ORDER } from "../../shell/workflowTaxonomy";

let reduceMotion = false;

// Home now lands through GlassSurface (SPR-03 M2 landing-glass), which reads
// prefers-reduced-motion via usePrefersReducedMotion → window.matchMedia.
// jsdom lacks matchMedia; stub the default (motion allowed → the glass variant
// renders). Mirrors the AppShell/GlassSurface suites' stub; weakens nothing.
beforeEach(() => {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    configurable: true,
    value: (query: string) => ({
      matches: query === "(prefers-reduced-motion: reduce)" && reduceMotion,
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

afterEach(() => {
  reduceMotion = false;
  cleanup();
});

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
        <Route path="/arcade" element={<div>ARCADE SURFACE</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("Home — authored environment (Cycle 7)", () => {
  it("renders the decorative environment image with the correct DOM contract", () => {
    mount();
    const img = screen.getByTestId("home-environment") as HTMLImageElement;
    expect(img).toBeTruthy();
    // Decorative: empty alt, aria-hidden
    expect(img.alt).toBe("");
    expect(img.getAttribute("aria-hidden")).toBe("true");
    // Pointer-inert: no pointer events, not draggable
    expect(img.className).toContain("pointer-events-none");
    expect(img.draggable).toBe(false);
    // Async decoding (non-blocking)
    expect(img.getAttribute("decoding")).toBe("async");
  });

  it("keeps the authored workbench on mobile and the full scene on wider screens", () => {
    mount();
    const img = screen.getByTestId("home-environment");
    expect(img.className).toContain("object-cover");
    expect(img.className).toContain("object-[24%_center]");
    expect(img.className).toContain("sm:object-center");
  });

  it("places the environment beneath the real GlassSurface scrim", () => {
    const { container } = mount();
    const img = screen.getByTestId("home-environment");
    const glass = container.querySelector("[data-glass-surface]");
    expect(glass, "GlassSurface must render").toBeTruthy();
    expect(glass!.contains(img)).toBe(false);
    expect(img.parentElement).toBe(glass!.parentElement);
    expect(img.className).toContain("absolute");
    expect(img.className).toContain("z-0");
    expect(glass!.className).toContain("z-10");
    expect(glass!.className).toContain("!backdrop-blur-none");
    expect(glass!.querySelector("[data-glass-scrim]")).toBeTruthy();
  });

  it("retains the static art while reduced motion invokes the solid contrast floor", () => {
    reduceMotion = true;
    mount();
    expect(screen.getByTestId("home-environment")).toBeTruthy();
    const glass = document.querySelector("[data-glass-surface]");
    expect(glass?.getAttribute("data-glass-surface")).toBe("solid");
    expect(glass?.querySelector("[data-glass-scrim]")).toBeNull();
  });
});

describe("Home (SPR-12 M1)", () => {
  it("renders a real branded home, not a placeholder", () => {
    mount();
    // The brand statement is present (a crafted sentence, not "TODO").
    expect(
      screen.getByText(/One workspace for everything you read/i),
    ).toBeTruthy();
    // Hero Werner — home of the penguin (UI-consumed, not inventory-only).
    expect(screen.getByTestId("home-werner-hero")).toBeTruthy();
    // Four equal door cards.
    const cards = screen.getByTestId("home-workflow-cards");
    expect(cards.querySelectorAll("button").length).toBe(WORKFLOW_ORDER.length);
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

  it("emits PRODUCT_ACTIVATE living-TV choreography before navigating each door", () => {
    const seen: string[] = [];
    const onAct = (e: Event) => {
      const id = (e as CustomEvent<{ productId?: string }>).detail?.productId;
      if (id) seen.push(id);
    };
    window.addEventListener("antiek:product:activate", onAct);
    for (const wf of WORKFLOW_ORDER) {
      cleanup();
      const { container } = mount();
      const card = container.querySelector<HTMLButtonElement>(
        `button[data-workflow="${wf}"]`,
      );
      expect(card?.getAttribute("data-product-id")).toBe(wf);
      fireEvent.click(card!);
    }
    window.removeEventListener("antiek:product:activate", onAct);
    for (const wf of WORKFLOW_ORDER) {
      expect(seen).toContain(wf);
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

  it("emits living-TV piece_started when starting a biography", () => {
    const seen: string[] = [];
    const onExp = (e: Event) => {
      const d = (e as CustomEvent<{ experience?: string }>).detail?.experience;
      if (d) seen.push(d);
    };
    window.addEventListener("antiek:werner-experience", onExp);
    mount();
    fireEvent.click(screen.getByTestId("home-biographies-cta"));
    window.removeEventListener("antiek:werner-experience", onExp);
    expect(seen).toContain("piece_started");
  });

  it("features Werner's arcade and opens /arcade in one click (opt-in mini-games)", () => {
    const seen: string[] = [];
    const onExp = (e: Event) => {
      const d = (e as CustomEvent<{ experience?: string }>).detail?.experience;
      if (d) seen.push(d);
    };
    window.addEventListener("antiek:werner-experience", onExp);
    mount();
    expect(screen.getByTestId("home-arcade")).toBeTruthy();
    // Session thinking brand chrome + igloo invent scene art (not inventory-only).
    expect(screen.getByTestId("home-arcade-werner-brand")).toBeTruthy();
    const igloo = screen.getByTestId("home-arcade-igloo-art") as HTMLImageElement;
    expect(igloo.getAttribute("src") ?? "").toMatch(
      /werner_igloo_arcade_session_v1/,
    );
    fireEvent.click(screen.getByTestId("home-arcade-cta"));
    expect(screen.getByText(/ARCADE SURFACE/)).toBeTruthy();
    expect(seen).toContain("highlight");
    window.removeEventListener("antiek:werner-experience", onExp);
  });
});

