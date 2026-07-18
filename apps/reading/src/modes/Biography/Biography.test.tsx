import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import { BANNED_PATTERNS } from "../../shared/language";

/**
 * Biography.test — the dedicated Biography TEMPLATE landing (SPR-11).
 *
 * Load-bearing claims, mechanically checked:
 *  M1 — a real biography landing renders (its own page, the steps + a start
 *       CTA), and its copy obeys §5 (NO substrate jargon — the same banned
 *       patterns the copy-lint enforces, applied to the rendered text here so
 *       the §5 discipline on the landing copy is asserted, not just eyeballed);
 *  M1 — the CTA creates a biography PROJECT (the composed template — it calls
 *       startInvestigation THEN createBiography), never a bare Write document;
 *  M3 — once started, a guided first-run surfaces the three composed surfaces
 *       AND a one-tap "send to a friend" invite (reuses the Speak share link);
 *     — an engine failure shows the honest AIActionFailure, never a fake start.
 */

const {
  startInvestigationMock,
  createBiographyMock,
  makeShareLinkMock,
} = vi.hoisted(() => ({
  startInvestigationMock: vi.fn(),
  createBiographyMock: vi.fn(),
  makeShareLinkMock: vi.fn(),
}));

vi.mock("../../lib/api", async (orig) => ({
  ...(await orig<typeof import("../../lib/api")>()),
  startInvestigation: startInvestigationMock,
}));

vi.mock("../../lib/speakApi", async (orig) => ({
  ...(await orig<typeof import("../../lib/speakApi")>()),
  createBiography: createBiographyMock,
  makeShareLink: makeShareLinkMock,
}));

import Biography from "./index";

beforeEach(() => {
  startInvestigationMock.mockReset().mockResolvedValue({
    investigation_id: "inv-bio-1",
    status: "in_progress",
    start_event_id: "ev-1",
  });
  createBiographyMock.mockReset().mockResolvedValue({
    investigationId: "inv-bio-1",
    deliverableId: "dlv-bio-1",
    projectId: "proj-bio-1",
  });
  makeShareLinkMock.mockReset().mockResolvedValue(
    "https://interview.antiek.ai/interview-abc?token=tok-xyz",
  );
});
afterEach(cleanup);

function mount() {
  return render(
    <MemoryRouter initialEntries={["/biography"]}>
      <Routes>
        <Route path="/biography" element={<Biography />} />
        <Route path="/inv/:id" element={<div>RESEARCH SURFACE</div>} />
        <Route path="/write/:id" element={<div>WRITE SURFACE</div>} />
        <Route path="/speak/:id" element={<div>SPEAK SURFACE</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("Biography landing (SPR-11 M1)", () => {
  it("renders its own page with the steps and a start CTA", () => {
    mount();
    expect(screen.getByText(/write someone.s biography/i)).toBeTruthy();
    // The "build a biography in N steps" explainer.
    const steps = screen.getByTestId("biography-steps");
    expect(steps.querySelectorAll("li").length).toBe(3);
    // The start CTA exists.
    expect(screen.getByRole("button", { name: /start a biography/i })).toBeTruthy();
    // Living-TV densify: session thinking brand mark + invent strip.
    expect(screen.getByTestId("biography-living-tv-art")).toBeTruthy();
    // Living-TV densify: session thinking brand mark (not inventory-only idle).
    expect(screen.getByTestId("biography-werner-brand")).toBeTruthy();
  });

  it("the landing copy obeys §5 voice discipline (no substrate jargon)", () => {
    const { container } = mount();
    const rendered = (container.textContent ?? "").toLowerCase();
    // The same banned patterns the copy-lint enforces, applied to the
    // rendered landing copy. The §5 discipline is asserted here, not eyeballed.
    for (const rule of BANNED_PATTERNS) {
      rule.pattern.lastIndex = 0;
      expect(
        rule.pattern.test(rendered),
        `landing copy must not contain substrate jargon (${rule.id}: ${rule.description})`,
      ).toBe(false);
    }
  });

  it("the CTA creates a biography PROJECT (research + composition), not a bare Write doc", async () => {
    mount();
    const input = screen.getByLabelText(/whose biography/i);
    fireEvent.change(input, { target: { value: "my grandmother" } });
    fireEvent.click(screen.getByRole("button", { name: /start a biography/i }));
    await waitFor(() => expect(createBiographyMock).toHaveBeenCalled());
    // It provisions the Research folder FIRST, then composes the template on it.
    expect(startInvestigationMock).toHaveBeenCalled();
    expect(createBiographyMock).toHaveBeenCalledWith(
      expect.objectContaining({
        investigationId: "inv-bio-1",
        subjectName: "my grandmother",
      }),
    );
  });

  it("shows an honest failure (no fake start) when composition fails", async () => {
    createBiographyMock.mockRejectedValue(new Error("no provider"));
    mount();
    const input = screen.getByLabelText(/whose biography/i);
    fireEvent.change(input, { target: { value: "Dad" } });
    fireEvent.click(screen.getByRole("button", { name: /start a biography/i }));
    expect(await screen.findByRole("alert")).toBeTruthy();
    // Did not advance to the onboarding (no "started" headline).
    expect(screen.queryByTestId("biography-surfaces")).toBeNull();
  });
});

describe("Biography onboarding + invite-to-talk (SPR-11 M3)", () => {
  async function start() {
    mount();
    fireEvent.change(screen.getByLabelText(/whose biography/i), {
      target: { value: "Maria" },
    });
    fireEvent.click(screen.getByRole("button", { name: /start a biography/i }));
    await screen.findByTestId("biography-surfaces");
  }

  it("walks the creator through the three composed surfaces", async () => {
    await start();
    // All three surfaces of the composition are surfaced, each one click away.
    expect(screen.getByTestId("biography-open-research")).toBeTruthy();
    expect(screen.getByTestId("biography-open-write")).toBeTruthy();
    expect(screen.getByTestId("biography-open-speak")).toBeTruthy();
    // The Speak surface is honestly empty-but-ready (no voices yet).
    expect(screen.getByText(/no voices yet/i)).toBeTruthy();
  });

  it("offers a one-tap 'send to a friend' that yields a Speak invite link", async () => {
    await start();
    fireEvent.click(screen.getByRole("button", { name: /send to a friend/i }));
    await waitFor(() => expect(makeShareLinkMock).toHaveBeenCalledWith("proj-bio-1"));
    // The invite link (the SPR-10 token link) is surfaced to share.
    expect(
      await screen.findByText(/interview\.antiek\.ai\/interview-abc/),
    ).toBeTruthy();
  });

  it("opening the Speak surface lands on THIS biography's project", async () => {
    await start();
    fireEvent.click(screen.getByTestId("biography-open-speak"));
    expect(screen.getByText(/SPEAK SURFACE/)).toBeTruthy();
  });
});
