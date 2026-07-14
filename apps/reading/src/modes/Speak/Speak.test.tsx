import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

/**
 * Speak.test — the project page (Product Depth SPR-08 M2 + M4).
 *
 * Load-bearing claims:
 *  - one shareable invite link (the warm flow);
 *  - arriving voices render;
 *  - "what everyone agrees on" is framed as corroborated, NEVER "proven";
 *    a disagreement is shown, not hidden;
 *  - the assembling story shows the Werner-thinking beat, then an honest
 *    no-result (AIActionFailure) without keys — never a fabricated biography;
 *  - economics/publishing live behind ONE Settings tap; the split is shown,
 *    nothing disburses (no money/publish path fires from the page itself).
 */

const api = vi.hoisted(() => ({
  getProject: vi.fn(),
  getEconomics: vi.fn(),
  listVoices: vi.fn(),
  makeShareLink: vi.fn(),
  inviteByEmail: vi.fn(),
  whatEveryoneAgreesOn: vi.fn(),
  assembleDraft: vi.fn(),
}));

vi.mock("../../lib/speakApi", async (orig) => ({
  ...(await orig<typeof import("../../lib/speakApi")>()),
  ...api,
}));

// The page calls apiFetch directly only for the gated publish/book actions.
const apiFetchMock = vi.hoisted(() => vi.fn());
vi.mock("../../lib/api", async (orig) => ({
  ...(await orig<typeof import("../../lib/api")>()),
  apiFetch: apiFetchMock,
}));

import Speak from "./index";

const wernerListeners = new Set<EventListener>();

function listenForWerner(listener: EventListener): void {
  wernerListeners.add(listener);
  window.addEventListener("antiek:werner-experience", listener);
}

