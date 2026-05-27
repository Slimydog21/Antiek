/**
 * Home.test.tsx — SPR-12 M1 acceptance.
 *
 * Load-bearing claims:
 *  - a real branded home renders (not a placeholder);
 *  - ONE click reaches each of the four surfaces, at each surface's
 *    canonical door route (read from workflowTaxonomy, so a door re-home
 *    is honoured automatically);
 *  - biographies are featured AND honestly labelled (SPR-11's guided
 *    onboarding is not built, so the CTA goes to /speak — its real entry
 *    point today — and the copy says the full flow is still on its way).
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

  it("features biographies and labels the unbuilt SPR-11 flow honestly", () => {
    mount();
    const bio = screen.getByTestId("home-biographies");
    expect(bio).toBeTruthy();
    // Honest: the copy says the guided onboarding is not built yet.
    expect(bio.textContent).toMatch(/still on its way/i);
    // The CTA goes to the Speak door (the real entry point today), not a
    // faked SPR-11 route.
    fireEvent.click(screen.getByTestId("home-biographies-cta"));
    expect(screen.getByText(/SPEAK SURFACE/)).toBeTruthy();
  });
});
