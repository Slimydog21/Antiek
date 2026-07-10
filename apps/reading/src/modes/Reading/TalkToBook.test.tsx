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

const {
  askBookMock,
  fetchDepthTiersMock,
  collectDeepResearchSpawnIds,
  listRecentDeepResearchSpawnIds,
} = vi.hoisted(() => ({
  askBookMock: vi.fn(),
  fetchDepthTiersMock: vi.fn(async () => ({
    active_depth_tier: null as string | null,
    active_preset: null,
    tiers: [],
  })),
  collectDeepResearchSpawnIds: vi.fn(() => [] as string[]),
  listRecentDeepResearchSpawnIds: vi.fn(() => [] as string[]),
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
    autoPromoteAfterLoad?: boolean;
    seedTitle?: string;
    researchTier?: string | null;
    onPromoted?: () => void;
  }) => (
    <div
      data-testid="twin-notes-panel-stub"
      data-asset-id={props.assetId}
      data-auto-load={String(Boolean(props.autoLoad))}
      data-auto-seed={String(Boolean(props.autoSeedIfEmpty))}
      data-auto-promote={String(Boolean(props.autoPromoteAfterLoad))}
      data-seed-title={props.seedTitle ?? ""}
      data-research-tier={(props.researchTier || "").trim().toLowerCase() || ""}
    >
      twins={props.assetId}
      {props.onPromoted ? (
        <button
          type="button"
          data-testid="talk-to-book-twin-promote-notify"
          onClick={() => props.onPromoted?.()}
        >
          notify promote
        </button>
      ) : null}
    </div>
  ),
}));

vi.mock("../../components/engagement/ResearchContextPanel", () => ({
  ResearchContextPanel: (props: {
    assetId: string;
    autoLoad?: boolean;
    researchTier?: string | null;
  }) => (
    <div
      data-testid="research-context-panel-stub"
      data-asset-id={props.assetId}
      data-auto-load={String(Boolean(props.autoLoad))}
      data-research-tier={(props.researchTier || "").trim().toLowerCase() || ""}
    >
      context={props.assetId}
    </div>
  ),
}));

// Residual (ang): collective multi-select from talk bookmark (parity ResearchThis fc).
vi.mock("../../workspace/collectDeepResearchSpawnIds", () => ({
  collectDeepResearchSpawnIds: (...args: unknown[]) =>
    collectDeepResearchSpawnIds(...args),
}));

vi.mock("../../workspace/recentDeepResearchSpawns", () => ({
  listRecentDeepResearchSpawnIds: (...args: unknown[]) =>
    listRecentDeepResearchSpawnIds(...args),
}));

vi.mock("../../workspace/windowsStore", () => ({
  useWindows: (sel: (s: { windows: Record<string, unknown> }) => unknown) =>
    sel({ windows: {} }),
}));

