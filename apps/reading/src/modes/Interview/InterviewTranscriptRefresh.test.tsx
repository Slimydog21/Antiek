import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import type { ReactNode } from "react";

import InterviewMode from ".";
import InterviewRecording from "./InterviewRecording";
import InterviewTranscript, {
  INTERVIEW_TRANSCRIPT_REFRESH_EVENT,
} from "./InterviewTranscript";

const apiFetchMock = vi.hoisted(() => vi.fn());

vi.mock("../../lib/api", async (orig) => ({
  ...(await orig<typeof import("../../lib/api")>()),
  apiFetch: apiFetchMock,
}));

vi.mock("../../components/InterviewVoiceCapture", () => ({
  default: ({ onUploaded }: { onUploaded?: (audioUrl: string) => void }) => (
    <button type="button" onClick={() => onUploaded?.("audio.webm")}>
      finish upload
    </button>
  ),
}));

vi.mock("../../workspace/PanelHost", () => ({
  PanelHost: ({ children }: { children: ReactNode }) => <>{children}</>,
}));

function interviewResponse(text: string) {
  return {
    ok: true,
    json: async () => ({
      interview_id: "int-1",
      project_id: "project-1",
      project_title: "Oral history",
      topic_description: null,
      framing: null,
      must_cover: [],
      status: "active",
      consent_recorded: true,
      transcript: [{ role: "informant", text, ts: null }],
    }),
  };
}

function deferredInterviewResponse(text: string) {
  let resolve!: () => void;
  const ready = new Promise<void>((done) => {
    resolve = done;
  });
  return {
    ok: true,
    json: async () => {
      await ready;
      return {
        interview_id: "int-1",
        project_id: "project-1",
        project_title: "Oral history",
        topic_description: null,
        framing: null,
        must_cover: [],
        status: "active",
        consent_recorded: true,
        transcript: [{ role: "informant", text, ts: null }],
      };
    },
    resolve,
  };
}

