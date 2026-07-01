/**
 * TalkToBook.test.tsx — Read SPR-08 M2 (+ M3 wiring).
 *
 * The floating bookmark's MULTI-TURN conversation: answers cite pages, a
 * citation click JUMPS the reader to that page, the conversation CONTINUES
 * (multi-turn) and BRANCHES, and it PERSISTS across a re-mount (the bookmark
 * carries it via sessionStorage — the usePosition precedent). An unresolved
 * page is shown honestly, never a fabricated page. The answer mounts a read-
 * aloud control (M3 wiring).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";

import type { AskBookResponse, BookCitation } from "../../api/books";
import TalkToBook from "./TalkToBook";

const { askBookMock } = vi.hoisted(() => ({ askBookMock: vi.fn() }));

vi.mock("../../api/books", async (orig) => {
  const actual = await orig<typeof import("../../api/books")>();
  return { ...actual, askBook: askBookMock };
});

// Stub ReadAloud so the TTS network path isn't coupled into this test (the real
// control is covered by ReadAloud.test.tsx); we only assert it is MOUNTED with
// the answer text (M3 wiring).
vi.mock("../../components/voice/ReadAloud", () => ({
  default: ({ text, label }: { text: string; label?: string }) => (
    <button type="button" data-testid="read-aloud" data-text={text}>
      {label ?? "Read aloud"}
    </button>
  ),
}));

const cite = (over: Partial<BookCitation> = {}): BookCitation => ({
  chunk_id: "c1",
  document_id: "doc-x",
  page_index: 6,
  page_resolved: true,
  snippet: "the cited passage",
  ...over,
});

function answer(over: Partial<AskBookResponse> = {}): AskBookResponse {
  return {
    answer: "Page seven discusses entanglement.",
    citations: [cite()],
    grounded: true,
    context_chunk_count: 1,
    ...over,
  };
}

beforeEach(() => {
  askBookMock.mockReset();
  window.sessionStorage.clear();
});
afterEach(cleanup);

async function openAndAsk(
  jump = vi.fn(),
  question = "what is on page seven?",
  expectAnswer = "Page seven discusses entanglement.",
) {
  const utils = render(<TalkToBook documentId="doc-x" title="A Book" onJumpToPage={jump} />);
  fireEvent.click(screen.getByTestId("talk-to-book-bookmark"));
  fireEvent.change(screen.getByPlaceholderText("Ask about this book…"), {
    target: { value: question },
  });
  fireEvent.click(screen.getByRole("button", { name: "Ask" }));
  await screen.findByText(expectAnswer);
  return utils;
}

describe("TalkToBook (M2)", () => {
  it("answers cite pages and a citation click jumps the reader to that page", async () => {
    askBookMock.mockResolvedValue(answer());
    const jump = vi.fn();
    await openAndAsk(jump);

    // The citation chip shows the 1-based page; clicking jumps to the 0-based
    // page index (REUSES the reader's setPageIndex via onJumpToPage).
    const chip = screen.getByRole("button", { name: "p.7" });
    fireEvent.click(chip);
    expect(jump).toHaveBeenCalledWith(6);
  });

  it("an unresolved page is shown honestly (no fabricated page, no jump)", async () => {
    askBookMock.mockResolvedValue(answer({ citations: [cite({ page_index: null, page_resolved: false })] }));
    const jump = vi.fn();
    await openAndAsk(jump);
    expect(screen.getByText("in the book (page not pinpointed)")).toBeTruthy();
    expect(jump).not.toHaveBeenCalled();
  });

  it("continues the multi-turn conversation, sending prior turns as history", async () => {
    askBookMock
      .mockResolvedValueOnce(answer({ answer: "First answer." }))
      .mockResolvedValueOnce(answer({ answer: "Second answer, building on the first." }));
    await openAndAsk(vi.fn(), "first question", "First answer.");

    fireEvent.change(screen.getByPlaceholderText("Ask about this book…"), {
      target: { value: "what about that?" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    await screen.findByText("Second answer, building on the first.");

    // The second call carries the first turn as history (multi-turn memory).
    const secondCallOpts = askBookMock.mock.calls[1][2];
    expect(secondCallOpts.history).toHaveLength(1);
    expect(secondCallOpts.history[0]).toEqual({
      question: "first question",
      answer: "First answer.",
    });
    // Both turns are visible in the thread.
    expect(screen.getByText("First answer.")).toBeTruthy();
  });

  it("branches a tangent off a turn ('what about that?')", async () => {
    askBookMock.mockResolvedValue(answer());
    await openAndAsk();
    // Fork a tangent from the first answer.
    fireEvent.click(screen.getByRole("button", { name: "↳ what about that?" }));
    // A branch picker appears with the trunk + the new tangent.
    await screen.findByTestId("talk-branches");
    expect(screen.getByRole("button", { name: "main" })).toBeTruthy();
  });

  it("persists the conversation across a re-mount (the bookmark carries it)", async () => {
    askBookMock.mockResolvedValue(answer({ answer: "A persisted answer." }));
    const { unmount } = await openAndAsk(vi.fn(), "a question", "A persisted answer.");
    expect(screen.getByText("A persisted answer.")).toBeTruthy();
    unmount();

    // Re-mount the SAME book: the bookmark shows the prior turn count, and the
    // thread is restored from session state (not refetched).
    render(<TalkToBook documentId="doc-x" title="A Book" onJumpToPage={vi.fn()} />);
    expect(screen.getByTestId("talk-turn-count").textContent).toBe("1");
    fireEvent.click(screen.getByTestId("talk-to-book-bookmark"));
    expect(screen.getByText("A persisted answer.")).toBeTruthy();
  });

  it("resets a malformed saved conversation instead of crashing the bookmark", () => {
    window.sessionStorage.setItem(
      "antiek.read.talk.doc-x",
      JSON.stringify({
        active_branch_id: "trunk",
        branches: [{ branch_id: "trunk", forked_from: null, messages: [{ id: "bad" }] }],
      }),
    );

    render(<TalkToBook documentId="doc-x" title="A Book" onJumpToPage={vi.fn()} />);

    expect(screen.queryByTestId("talk-turn-count")).toBeNull();
    fireEvent.click(screen.getByTestId("talk-to-book-bookmark"));
    expect(screen.getByText(/Ask a cited question about this book/)).toBeTruthy();
  });

  it("resets saved state whose active branch no longer exists", () => {
    window.sessionStorage.setItem(
      "antiek.read.talk.doc-x",
      JSON.stringify({
        active_branch_id: "missing",
        branches: [{ branch_id: "trunk", forked_from: null, messages: [] }],
      }),
    );

    render(<TalkToBook documentId="doc-x" title="A Book" onJumpToPage={vi.fn()} />);

    expect(screen.queryByTestId("talk-turn-count")).toBeNull();
    fireEvent.click(screen.getByTestId("talk-to-book-bookmark"));
    expect(screen.getByText(/Ask a cited question about this book/)).toBeTruthy();
  });

  it("presents the surface as async cited Q&A, not live voice chat", () => {
    render(<TalkToBook documentId="doc-x" title="A Book" onJumpToPage={vi.fn()} />);

    expect(screen.getByTestId("talk-to-book-bookmark").textContent).toBe("Ask this book");
    fireEvent.click(screen.getByTestId("talk-to-book-bookmark"));
    expect(screen.getByLabelText("Ask this book")).toBeTruthy();
    expect(screen.getByText("Ask “A Book”")).toBeTruthy();
    expect(screen.getByText(/Answers return asynchronously/i)).toBeTruthy();
    expect(screen.queryByText(/live voice/i)).toBeNull();
    expect(screen.queryByText(/real[- ]?time/i)).toBeNull();
  });

  it("restores a valid saved branch without refetching", () => {
    window.sessionStorage.setItem(
      "antiek.read.talk.doc-x",
      JSON.stringify({
        active_branch_id: "trunk",
        branches: [
          {
            branch_id: "trunk",
            forked_from: null,
            messages: [
              {
                id: "turn-saved",
                question: "saved question",
                answer: "Saved answer.",
                citations: [{ ...cite(), future_field: 42 }],
                grounded: true,
                future_field: "kept by newer code",
              },
            ],
            future_field: "kept by newer code",
          },
        ],
        future_field: "kept by newer code",
      }),
    );

    render(<TalkToBook documentId="doc-x" title="A Book" onJumpToPage={vi.fn()} />);

    expect(screen.getByTestId("talk-turn-count").textContent).toBe("1");
    fireEvent.click(screen.getByTestId("talk-to-book-bookmark"));
    expect(screen.getByText("Saved answer.")).toBeTruthy();
    expect(askBookMock).not.toHaveBeenCalled();
  });

  it("mounts a read-aloud control for the answer (M3 wiring)", async () => {
    askBookMock.mockResolvedValue(answer());
    await openAndAsk();
    const readAloud = screen.getByTestId("read-aloud");
    expect(readAloud.getAttribute("data-text")).toBe("Page seven discusses entanglement.");
  });

  it("an ungrounded answer is labelled honestly", async () => {
    askBookMock.mockResolvedValue(
      answer({ answer: "No readable text here.", citations: [], grounded: false }),
    );
    await openAndAsk(vi.fn(), "anything", "No readable text here.");
    expect(screen.getByText(/isn’t grounded in the book’s text/)).toBeTruthy();
  });

  it("frames ask failures as retryable engine failures and adds no fake answer", async () => {
    askBookMock.mockRejectedValue(new Error("Talk-to-book isn’t available right now."));
    render(<TalkToBook documentId="doc-x" title="A Book" onJumpToPage={vi.fn()} />);
    fireEvent.click(screen.getByTestId("talk-to-book-bookmark"));
    fireEvent.change(screen.getByPlaceholderText("Ask about this book…"), {
      target: { value: "what does this book say?" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));

    expect(await screen.findByText(/Couldn’t ask this book/i)).toBeTruthy();
    expect(screen.getByText(/Engine: Talk-to-book isn’t available right now/i)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Try again" })).toBeTruthy();
    expect(screen.queryByText("the book")).toBeNull();
  });
});