beforeEach(() => {
  api.getProject.mockReset().mockResolvedValue({
    id: "p1", name: "Grandma Rosa", willBePublic: false, subjectStatusWord: "deceased",
  });
  api.getEconomics.mockReset().mockResolvedValue({ splitApplies: false, creatorCarriesCost: true });
  api.listVoices.mockReset().mockResolvedValue([]);
  api.makeShareLink.mockReset().mockResolvedValue("https://antiek.ai/speak/invite/tok-xyz");
  api.inviteByEmail.mockReset();
  api.whatEveryoneAgreesOn.mockReset();
  api.assembleDraft.mockReset();
  apiFetchMock.mockReset();
  // jsdom clipboard stub
  Object.assign(navigator, { clipboard: { writeText: vi.fn().mockResolvedValue(undefined) } });
  // Speak now lands through GlassSurface (SPR-03 M2 landing-glass), which reads
  // prefers-reduced-motion via window.matchMedia. jsdom lacks it; stub the
  // default (motion allowed → the glass variant renders). Weakens nothing.
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
afterEach(() => {
  try {
    cleanup();
  } finally {
    for (const listener of wernerListeners) {
      window.removeEventListener("antiek:werner-experience", listener);
    }
    wernerListeners.clear();
  }
});

function mount() {
  return render(
    <MemoryRouter initialEntries={["/speak/p1"]}>
      <Routes>
        <Route path="/speak/:projectId" element={<Speak />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("Speak project page", () => {
  it("reacts only after an email invitation is committed", async () => {
    let resolveInvite!: () => void;
    api.inviteByEmail.mockReturnValue(
      new Promise<void>((resolve) => { resolveInvite = resolve; }),
    );
    const seen: string[] = [];
    const listener = (event: Event) => {
      seen.push((event as CustomEvent).detail?.experience);
    };
    listenForWerner(listener);

    mount();
    await screen.findByText("Grandma Rosa");
    fireEvent.click(screen.getByText(/or invite someone by email/i));
    fireEvent.change(screen.getByPlaceholderText("friend@example.com"), {
      target: { value: "friend@example.com" },
    });
    fireEvent.click(screen.getByRole("button", { name: /send invite/i }));
    expect(api.inviteByEmail).toHaveBeenCalledWith("p1", "friend@example.com");
    expect(seen).toEqual([]);

    resolveInvite();
    await waitFor(() => expect(seen).toEqual(["speak_invite_committed"]));
  });

  it("stays silent when an email invitation is rejected", async () => {
    api.inviteByEmail.mockRejectedValue(new Error("invite refused"));
    const seen: string[] = [];
    const listener = (event: Event) => {
      seen.push((event as CustomEvent).detail?.experience);
    };
    listenForWerner(listener);

    mount();
    await screen.findByText("Grandma Rosa");
    fireEvent.click(screen.getByText(/or invite someone by email/i));
    fireEvent.change(screen.getByPlaceholderText("friend@example.com"), {
      target: { value: "friend@example.com" },
    });
    fireEvent.click(screen.getByRole("button", { name: /send invite/i }));
    await screen.findByText("invite refused");
    expect(seen).toEqual([]);
  });

  it("lands as a LANDING-GLASS surface (SPR-03 M2 occlusion contract)", async () => {
    // Audit §3 item 3 classifies the Speak project page landing-glass: the scene
    // shows through the margins. A refactor back to an opaque body / variant=solid
    // would re-occlude the mountain; this enforces the variant per-route (rigor #5).
    const { container } = mount();
    await screen.findByText("Grandma Rosa");
    const surface = container.querySelector("[data-glass-surface]");
    expect(surface, "Speak must render through GlassSurface").toBeTruthy();
    expect(surface!.getAttribute("data-glass-variant")).toBe("glass");
    expect(surface!.getAttribute("data-glass-surface")).toBe("glass");
  });

  it("offers a shareable invite link", async () => {
    mount();
    await screen.findByText("Grandma Rosa");
    fireEvent.click(screen.getByRole("button", { name: /get a shareable link/i }));
    await waitFor(() =>
      expect(screen.getByText("https://antiek.ai/speak/invite/tok-xyz")).toBeTruthy(),
    );
    expect(screen.getByRole("button", { name: /copy link/i })).toBeTruthy();
  });

  it("renders arriving voices", async () => {
    api.listVoices.mockResolvedValue([
      { interviewId: "iv1", who: "aunt@x.com", state: "shared", link: "L" },
      { interviewId: "iv2", who: "Uncle Theo", state: "recording", link: "L2" },
    ]);
    mount();
    // The voice appears in the standalone "Voices" list (and again in the
    // email-invite fallback) — assert it's present at least once.
    expect((await screen.findAllByText("aunt@x.com")).length).toBeGreaterThan(0);
    expect(screen.getAllByText("Uncle Theo").length).toBeGreaterThan(0);
    // Voice-state labels are now centralized in speakVocab (VOICE_STATE_LABELS)
    // so the console and Invites can't drift — both surfaces show the humanized
    // word ("Shared"), not the raw VoiceState. The shared voice (aunt@x.com)
    // renders it in BOTH surfaces: the standalone Voices list AND the
    // email-invite Invites fallback (completed→shared→"Shared"). The recording
    // voice (Uncle Theo) shows "Recording…", not "Shared". So "Shared" must
    // appear EXACTLY twice — a single-surface regression (e.g. the console
    // dropping the label) would drop this to 1 and fail, where >0 would not.
    expect(screen.getAllByText("Shared")).toHaveLength(2);
  });

  it("frames agreement as corroborated, never proven; shows disagreement", async () => {
    api.whatEveryoneAgreesOn.mockResolvedValue([
      { text: "She ran the village bakery for thirty years.", kind: "corroborated", voices: 3 },
      { text: "She moved to the city in 1962.", kind: "disagreement", voices: 1 },
    ]);
    mount();
    await screen.findByText("Grandma Rosa");
    fireEvent.click(screen.getByRole("button", { name: /refresh/i }));
    expect(await screen.findByText(/corroborated · 3 people/i)).toBeTruthy();
    expect(screen.getByText(/remember this differently/i)).toBeTruthy();
    // The cardinal rule: nothing on the page claims a memory is proven/true.
    expect(screen.queryByText(/\bproven\b/i)).toBeNull();
    expect(screen.queryByText(/proven true/i)).toBeNull();
  });

  it("shows the Werner-thinking beat then an honest no-result when assembly fails (no key)", async () => {
    let reject!: (e: Error) => void;
    api.assembleDraft.mockReturnValue(new Promise((_res, rej) => { reject = rej; }));
    mount();
    await screen.findByText("Grandma Rosa");
    fireEvent.click(screen.getByRole("button", { name: /assemble the story/i }));
    // Werner present while assembling.
    expect(await screen.findByLabelText(/assembling their story/i)).toBeTruthy();
    // The engine returns nothing (no provider) → honest failure, no fake bio.
    reject(new Error("no provider"));
    expect(await screen.findByRole("alert")).toBeTruthy();
  });

  it("gathers economics/publishing behind one Settings tap; the split is shown, not paid", async () => {
    api.getProject.mockResolvedValue({
      id: "p1", name: "Grandma Rosa", willBePublic: true, subjectStatusWord: "deceased",
    });
    api.getEconomics.mockResolvedValue({ splitApplies: true, creatorCarriesCost: false });
    mount();
    await screen.findByText("Grandma Rosa");
    // The page itself is NOT a wall of verbs — publish lives behind Settings.
    expect(screen.queryByRole("button", { name: /try to publish/i })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /^settings$/i }));
    // The split is displayed as attribution, labelled not-yet-paid, balance $0.
    // (70% appears in both the split summary and the M2 matrix copy — assert
    // the load-bearing split-as-attribution sentence specifically.)
    expect(await screen.findByText(/70% of what it earns goes to the people/i)).toBeTruthy();
    expect(screen.getByText(/\$0\.00/)).toBeTruthy();
    expect(screen.getByText(/not a payment/i)).toBeTruthy();
    // No disbursement fired just from opening Settings.
    expect(apiFetchMock).not.toHaveBeenCalled();
  });

  it("the gated publish action surfaces the backend refusal verbatim (no fake success)", async () => {
    api.getProject.mockResolvedValue({
      id: "p1", name: "Grandma Rosa", willBePublic: true, subjectStatusWord: null,
    });
    api.getEconomics.mockResolvedValue({ splitApplies: true, creatorCarriesCost: false });
    apiFetchMock.mockResolvedValue({
      ok: false,
      status: 409,
      json: async () => ({ detail: "publishing blocked: legal gate G2 open" }),
    });
    mount();
    await screen.findByText("Grandma Rosa");
    fireEvent.click(screen.getByRole("button", { name: /^settings$/i }));
    fireEvent.click(await screen.findByRole("button", { name: /try to publish/i }));
    expect(await screen.findByText(/legal gate g2 open/i)).toBeTruthy();
  });
});
