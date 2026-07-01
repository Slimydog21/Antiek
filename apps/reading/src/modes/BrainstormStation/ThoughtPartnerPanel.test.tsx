import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import type { ParkedQuestionEntry } from "../../lib/api";
import ThoughtPartnerPanel from "./ThoughtPartnerPanel";
import {
  dispatchBrainstormQuestionSelection,
  resetBrainstormQuestionSelection,
} from "./WatchForLaterPanel";

const apiFetchMock = vi.hoisted(() => vi.fn());

vi.mock("../../lib/api", async (orig) => ({
  ...(await orig<typeof import("../../lib/api")>()),
  apiFetch: apiFetchMock,
}));

const QUESTION: ParkedQuestionEntry = {
  question_id: "q-memory",
  question_text: "What would make retrieval feel like memory?",
  source_investigation_id: "inv-source",
  source_document_id: "doc-source",
  anchor_region_id: "region-1",
  parent_event_id: "event-parent",
  parked_at: "2026-07-01T00:00:00Z",
};
const SECOND_QUESTION: ParkedQuestionEntry = {
  ...QUESTION,
  question_id: "q-second",
  question_text: "How should a note become a writing block?",
  source_investigation_id: "inv-second",
  source_document_id: null,
  anchor_region_id: null,
};

function selectQuestion(question = QUESTION) {
  dispatchBrainstormQuestionSelection(question);
}

function deferredResponse(text: string) {
  let resolve!: () => void;
  const ready = new Promise<void>((done) => {
    resolve = done;
  });
  return {
    response: ready.then(() => ({
      ok: true,
      json: async () => ({ text, thread_node_id: null }),
    })),
    resolve,
  };
}

beforeEach(() => {
  apiFetchMock.mockReset();
});

afterEach(() => {
  cleanup();
  resetBrainstormQuestionSelection();
});

describe("ThoughtPartnerPanel", () => {
  it("sends the selected parked question as thought-partner context", async () => {
    apiFetchMock.mockResolvedValue({
      ok: true,
      json: async () => ({
        text: "Treat memory as retrieval that preserves friction and provenance.",
        thread_node_id: "thread-1",
      }),
    });

    render(<ThoughtPartnerPanel />);
    expect(screen.getByText("Select a parked question from the watch-for-later panel.")).toBeTruthy();

    selectQuestion();
    expect(await screen.findByText(QUESTION.question_text)).toBeTruthy();
    expect(screen.getByText("inv-source / doc-source")).toBeTruthy();

    await userEvent.type(
      screen.getByPlaceholderText("Challenge, synthesize, or extend this question..."),
      "Synthesize this into a sharper direction",
    );
    await userEvent.click(screen.getByRole("button", { name: "Ask thought partner" }));

    await waitFor(() => expect(apiFetchMock).toHaveBeenCalledTimes(1));
    expect(apiFetchMock).toHaveBeenCalledWith(
      "/thought-partner",
      expect.objectContaining({
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          investigation_id: "inv-source",
          passage: QUESTION.question_text,
          follow_up: "Synthesize this into a sharper direction",
          system_context: [
            "BrainstormStation thought-partner panel",
            "parked_question_id=q-memory",
            "anchor_region_id=region-1",
          ].join("\n"),
        }),
      }),
    );
    expect(await screen.findByText(/Treat memory as retrieval/)).toBeTruthy();
    expect(screen.getByText("anchored thread: thread-1")).toBeTruthy();
  });

  it("surfaces the honest no-key state without fabricating a reply", async () => {
    apiFetchMock.mockResolvedValue({
      ok: false,
      status: 503,
      text: async () => "dispatch_unavailable",
    });

    render(<ThoughtPartnerPanel />);
    selectQuestion();
    await userEvent.type(
      await screen.findByPlaceholderText("Challenge, synthesize, or extend this question..."),
      "Challenge this",
    );
    await userEvent.click(screen.getByRole("button", { name: "Ask thought partner" }));

    expect(await screen.findByText(/No provider keys configured yet/)).toBeTruthy();
    expect(screen.queryByText("Reply")).toBeNull();
  });

  it("replays a selected question when the panel mounts after the selection event", async () => {
    selectQuestion();

    render(<ThoughtPartnerPanel />);

    expect(await screen.findByText(QUESTION.question_text)).toBeTruthy();
    expect(screen.getByText("inv-source / doc-source")).toBeTruthy();
  });

  it("drops an in-flight reply when the selected question changes", async () => {
    const stale = deferredResponse("stale answer for the first question");
    apiFetchMock.mockReturnValueOnce(stale.response);

    render(<ThoughtPartnerPanel />);
    selectQuestion();
    await userEvent.type(
      await screen.findByPlaceholderText("Challenge, synthesize, or extend this question..."),
      "Synthesize this",
    );
    await userEvent.click(screen.getByRole("button", { name: "Ask thought partner" }));

    selectQuestion(SECOND_QUESTION);
    expect(await screen.findByText(SECOND_QUESTION.question_text)).toBeTruthy();

    stale.resolve();
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(screen.queryByText(/stale answer/)).toBeNull();
    expect(screen.queryByText("Reply")).toBeNull();
  });

  it("resets the draft when a different parked question is selected", async () => {
    render(<ThoughtPartnerPanel />);
    selectQuestion();
    const input = await screen.findByPlaceholderText(
      "Challenge, synthesize, or extend this question...",
    );
    await userEvent.type(input, "Question-specific prompt");

    selectQuestion(SECOND_QUESTION);

    await waitFor(() =>
      expect(
        (
          screen.getByPlaceholderText(
            "Challenge, synthesize, or extend this question...",
          ) as HTMLTextAreaElement
        ).value,
      ).toBe(""),
    );
    expect(
      (screen.getByRole("button", { name: "Ask thought partner" }) as HTMLButtonElement)
        .disabled,
    ).toBe(true);
  });

  it("does not send an empty parked question to the backend", async () => {
    render(<ThoughtPartnerPanel />);
    selectQuestion({ ...QUESTION, question_text: "   " });

    expect(await screen.findByText("This parked question has no text to send.")).toBeTruthy();
    await userEvent.type(
      screen.getByPlaceholderText("Challenge, synthesize, or extend this question..."),
      "Try anyway",
    );

    expect(
      (screen.getByRole("button", { name: "Ask thought partner" }) as HTMLButtonElement)
        .disabled,
    ).toBe(true);
    expect(apiFetchMock).not.toHaveBeenCalled();
  });
});