vi.mock("../../components/engagement/CollectiveResearchPanel", () => ({
  CollectiveResearchPanel: (props: {
    availableSpawnIds: string[];
    parentAssetId?: string | null;
    recentSpawnIds?: readonly string[] | null;
    openSpawnIds?: readonly string[] | null;
    onRecentSpawnsCleared?: () => void;
    onDocMerged?: () => void;
  }) => (
    <div
      data-testid="collective-research-panel-stub"
      data-recent={
        props.recentSpawnIds != null ? props.recentSpawnIds.join(",") : ""
      }
      data-has-clear={props.onRecentSpawnsCleared ? "1" : "0"}
      data-has-merged={props.onDocMerged ? "1" : "0"}
    >
      {props.parentAssetId}:{props.availableSpawnIds.join(",")}
      {props.onDocMerged ? (
        <button
          type="button"
          data-testid="talk-to-book-collective-merge-notify"
          onClick={() => props.onDocMerged?.()}
        >
          notify merge
        </button>
      ) : null}
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
  collectDeepResearchSpawnIds.mockReset().mockReturnValue([]);
  listRecentDeepResearchSpawnIds.mockReset().mockReturnValue([]);
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

  it("mounts TwinNotes recursive note-taker for the book asset (agm)", async () => {
    render(
      <TalkToBook documentId="doc-twin" title="Twin Book" onJumpToPage={vi.fn()} />,
    );
    // Bookmark closed: twins not mounted until open.
    expect(screen.queryByTestId("talk-to-book-twins-mount")).toBeNull();
    fireEvent.click(screen.getByTestId("talk-to-book-bookmark"));
    // Residual (aoa): HTML-first talk surface + competitive/twin FUTURE links.
    const root = screen.getByTestId("talk-to-book");
    expect(root.getAttribute("data-view-format")).toBe("html");
    expect(root.getAttribute("data-html-first")).toBe("true");
    expect(root.getAttribute("data-document-id")).toBe("doc-twin");
    expect(root.getAttribute("data-seamless-talk-bookmark")).toBe("true");
    expect(
      screen
        .getByTestId("talk-to-book-competitive-scorecard-link")
        .getAttribute("href"),
    ).toBe("/settings#settings-competitive-dr-scorecard");
    expect(
      screen
        .getByTestId("talk-to-book-competitive-dr-future-agent-link")
        .getAttribute("href") || "",
    ).toMatch(/FUTURE-AGENT-SPEC-competitive-deep-research-quality/);
    // Residual (apt): hop/stage pipeline honesty on talk competitive links.
    const talkComp = screen.getByTestId("talk-to-book-competitive-links");
    expect(talkComp.getAttribute("data-hop-pipeline")).toBe("api");
    expect(talkComp.getAttribute("data-stage-pipeline")).toBe("ape");
    expect(
      screen.getByTestId("talk-to-book-competitive-pipeline-hint").textContent,
    ).toMatch(/insights.*questions.*sources/i);
    expect(
      screen
        .getByTestId("talk-to-book-twin-completeness-future-agent-link")
        .getAttribute("href") || "",
    ).toMatch(/FUTURE-AGENT-SPEC-twin-note-taker-completeness-matrix/);
    const mount = screen.getByTestId("talk-to-book-twins-mount");
    expect(mount.getAttribute("data-view-format")).toBe("html");
    expect(mount.getAttribute("data-document-id")).toBe("doc-twin");
    expect(mount.getAttribute("data-seamless-talk-twins")).toBe("true");
    const twins = screen.getByTestId("twin-notes-panel-stub");
    expect(twins.getAttribute("data-asset-id")).toBe("doc-twin");
    expect(twins.getAttribute("data-auto-load")).toBe("true");
    expect(twins.getAttribute("data-auto-seed")).toBe("true");
    expect(twins.getAttribute("data-seed-title")).toBe("Twin Book");
    // Residual (ams): ResearchContext on talk bookmark with depth prefill.
    const ctxMount = screen.getByTestId("talk-to-book-context-mount");
    expect(ctxMount.getAttribute("data-document-id")).toBe("doc-twin");
    expect(ctxMount.getAttribute("data-seamless-talk-context")).toBe("true");
    expect(ctxMount.getAttribute("data-research-tier")).toMatch(
      /deep|fast|wrestle/,
    );
    const ctx = screen.getByTestId("research-context-panel-stub");
    expect(ctx.getAttribute("data-asset-id")).toBe("doc-twin");
    expect(ctx.getAttribute("data-auto-load")).toBe("true");
    expect(ctx.getAttribute("data-research-tier")).toMatch(/deep|fast|wrestle/);
    // Residual (ana): promote remounts twins + context (parity amy ResearchThis).
    expect(twins.getAttribute("data-auto-promote")).toBe("true");
    expect(
      screen
        .getByTestId("talk-to-book-twins-refresh")
        .getAttribute("data-refresh-key"),
    ).toBe("0");
    expect(
      screen
        .getByTestId("talk-to-book-context-refresh")
        .getAttribute("data-refresh-key"),
    ).toBe("0");
    fireEvent.click(screen.getByTestId("talk-to-book-twin-promote-notify"));
    await waitFor(() => {
      expect(
        screen
          .getByTestId("talk-to-book-twins-refresh")
          .getAttribute("data-refresh-key"),
      ).toBe("1");
    });
    expect(
      screen
        .getByTestId("talk-to-book-context-refresh")
        .getAttribute("data-refresh-key"),
    ).toBe("1");
  });

  it("mounts collective panel when open DR spawns exist (ang)", async () => {
    collectDeepResearchSpawnIds.mockReturnValue(["spn_talk_1", "spn_talk_2"]);
    render(
      <TalkToBook
        documentId="doc-talk-coll"
        title="Talk Collective Book"
        onJumpToPage={vi.fn()}
      />,
    );
    // Bookmark closed: collective not mounted until open.
    expect(screen.queryByTestId("talk-to-book-collective-mount")).toBeNull();
    fireEvent.click(screen.getByTestId("talk-to-book-bookmark"));
    const mount = screen.getByTestId("talk-to-book-collective-mount");
    expect(mount.getAttribute("data-view-format")).toBe("html");
    expect(mount.getAttribute("data-document-id")).toBe("doc-talk-coll");
    expect(mount.getAttribute("data-seamless-talk-collective")).toBe("true");
    expect(mount.getAttribute("data-available-spawn-count")).toBe("2");
    // Residual (anq): open-vs-recent honesty stamp.
    expect(mount.getAttribute("data-open-spawn-count")).toMatch(/^\d+$/);
    expect(screen.getByTestId("collective-research-panel-stub").textContent).toMatch(
      /doc-talk-coll:spn_talk_1,spn_talk_2/,
    );
    // Collective merge remounts twins + context (parity ResearchThis and).
    expect(
      screen
        .getByTestId("collective-research-panel-stub")
        .getAttribute("data-has-merged"),
    ).toBe("1");
    expect(
      screen
        .getByTestId("talk-to-book-context-refresh")
        .getAttribute("data-refresh-key"),
    ).toBe("0");
    fireEvent.click(screen.getByTestId("talk-to-book-collective-merge-notify"));
    await waitFor(() => {
      expect(
        screen
          .getByTestId("talk-to-book-context-refresh")
          .getAttribute("data-refresh-key"),
      ).toBe("1");
    });
    expect(
      screen
        .getByTestId("talk-to-book-twins-refresh")
        .getAttribute("data-refresh-key"),
    ).toBe("1");
  });

  it("wires recent_ring into collect + talk collective mount (ang)", () => {
    listRecentDeepResearchSpawnIds.mockReturnValue([
      "spn_talk_recent",
      "spn_talk_older",
    ]);
    collectDeepResearchSpawnIds.mockImplementation(
      (source: { recentSpawnIds?: readonly string[] | null }) =>
        [...(source.recentSpawnIds ?? [])],
    );
    render(
      <TalkToBook
        documentId="doc-talk-recent"
        title="Recent Talk"
        onJumpToPage={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByTestId("talk-to-book-bookmark"));
    expect(collectDeepResearchSpawnIds).toHaveBeenCalled();
    const lastCall = collectDeepResearchSpawnIds.mock.calls.at(-1)?.[0] as {
      recentSpawnIds?: readonly string[];
    };
    expect(lastCall.recentSpawnIds).toEqual([
      "spn_talk_recent",
      "spn_talk_older",
    ]);
    const mount = screen.getByTestId("talk-to-book-collective-mount");
    expect(mount.getAttribute("data-recent-count")).toBe("2");
    expect(mount.getAttribute("data-available-spawn-count")).toBe("2");
    const stub = screen.getByTestId("collective-research-panel-stub");
    expect(stub.getAttribute("data-recent")).toBe(
      "spn_talk_recent,spn_talk_older",
    );
    expect(stub.getAttribute("data-has-clear")).toBe("1");
    expect(stub.textContent).toMatch(
      /doc-talk-recent:spn_talk_recent,spn_talk_older/,
    );
  });

  it("omits collective panel when no open spawns (ang)", () => {
    collectDeepResearchSpawnIds.mockReturnValue([]);
    render(
      <TalkToBook documentId="doc-x" title="A Book" onJumpToPage={vi.fn()} />,
    );
    fireEvent.click(screen.getByTestId("talk-to-book-bookmark"));
    expect(screen.queryByTestId("talk-to-book-collective-mount")).toBeNull();
  });
});