describe("Interview transcript refresh bridge", () => {
  beforeEach(() => {
    apiFetchMock.mockReset();
  });

  afterEach(() => {
    cleanup();
  });

  it("reloads the transcript after a matching recording upload event", async () => {
    apiFetchMock
      .mockResolvedValueOnce(interviewResponse("Before upload"))
      .mockResolvedValueOnce(interviewResponse("After upload"));

    render(<InterviewTranscript interviewId="int-1" />);

    expect(await screen.findByText("Before upload")).toBeTruthy();

    window.dispatchEvent(
      new CustomEvent(INTERVIEW_TRANSCRIPT_REFRESH_EVENT, {
        detail: { interviewId: "other-interview" },
      }),
    );

    expect(apiFetchMock).toHaveBeenCalledTimes(1);

    window.dispatchEvent(
      new CustomEvent(INTERVIEW_TRANSCRIPT_REFRESH_EVENT, {
        detail: { interviewId: "int-1" },
      }),
    );

    expect(await screen.findByText("After upload")).toBeTruthy();
    expect(apiFetchMock).toHaveBeenCalledTimes(2);
  });

  it("emits a scoped transcript refresh event when recording upload completes", async () => {
    apiFetchMock.mockResolvedValue(interviewResponse("Ready"));
    const refreshListener = vi.fn();
    window.addEventListener(INTERVIEW_TRANSCRIPT_REFRESH_EVENT, refreshListener);

    try {
      render(<InterviewRecording interviewId="int-1" consentRecorded />);

      await screen.findByRole("button", { name: "finish upload" });
      fireEvent.click(screen.getByRole("button", { name: "finish upload" }));

      expect(refreshListener).toHaveBeenCalledTimes(1);
      expect(refreshListener.mock.calls[0][0]).toMatchObject({
        detail: { interviewId: "int-1" },
      });
    } finally {
      window.removeEventListener(
        INTERVIEW_TRANSCRIPT_REFRESH_EVENT,
        refreshListener,
      );
    }
  });

  it("main interview voice capture emits refresh and updates the inline transcript", async () => {
    apiFetchMock
      .mockResolvedValueOnce(interviewResponse("Before upload"))
      .mockResolvedValueOnce(interviewResponse("After upload"));
    const refreshListener = vi.fn();
    window.addEventListener(INTERVIEW_TRANSCRIPT_REFRESH_EVENT, refreshListener);

    try {
      render(
        <MemoryRouter initialEntries={["/interview/int-1"]}>
          <Routes>
            <Route path="/interview/:interviewId" element={<InterviewMode />} />
          </Routes>
        </MemoryRouter>,
      );

      expect(await screen.findByText("Before upload")).toBeTruthy();
      fireEvent.click(screen.getByRole("button", { name: "finish upload" }));

      expect(await screen.findByText("After upload")).toBeTruthy();
      expect(refreshListener).toHaveBeenCalledTimes(1);
      expect(refreshListener.mock.calls[0][0]).toMatchObject({
        detail: { interviewId: "int-1" },
      });
    } finally {
      window.removeEventListener(
        INTERVIEW_TRANSCRIPT_REFRESH_EVENT,
        refreshListener,
      );
    }
  });

  it("main interview transcript follows docked recording refresh events", async () => {
    apiFetchMock
      .mockResolvedValueOnce(interviewResponse("Before docked upload"))
      .mockResolvedValueOnce(interviewResponse("After docked upload"));

    render(
      <MemoryRouter initialEntries={["/interview/int-1"]}>
        <Routes>
          <Route path="/interview/:interviewId" element={<InterviewMode />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(await screen.findByText("Before docked upload")).toBeTruthy();

    window.dispatchEvent(
      new CustomEvent(INTERVIEW_TRANSCRIPT_REFRESH_EVENT, {
        detail: { interviewId: "int-1" },
      }),
    );

    expect(await screen.findByText("After docked upload")).toBeTruthy();
  });

  it("keeps the newest transcript when reload responses complete out of order", async () => {
    const stale = deferredInterviewResponse("Stale upload");
    const fresh = deferredInterviewResponse("Fresh upload");
    apiFetchMock.mockResolvedValueOnce(stale).mockResolvedValueOnce(fresh);

    render(<InterviewTranscript interviewId="int-1" />);

    window.dispatchEvent(
      new CustomEvent(INTERVIEW_TRANSCRIPT_REFRESH_EVENT, {
        detail: { interviewId: "int-1" },
      }),
    );

    fresh.resolve();
    expect(await screen.findByText("Fresh upload")).toBeTruthy();

    stale.resolve();
    expect(screen.queryByText("Stale upload")).toBeNull();
  });

  it("keeps the newest main transcript when route reloads complete out of order", async () => {
    const stale = deferredInterviewResponse("Stale main");
    const fresh = deferredInterviewResponse("Fresh main");
    apiFetchMock.mockResolvedValueOnce(stale).mockResolvedValueOnce(fresh);

    render(
      <MemoryRouter initialEntries={["/interview/int-1"]}>
        <Routes>
          <Route path="/interview/:interviewId" element={<InterviewMode />} />
        </Routes>
      </MemoryRouter>,
    );

    window.dispatchEvent(
      new CustomEvent(INTERVIEW_TRANSCRIPT_REFRESH_EVENT, {
        detail: { interviewId: "int-1" },
      }),
    );

    fresh.resolve();
    expect(await screen.findByText("Fresh main")).toBeTruthy();

    stale.resolve();
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(screen.queryByText("Stale main")).toBeNull();
  });

  it("sanitizes main interview detail before rendering transcript and consent state", async () => {
    apiFetchMock.mockResolvedValue({
      ok: true,
      json: async () => ({
        interview_id: " int dirty ",
        project_id: " project dirty ",
        project_title: " Oral history ",
        topic_description: " Topic dirty ",
        framing: " Framing dirty ",
        must_cover: [" Question one ", " ", 42],
        status: " active ",
        consent_recorded: "yes",
        transcript: [
          { role: " informant ", text: "Skipped bad role", ts: null },
          { role: "informant", text: " Informant answer ", ts: " now " },
          { role: "interviewer", text: " ", ts: "Skipped empty" },
        ],
      }),
    });

    render(
      <MemoryRouter initialEntries={["/interview/int-1"]}>
        <Routes>
          <Route path="/interview/:interviewId" element={<InterviewMode />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(await screen.findByText("Oral history")).toBeTruthy();
    expect(screen.getByText("Informant answer")).toBeTruthy();
    expect(screen.getByText(/consent_recorded = false/)).toBeTruthy();
    expect(screen.getByText(/must_cover = 1/)).toBeTruthy();
    expect(document.body.textContent).not.toMatch(/Skipped| int dirty | now /);
  });

  it("sanitizes fetched transcript panel turns before rendering", async () => {
    apiFetchMock.mockResolvedValue({
      ok: true,
      json: async () => ({
        transcript: [
          {
            role: "informant",
            text: " Correct me ",
            ts: " 2026-06-06 ",
            pending: "yes",
            question_id: " q dirty ",
          },
          {
            role: "interviewer",
            text: " Interviewer question ",
            ts: null,
            pending: true,
          },
          { role: "operator", text: "Skipped role" },
          { role: "informant", text: " " },
        ],
      }),
    });

    render(<InterviewTranscript interviewId="int-1" />);

    expect(await screen.findByText("Correct me")).toBeTruthy();
    expect(screen.getByText("Interviewer question")).toBeTruthy();
    expect(screen.queryByText(/pending correction/)).toBeNull();
    expect(document.body.textContent).not.toMatch(/Skipped| q dirty |2026-06-06 /);
  });

  it("requires literal true consent before enabling the recording panel", async () => {
    apiFetchMock.mockResolvedValue({
      ok: true,
      json: async () => ({ consent_recorded: "yes" }),
    });

    render(<InterviewRecording interviewId="int-1" consentRecorded />);

    expect(await screen.findByText(/Consent not yet recorded/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "finish upload" })).toBeNull();
  });
});
