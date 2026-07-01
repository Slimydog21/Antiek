import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import InterviewTranscript, {
  INTERVIEW_TRANSCRIPT_REFRESH_EVENT,
} from "./InterviewTranscript";

const apiFetchMock = vi.hoisted(() => vi.fn());

vi.mock("../../lib/api", async (orig) => ({
  ...(await orig<typeof import("../../lib/api")>()),
  apiFetch: apiFetchMock,
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

});
