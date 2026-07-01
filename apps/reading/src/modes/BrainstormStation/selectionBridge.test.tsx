import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";

import type { ParkedQuestionEntry } from "../../lib/api";

const apiMocks = vi.hoisted(() => ({
  listWatchForLater: vi.fn(),
  launchParkedQuestion: vi.fn(),
}));

vi.mock("../../lib/api", async (orig) => ({
  ...(await orig<typeof import("../../lib/api")>()),
  listWatchForLater: apiMocks.listWatchForLater,
  launchParkedQuestion: apiMocks.launchParkedQuestion,
}));

vi.mock("../../lib/analytics", () => ({
  track: vi.fn(),
}));

vi.mock("../../workspace/PanelHost", () => ({
  PanelHost: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="panel-host">{children}</div>
  ),
}));

import BrainstormStation from ".";
import WatchForLaterPanel, {
  BRAINSTORM_SELECT_QUESTION_EVENT,
  BRAINSTORM_WATCHLIST_CHANGED_EVENT,
  dispatchBrainstormQuestionSelection,
  dispatchBrainstormWatchlistChanged,
  resetBrainstormQuestionSelection,
} from "./WatchForLaterPanel";

const QUESTION: ParkedQuestionEntry = {
  question_id: "q-bridge",
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

beforeEach(() => {
  apiMocks.listWatchForLater.mockReset().mockResolvedValue({
    questions: [QUESTION],
  });
  apiMocks.launchParkedQuestion.mockReset();
});

afterEach(() => {
  cleanup();
  resetBrainstormQuestionSelection();
});

describe("BrainstormStation watch-list selection bridge", () => {
  it("WatchForLaterPanel emits the selected parked question", async () => {
    const seen: ParkedQuestionEntry[] = [];
    const listener = (event: Event) => {
      const question = (event as CustomEvent<{ question: ParkedQuestionEntry }>).detail
        .question;
      seen.push(question);
    };
    window.addEventListener(BRAINSTORM_SELECT_QUESTION_EVENT, listener);

    render(<WatchForLaterPanel />);
    await userEvent.click(await screen.findByText(QUESTION.question_text));

    expect(seen).toEqual([QUESTION]);
    window.removeEventListener(BRAINSTORM_SELECT_QUESTION_EVENT, listener);
  });

  it("BrainstormStation main pane follows a docked watch-list selection", async () => {
    render(
      <MemoryRouter>
        <BrainstormStation />
      </MemoryRouter>,
    );

    await waitFor(() => expect(apiMocks.listWatchForLater).toHaveBeenCalled());
    expect(screen.queryByText("Parked question")).toBeNull();

    window.dispatchEvent(
      new CustomEvent(BRAINSTORM_SELECT_QUESTION_EVENT, {
        detail: { question: QUESTION },
      }),
    );

    expect(await screen.findByText("Parked question")).toBeTruthy();
    expect(screen.getAllByText(QUESTION.question_text).length).toBeGreaterThan(0);
    expect(screen.getAllByText("inv-source").length).toBeGreaterThan(0);
    expect(screen.getByText("q-bridge")).toBeTruthy();
  });

  it("BrainstormStation replays the latest selected question when the route mounts after selection", async () => {
    dispatchBrainstormQuestionSelection(QUESTION);

    render(
      <MemoryRouter>
        <BrainstormStation />
      </MemoryRouter>,
    );

    expect(await screen.findByText("Parked question")).toBeTruthy();
    expect(screen.getAllByText(QUESTION.question_text).length).toBeGreaterThan(0);
    expect(screen.getByText("q-bridge")).toBeTruthy();
  });

  it("WatchForLaterPanel follows selection events emitted outside the dock", async () => {
    apiMocks.listWatchForLater.mockResolvedValue({
      questions: [QUESTION, SECOND_QUESTION],
    });

    render(<WatchForLaterPanel />);
    expect(await screen.findByText(QUESTION.question_text)).toBeTruthy();

    dispatchBrainstormQuestionSelection(SECOND_QUESTION);

    await waitFor(() => {
      const selectedButton = screen
        .getByText(SECOND_QUESTION.question_text)
        .closest("button");
      expect(selectedButton?.className).toContain("border-ink");
    });
  });

  it("WatchForLaterPanel reloads immediately when the watch-list changes", async () => {
    apiMocks.listWatchForLater
      .mockResolvedValueOnce({ questions: [QUESTION] })
      .mockResolvedValueOnce({ questions: [QUESTION, SECOND_QUESTION] });

    render(<WatchForLaterPanel />);
    expect(await screen.findByText(QUESTION.question_text)).toBeTruthy();
    expect(screen.queryByText(SECOND_QUESTION.question_text)).toBeNull();

    act(() => {
      dispatchBrainstormWatchlistChanged();
    });

    await waitFor(() => expect(apiMocks.listWatchForLater).toHaveBeenCalledTimes(2));
    expect(await screen.findByText(SECOND_QUESTION.question_text)).toBeTruthy();
  });

  it("BrainstormStation reloads its host state when the watch-list changes", async () => {
    apiMocks.listWatchForLater
      .mockResolvedValueOnce({ questions: [] })
      .mockResolvedValueOnce({ questions: [QUESTION] });

    render(
      <MemoryRouter>
        <BrainstormStation />
      </MemoryRouter>,
    );
    expect(await screen.findByText(/No parked questions yet/i)).toBeTruthy();

    act(() => {
      dispatchBrainstormWatchlistChanged();
    });

    await waitFor(() => expect(apiMocks.listWatchForLater).toHaveBeenCalledTimes(2));
    expect(await screen.findByText(QUESTION.question_text)).toBeTruthy();
  });

  it("BrainstormStation broadcasts a watch-list change after launching a parked question", async () => {
    apiMocks.launchParkedQuestion.mockResolvedValue({
      investigation_id: "inv-child",
      status: "in_progress",
      start_event_id: "evt-start",
    });
    apiMocks.listWatchForLater
      .mockResolvedValueOnce({ questions: [QUESTION] })
      .mockResolvedValue({ questions: [] });
    const watchlistChanges: Event[] = [];
    const onWatchlistChanged = (event: Event) => {
      watchlistChanges.push(event);
    };
    window.addEventListener(BRAINSTORM_WATCHLIST_CHANGED_EVENT, onWatchlistChanged);

    try {
      render(
        <MemoryRouter>
          <BrainstormStation />
        </MemoryRouter>,
      );
      await waitFor(() => expect(apiMocks.listWatchForLater).toHaveBeenCalled());

      dispatchBrainstormQuestionSelection(QUESTION);
      await userEvent.click(await screen.findByRole("button", { name: /launch investigation/i }));

      await waitFor(() =>
        expect(apiMocks.launchParkedQuestion).toHaveBeenCalledWith(QUESTION.question_id),
      );
      await waitFor(() => expect(watchlistChanges).toHaveLength(1));
    } finally {
      window.removeEventListener(BRAINSTORM_WATCHLIST_CHANGED_EVENT, onWatchlistChanged);
    }
  });
});
