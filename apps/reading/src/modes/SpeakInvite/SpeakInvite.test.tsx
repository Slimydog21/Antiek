import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

/**
 * SpeakInvite.test — the phone-first, voice-first invitee landing (SPR-08 M3).
 *
 * Load-bearing claims:
 *  - VOICE is the primary input: a tap-to-talk mic shows by default, with
 *    typing offered as a fallback (the headline fix — today invitees must type);
 *  - consent is one honest sentence with a safe default, not a checklist wall;
 *  - declining terminates cleanly (thank-you, no dead end) and the person is
 *    NOT pushed into recording.
 */

const apiFetchMock = vi.hoisted(() => vi.fn());
vi.mock("../../lib/api", async (orig) => ({
  ...(await orig<typeof import("../../lib/api")>()),
  apiFetch: apiFetchMock,
}));

import SpeakInvite from "./index";

const NOT_CONSENTED = {
  interview_id: "iv1",
  project_id: "p1",
  project_title: "Grandma Rosa's story",
  subject_ref: "Grandma Rosa",
  required_consent_scopes: ["record", "publish"],
  granted_consent_scopes: [],
  status: "invited",
  pending_questions: [{ id: "q1", text: "What's your earliest memory of her?" }],
  transcript: [],
};

const CONSENTED = { ...NOT_CONSENTED, granted_consent_scopes: ["record"] };

function landingResponse(body: unknown) {
  return { ok: true, status: 200, json: async () => body };
}

beforeEach(() => {
  apiFetchMock.mockReset();
  Object.assign(navigator, {
    mediaDevices: { getUserMedia: vi.fn().mockResolvedValue({ getTracks: () => [] }) },
  });
});
afterEach(cleanup);

