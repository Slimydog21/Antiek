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
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

import type { AskBookResponse, BookCitation } from "../../api/books";
import TalkToBook from "./TalkToBook";

const { askBookMock, fetchDepthTiersMock } = vi.hoisted(() => ({
  askBookMock: vi.fn(),
  fetchDepthTiersMock: vi.fn(async () => ({
    active_depth_tier: null as string | null,
    active_preset: null,
    tiers: [],
  })),
}));

vi.mock("../../api/books", async (orig) => {
  const actual = await orig<typeof import("../../api/books")>();
  return { ...actual, askBook: askBookMock };
});

vi.mock("../../api/settings", () => ({
  fetchDepthTiers: (...args: unknown[]) => fetchDepthTiersMock(...args),
  fetchDecisionTreeSelection: vi.fn(async () => ({
    model_id: null,
    provider_id: null,
    installed: false,
    notes: [],
    source: "test",
  })),
  fetchSettingsBudget: vi.fn(async () => null),
}));

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

vi.mock("../../components/engagement/DecisionTreeDriverBadge", () => ({
  DecisionTreeDriverBadge: (props: {
    researchTier?: string | null;
  }) => (
    <div
      data-testid="decision-tree-driver-badge-stub"
      data-research-tier={(props.researchTier || "").trim().toLowerCase() || ""}
    >
      driver badge
    </div>
  ),
}));

vi.mock("../../components/engagement/TwinNotesPanel", () => ({
  TwinNotesPanel: (props: {
    assetId: string;
    autoLoad?: boolean;
    autoSeedIfEmpty?: boolean;
    seedTitle?: string;
  }) => (
    <div
      data-testid="twin-notes-panel-stub"
      data-asset-id={props.assetId}
      data-auto-load={String(Boolean(props.autoLoad))}
      data-auto-seed={String(Boolean(props.autoSeedIfEmpty))}
      data-seed-title={props.seedTitle ?? ""}
    >
      twins={props.assetId}
    </div>
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
  fetchDepthTiersMock.mockReset().mockResolvedValue({
    active_depth_tier: null,
    active_preset: null,
    tiers: [],
  });
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
  it("mounts DecisionTreeDriverBadge with researchTier when open (lh)", async () => {
    askBookMock.mockResolvedValue(answer());
    render(<TalkToBook documentId="doc-x" title="A Book" onJumpToPage={vi.fn()} />);
    fireEvent.click(screen.getByTestId("talk-to-book-bookmark"));
    await waitFor(() => {
      expect(screen.getByTestId("talk-to-book-driver-badge-mount")).toBeTruthy();
    });
    expect(
      screen
        .getByTestId("talk-to-book-driver-badge-mount")
        .getAttribute("data-research-tier"),
    ).toBe("deep");
    expect(
      screen
        .getByTestId("decision-tree-driver-badge-stub")
        .getAttribute("data-research-tier"),
    ).toBe("deep");
  });

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
    // Residual (jn): default researchTier deep when Settings unset.
    expect(secondCallOpts.researchTier).toBe("deep");
    // Both turns are visible in the thread.
    expect(screen.getByText("First answer.")).toBeTruthy();
  });

  it("forwards Settings wrestle research_tier on ask (jn)", async () => {
    fetchDepthTiersMock.mockResolvedValue({
      active_depth_tier: "wrestle",
      active_preset: null,
      tiers: [],
    });
    askBookMock.mockResolvedValue(answer({ answer: "Wrestle answer." }));
    render(
      <TalkToBook documentId="doc-x" title="A Book" onJumpToPage={vi.fn()} />,
    );
    fireEvent.click(screen.getByTestId("talk-to-book-bookmark"));
    await waitFor(() => {
      expect(screen.getByTestId("talk-to-book").getAttribute("data-depth-prefill")).toBe(
        "installed",
      );
    });
    expect(screen.getByTestId("talk-to-book").getAttribute("data-research-tier")).toBe(
      "wrestle",
    );
    fireEvent.change(screen.getByPlaceholderText("Ask about this book…"), {
      target: { value: "wrestle this claim" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    await screen.findByText("Wrestle answer.");
    expect(askBookMock).toHaveBeenCalledWith(
      "doc-x",
      "wrestle this claim",
      expect.objectContaining({ researchTier: "wrestle" }),
    );
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

  it("mounts TwinNotes recursive note-taker for the book asset (agm)", () => {
    render(
      <TalkToBook documentId="doc-twin" title="Twin Book" onJumpToPage={vi.fn()} />,
    );
    // Bookmark closed: twins not mounted until open.
    expect(screen.queryByTestId("talk-to-book-twins-mount")).toBeNull();
    fireEvent.click(screen.getByTestId("talk-to-book-bookmark"));
    const mount = screen.getByTestId("talk-to-book-twins-mount");
    expect(mount.getAttribute("data-view-format")).toBe("html");
    expect(mount.getAttribute("data-document-id")).toBe("doc-twin");
    expect(mount.getAttribute("data-seamless-talk-twins")).toBe("true");
    const twins = screen.getByTestId("twin-notes-panel-stub");
    expect(twins.getAttribute("data-asset-id")).toBe("doc-twin");
    expect(twins.getAttribute("data-auto-load")).toBe("true");
    expect(twins.getAttribute("data-auto-seed")).toBe("true");
    expect(twins.getAttribute("data-seed-title")).toBe("Twin Book");
  });
});
