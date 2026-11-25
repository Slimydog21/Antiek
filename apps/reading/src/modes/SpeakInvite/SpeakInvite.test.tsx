import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
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
  publish_intent: "private_never_published",
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
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

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
  it("does not claim consent alone saved a memory and can reload a ready question", async () => {
    apiFetchMock.mockResolvedValueOnce(landingResponse({ ...CONSENTED, pending_questions: [] }))
      .mockResolvedValue(landingResponse(CONSENTED));
    mount();
    expect(await screen.findByText(/no memories yet/i)).toBeTruthy();
    expect(screen.queryByText(/what you shared is saved/i)).toBeNull();
    expect(screen.queryByRole("button", { name: /grant mic access/i })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /check again/i }));
    expect(await screen.findByText(/what's your earliest memory/i)).toBeTruthy();
    expect(screen.getByRole("button", { name: /grant mic access/i })).toBeTruthy();
  });

  it("does not count an interviewer prompt as a saved memory", async () => {
    apiFetchMock.mockResolvedValue(landingResponse({
      ...CONSENTED, pending_questions: [],
      transcript: [{ role: "interviewer", text: "An unanswered prompt", ts: null }],
    }));
    mount();
    expect(await screen.findByText(/no memories yet/i)).toBeTruthy();
    expect(screen.queryByText(/what you shared is saved/i)).toBeNull();
  });

  it("shows saved only when the server returns an informant memory", async () => {
    apiFetchMock.mockResolvedValue(landingResponse({
      ...CONSENTED, pending_questions: [],
      transcript: [{ role: "informant", text: "She sang while cooking.", ts: null }],
    }));
    mount();
    expect(await screen.findByText(/what you shared is saved/i)).toBeTruthy();
    expect(screen.queryByText(/no memories yet/i)).toBeNull();
    expect(screen.queryByText(/anytime to add more/i)).toBeNull();
  });

  it("keeps consent retryable when the network fails", async () => {
    apiFetchMock.mockImplementation((url: string) => url.endsWith("/consent")
      ? Promise.reject(new TypeError("Failed to fetch"))
      : Promise.resolve(landingResponse(NOT_CONSENTED)));
    await act(async () => { mount(); });
    fireEvent.click(screen.getByRole("button", { name: /i'll share a memory/i }));
    expect(await screen.findByText(/couldn't start sharing/i)).toBeTruthy();
    await waitFor(() => expect(screen.getByRole("button", { name: /i'll share a memory/i }).hasAttribute("disabled")).toBe(false));
    expect(screen.queryByText(/tap to talk/i)).toBeNull();
  });

  it("retains an unsent memory and allows retry after a network failure", async () => {
    apiFetchMock.mockImplementation((url: string) => url.endsWith("/answer")
      ? Promise.reject(new TypeError("Failed to fetch"))
      : Promise.resolve(landingResponse(CONSENTED)));
    await act(async () => { mount(); });
    fireEvent.click(screen.getByRole("button", { name: /i'd rather type/i }));
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "My unsent memory" } });
    fireEvent.click(screen.getByRole("button", { name: /send this memory/i }));
    expect(await screen.findByText(/couldn't send your answer/i)).toBeTruthy();
    const box = screen.getByRole("textbox");
    if (!(box instanceof HTMLTextAreaElement)) throw new Error("Memory textbox missing");
    expect(box.value).toBe("My unsent memory");
    expect(screen.queryByText(/what you shared is saved/i)).toBeNull();
  });

  it("does not claim a decline was recorded when the server refuses it", async () => {
    apiFetchMock.mockImplementation((url: string) => url.endsWith("/decline")
      ? Promise.resolve({ ok: false, status: 503 })
      : Promise.resolve(landingResponse(NOT_CONSENTED)));
    mount();
    fireEvent.click(await screen.findByRole("button", { name: /not right now/i }));
    expect(await screen.findByText(/couldn't save your choice/i)).toBeTruthy();
    expect(screen.queryByText(/^thank you\.$/i)).toBeNull();
  });

  it("offers the next recording after voice submission and sends a typed followup to the displayed question", async () => {
    let recorder: Recorder;
    class Recorder {
      state = "inactive";
      mimeType = "audio/webm";
      ondataavailable: ((event: { data: Blob }) => void) | null = null;
      onstop: (() => void) | null = null;
      constructor() { recorder = this; }
      start() { this.state = "recording"; }
      stop() { this.state = "inactive"; }
    }
    vi.stubGlobal("MediaRecorder", Recorder);
    let voiceShared = false;
    const answers: unknown[] = [];
    apiFetchMock.mockImplementation((url: string, init?: RequestInit) => {
      if (url.includes("/voice?")) {
        voiceShared = true;
        return Promise.resolve(landingResponse({ transcript: "Unit-test voice response" }));
      }
      if (url.endsWith("/answer")) {
        answers.push(JSON.parse(String(init?.body)));
        return Promise.resolve(landingResponse({}));
      }
      return Promise.resolve(landingResponse(voiceShared ? {
        ...CONSENTED, pending_questions: [{ id: "q2", text: "What happened next?" }],
      } : CONSENTED));
    });
    mount();
    fireEvent.click(await screen.findByRole("button", { name: /grant mic access/i }));
    fireEvent.click(await screen.findByRole("button", { name: /start recording/i }));
    fireEvent.click(screen.getByRole("button", { name: /stop & upload/i }));
    act(() => {
      recorder.ondataavailable?.({ data: new Blob(["test audio"]) });
      recorder.onstop?.();
    });
    expect(await screen.findByText("What happened next?")).toBeTruthy();
    expect(screen.getByRole("button", { name: /grant mic access/i })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /i'd rather type/i }));
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "A typed followup" } });
    fireEvent.click(screen.getByRole("button", { name: /send this memory/i }));
    await waitFor(() => expect(answers).toEqual([{ question_id: "q2", transcript: "A typed followup" }]));
  });

  it("shows warm consent as one honest sentence with a safe default, not a checklist wall", async () => {
    apiFetchMock.mockResolvedValue(landingResponse(NOT_CONSENTED));
    mount();
    await screen.findByText(/remember grandma rosa/i);
    // One warm yes — and a clean "not right now". No checklist of scopes.
    expect(screen.getByRole("button", { name: /i'll share a memory/i })).toBeTruthy();
    expect(screen.getByRole("button", { name: /not right now/i })).toBeTruthy();
    expect(document.querySelectorAll('input[type="checkbox"]').length).toBe(0);
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
        ? { ...CONSENTED, pending_questions: [], transcript: [
          { role: "informant", text: "She always sang while cooking.", ts: null, question_id: "q1" },
        ] }
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

  it("shows unmistakable NO EARNINGS banner on a private project before consent", async () => {
    apiFetchMock.mockResolvedValue(landingResponse(NOT_CONSENTED));
    mount();
    expect(await screen.findByTestId("private-econ-notice")).toBeTruthy();
    expect(
      screen.getByText(/you will NOT make money on this private project/i),
    ).toBeTruthy();
    expect(screen.queryByTestId("public-econ-notice")).toBeNull();
  });

  it("shows public can-earn notice when publish_intent is will_be_public", async () => {
    apiFetchMock.mockResolvedValue(
      landingResponse({ ...NOT_CONSENTED, publish_intent: "will_be_public" }),
    );
    mount();
    expect(await screen.findByTestId("public-econ-notice")).toBeTruthy();
    expect(screen.getByText(/contributors can earn via the 70% split/i)).toBeTruthy();
    expect(screen.queryByTestId("private-econ-notice")).toBeNull();
  });

});