function mount() {
  return render(
    <MemoryRouter initialEntries={["/speak/invite/tok-xyz"]}>
      <Routes>
        <Route path="/speak/invite/:token" element={<SpeakInvite />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("SpeakInvite — phone-first, voice-first", () => {
  it("shows warm consent as one honest sentence with a safe default, not a checklist wall", async () => {
    apiFetchMock.mockResolvedValue(landingResponse(NOT_CONSENTED));
    mount();
    await screen.findByText(/remember grandma rosa/i);
    // One warm yes — and a clean "not right now". No checklist of scopes.
    expect(screen.getByRole("button", { name: /i'll share a memory/i })).toBeTruthy();
    expect(screen.getByRole("button", { name: /not right now/i })).toBeTruthy();
    expect(document.querySelectorAll('input[type="checkbox"]').length).toBe(0);
    // Living-TV densify on invitee door (phone-first).
    expect(screen.getByTestId("speak-invite-werner-brand")).toBeTruthy();
    expect(
      (screen.getByTestId("speak-invite-living-tv-art") as HTMLImageElement)
        .getAttribute("src") ?? "",
    ).toMatch(/werner_living_tv_session_v1/);
  });

  it("makes VOICE the primary input once consented, with typing as a fallback", async () => {
    apiFetchMock.mockResolvedValue(landingResponse(CONSENTED));
    mount();
    await screen.findByText(/what's your earliest memory/i);
    // The tap-to-talk mic is present (the capture component's consent button).
    expect(screen.getByRole("button", { name: /grant mic access/i })).toBeTruthy();
    expect(screen.getByText(/tap to talk/i)).toBeTruthy();
    // Typing is offered as the fallback, not the default.
    expect(screen.getByRole("button", { name: /i'd rather type/i })).toBeTruthy();
    // Switching to type reveals the textarea.
    fireEvent.click(screen.getByRole("button", { name: /i'd rather type/i }));
    expect(screen.getByPlaceholderText(/share whatever comes to mind/i)).toBeTruthy();
  });

  it("declining terminates cleanly (thank-you, no dead end) and never enters recording", async () => {
    apiFetchMock.mockImplementation((url: string) => {
      if (typeof url === "string" && url.includes("/decline")) {
        return Promise.resolve({ ok: true, status: 200, json: async () => ({ status: "declined" }) });
      }
      return Promise.resolve(landingResponse(NOT_CONSENTED));
    });
    mount();
    await screen.findByText(/remember grandma rosa/i);
    fireEvent.click(screen.getByRole("button", { name: /not right now/i }));
    expect(await screen.findByText(/thank you/i)).toBeTruthy();
    expect(screen.getByText(/nothing's been shared/i)).toBeTruthy();
    // Never pushed into recording.
    expect(screen.queryByText(/tap to talk/i)).toBeNull();
    expect(screen.queryByRole("button", { name: /grant mic access/i })).toBeNull();
  });

  it("an invalid token is an honest dead-stop, not a broken page", async () => {
    apiFetchMock.mockResolvedValue({ ok: false, status: 404, json: async () => ({}) });
    mount();
    expect(await screen.findByText(/invalid or has expired/i)).toBeTruthy();
  });

  it("renders fully logged-out: no AuthProvider/RequireAuth in the tree, the token is the only credential", async () => {
    // mount() deliberately wraps SpeakInvite in a bare MemoryRouter — NO
    // AuthProvider, NO RequireAuth. If the component reached for auth context
    // or redirected to /login, this would throw or fail to render. The route
    // sits before the RequireAuth catch-all in App.tsx (verified at line 232).
    apiFetchMock.mockResolvedValue(landingResponse(NOT_CONSENTED));
    mount();
    expect(await screen.findByText(/remember grandma rosa/i)).toBeTruthy();
    // No login redirect happened; the landing rendered from the token alone.
    expect(screen.queryByText(/log ?in/i)).toBeNull();
  });

  it("land → consent → answer (text): grants consent then submits the typed memory", async () => {
    const calls: { url: string; init?: RequestInit }[] = [];
    apiFetchMock.mockImplementation((url: string, init?: RequestInit) => {
      calls.push({ url, init });
      if (typeof url === "string" && url.includes("/consent")) {
        return Promise.resolve({ ok: true, status: 200, json: async () => ({}) });
      }
      if (typeof url === "string" && url.includes("/answer")) {
        return Promise.resolve({ ok: true, status: 201, json: async () => ({}) });
      }
      // The landing reload after consent reflects record granted; reload after
      // the answer shows nothing pending (warm thank-you).
      const consentDone = calls.some((c) => c.url.includes("/consent"));
      const answerDone = calls.some((c) => c.url.includes("/answer"));
      const body = answerDone
        ? { ...CONSENTED, pending_questions: [] }
        : consentDone
          ? CONSENTED
          : NOT_CONSENTED;
      return Promise.resolve(landingResponse(body));
    });
    mount();
    await screen.findByText(/remember grandma rosa/i);

    // Consent — one warm yes.
    fireEvent.click(screen.getByRole("button", { name: /i'll share a memory/i }));
    await screen.findByText(/what's your earliest memory/i);

    // Switch to typing (voice-first; text is the fallback), type, send.
    fireEvent.click(screen.getByRole("button", { name: /i'd rather type/i }));
    const box = screen.getByPlaceholderText(/share whatever comes to mind/i) as HTMLTextAreaElement;
    fireEvent.change(box, { target: { value: "She always sang while cooking." } });
    fireEvent.click(screen.getByRole("button", { name: /send this memory/i }));

    // The warm done-state appears (no dead end), and the answer POST carried
    // the typed transcript verbatim (the corrected transcript IS what they typed).
    expect(await screen.findByText(/what you shared is saved/i)).toBeTruthy();
    const answerCall = calls.find((c) => c.url.includes("/answer"));
    expect(answerCall).toBeTruthy();
    expect(JSON.parse(String(answerCall!.init!.body))).toMatchObject({
      question_id: "q1",
      transcript: "She always sang while cooking.",
    });
  });

  it("publish is OFF BY DEFAULT: the prominent share action grants RECORD ONLY (no publish), never opt-out", async () => {
    // This is the legally-load-bearing assertion: the one obvious button a
    // friend taps must NOT publish them. Publishing is the consent that has to
    // be defensible against "did this friend actually agree to be published?";
    // it can only ever be granted by the explicit second action (next test).
    const consentBodies: unknown[] = [];
    apiFetchMock.mockImplementation((url: string, init?: RequestInit) => {
      if (typeof url === "string" && url.includes("/consent")) {
        consentBodies.push(JSON.parse(String(init!.body)));
        return Promise.resolve({ ok: true, status: 200, json: async () => ({}) });
      }
      const body = consentBodies.length > 0 ? CONSENTED : NOT_CONSENTED;
      return Promise.resolve(landingResponse(body));
    });
    mount();
    await screen.findByText(/remember grandma rosa/i);
    // The honest "still helps, just not public" framing is present (the invite
    // asks for publish — NOT_CONSENTED.required_consent_scopes includes it).
    expect(screen.getByText(/either way still helps/i)).toBeTruthy();
    // Tap the PROMINENT / default share action.
    fireEvent.click(screen.getByRole("button", { name: /yes, i'll share a memory/i }));
    await screen.findByText(/what's your earliest memory/i);
    // The default consent POST granted record only — publish was NOT snuck in.
    expect(consentBodies).toHaveLength(1);
    const granted = (consentBodies[0] as { scopes: string[] }).scopes;
    expect(granted).toContain("record");
    expect(granted).not.toContain("publish");
  });

  it("publish is an affirmative OPT-IN: only the explicit publish button grants publish (a button, not a checkbox)", async () => {
    const consentBodies: unknown[] = [];
    apiFetchMock.mockImplementation((url: string, init?: RequestInit) => {
      if (typeof url === "string" && url.includes("/consent")) {
        consentBodies.push(JSON.parse(String(init!.body)));
        return Promise.resolve({ ok: true, status: 200, json: async () => ({}) });
      }
      const body = consentBodies.length > 0 ? CONSENTED : NOT_CONSENTED;
      return Promise.resolve(landingResponse(body));
    });
    mount();
    await screen.findByText(/remember grandma rosa/i);
    // Publish opt-in is a clearly-affirmative BUTTON the friend actively picks —
    // not a checkbox/checklist (the 0-checkboxes contract above stays green).
    const optIn = screen.getByRole("button", {
      name: /use my words in the public story/i,
    });
    expect(document.querySelectorAll('input[type="checkbox"]').length).toBe(0);
    fireEvent.click(optIn);
    await screen.findByText(/what's your earliest memory/i);
    // Only this action grants publish — affirmatively, by the friend's choice.
    expect(consentBodies).toHaveLength(1);
    const granted = (consentBodies[0] as { scopes: string[] }).scopes;
    expect(granted).toContain("record");
    expect(granted).toContain("publish");
  });

  it("mic-denied is honest: 'Type instead' reveals a real text box with the no-mic reassurance", async () => {
    apiFetchMock.mockResolvedValue(landingResponse(CONSENTED));
    mount();
    await screen.findByText(/what's your earliest memory/i);
    // The capture surface offers an explicit out for a broken/blocked mic.
    fireEvent.click(screen.getByRole("button", { name: /type instead/i }));
    // We drop to the honest text fallback — never a dead end, never a fake mic.
    expect(screen.getByText(/no microphone — no problem/i)).toBeTruthy();
    expect(screen.getByPlaceholderText(/share whatever comes to mind/i)).toBeTruthy();
    // The mic is gone (we committed to text); no decorative recorder lingers.
    expect(screen.queryByText(/tap to talk/i)).toBeNull();
  });
});
