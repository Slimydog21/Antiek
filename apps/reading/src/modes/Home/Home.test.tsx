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
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import Home from "./Home";
import { WORKFLOWS, WORKFLOW_ORDER } from "../../shell/workflowTaxonomy";

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
