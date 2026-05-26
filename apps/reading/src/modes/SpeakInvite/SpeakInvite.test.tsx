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
});
