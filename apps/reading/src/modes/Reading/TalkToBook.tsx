import { useCallback, useState } from "react";

import livingTvArt from "../../brand/werner/poses/session/werner_living_tv_session_v1.webp";
import thinkingArt from "../../brand/werner/poses/session/werner_thinking_session_v1.png";
import { LemonButton } from "../../components/lemon";
import { askBook, judgeBookAnswer } from "../../api/books";
import type { BookCitation } from "../../api/books";
import ReadAloud from "../../components/voice/ReadAloud";
import { emitWernerExperience } from "../../werner/reactionBus";
import { useTalkThread } from "./useTalkThread";
import type { TalkMessage } from "./useTalkThread";

/**
 * TalkToBook — the floating bookmark: a book-level MULTI-TURN conversation
 * (Read SPR-08 M2).
 *
 * This is the NEW book-level surface (the SPR-04 selection FloatMenu Dialogue
 * stays ONE-SHOT — it is NOT converted). A persistent conversation that:
 *   • remembers earlier turns and sends the recent tail as context each turn
 *     (multi-turn, backed by `POST /books/{id}/ask`);
 *   • CITES page-level locations — clicking a citation jumps the SPR-07 reader
 *     to that page (reuses the reader's `setPageIndex` via `onJumpToPage`);
 *   • BRANCHES into a "what about that?" tangent off any turn;
 *   • persists per-book in SESSION state (the floating bookmark) so it survives
 *     page navigation (`useTalkThread` → sessionStorage, the usePosition
 *     precedent — NOT substrate truth);
 *   • reads any answer aloud via the SPR-14 shared TTS service (`ReadAloud`).
 *
 * §9.0: a withheld region can never be cited — the backend search gate keeps a
 * withheld body out of the model context and the citation set, so this surface
 * never receives one. An ungrounded answer (no extractable text / withheld) is
 * labelled honestly.
 *
 * APPROXIMATE PAGES: a citation whose page did not resolve to a `Page N` marker
 * is shown as "open the book", NEVER a fabricated page number (no false
 * precision — rigor #1).
 */

export interface TalkToBookProps {
  documentId: string;
  title: string | null;
  /** Jump the reader to a page (the reader passes its windowForTocPage +
   * setPageIndex composition). Reuses the EXISTING page navigation, not a
   * parallel one. */
  onJumpToPage: (pageIndex: number) => void;
}

export default function TalkToBook({ documentId, title, onJumpToPage }: TalkToBookProps) {
  const thread = useTalkThread(documentId);
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const turnCount = thread.messages.length;
  const branchCount = thread.state.branches.length;

  const ask = useCallback(async () => {
    const q = draft.trim();
    if (!q || pending) return;
    setError(null);
    setDraft("");
    // The recent tail of the active branch is the multi-turn context. Only
    // completed turns are carried (a pending/failed turn has no answer yet).
    const history = thread.messages
      .filter((m): m is TalkMessage & { answer: string } => m.answer !== null)
      .map((m) => ({ question: m.question, answer: m.answer }));
    const messageId = thread.startTurn(q);
    setPending(true);
    try {
      const res = await askBook(documentId, q, { history });
      thread.completeTurn(
        messageId,
        res.answer,
        res.citations,
        res.grounded,
        res.answer_id,
        res.capture_status,
      );
      // Living-TV: a landed book answer is a noted craft beat.
      emitWernerExperience("note_saved");
    } catch (e: unknown) {
      thread.failTurn(messageId);
      setError(e instanceof Error ? e.message : String(e));
      emitWernerExperience("fail");
    } finally {
      setPending(false);
    }
  }, [draft, pending, thread, documentId]);

  if (!open) {
    return (
      <button
        type="button"
        data-testid="talk-to-book-bookmark"
        onClick={() => {
          // Living-TV: opening the bookmark is a curious glance.
          emitWernerExperience("highlight");
          setOpen(true);
        }}
        title="Talk to this book"
        className="fixed bottom-6 right-6 z-30 flex items-center gap-2 rounded-full bg-ink text-white px-4 py-2 text-sm font-serif shadow-lg hover:opacity-90"
      >
        Talk to this book
        {turnCount > 0 && (
          <span className="rounded-full bg-white/25 px-1.5 text-[11px] font-mono" data-testid="talk-turn-count">
            {turnCount}
          </span>
        )}
      </button>
    );
  }

  return (
    <aside
      data-testid="talk-to-book"
      className="fixed bottom-6 right-6 z-30 flex flex-col w-96 max-h-[70vh] rounded-lg border border-rule dark:border-charcoal-1 bg-ice-0 dark:bg-charcoal-2 shadow-2xl"
      aria-label="Talk to this book"
    >
      <header className="flex items-center justify-between gap-2 border-b border-rule dark:border-charcoal-1 px-3 py-2">
        <div className="flex min-w-0 items-center gap-2">
          <img
            src={thinkingArt}
            alt=""
            aria-hidden="true"
            data-testid="talk-to-book-werner-brand"
            className="h-8 w-8 shrink-0 object-contain"
          />
          <span className="text-[13px] font-serif text-ink dark:text-bright truncate">
            Talk to “{title ?? "this book"}”
          </span>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {turnCount > 0 && (
            <button
              type="button"
              onClick={thread.reset}
              className="text-[11px] font-mono text-shadow-1 dark:text-moonlight hover:underline"
              title="Clear the conversation"
            >
              clear
            </button>
          )}
          <button
            type="button"
            onClick={() => setOpen(false)}
            aria-label="Close"
            className="text-[13px] font-mono text-ink dark:text-bright hover:opacity-70"
          >
            ✕
          </button>
        </div>
      </header>

      <img
        src={livingTvArt}
        alt=""
        aria-hidden="true"
        data-testid="talk-to-book-living-tv-art"
        className="h-12 w-full object-cover object-center antiek-living-tv-invent"
        loading="lazy"
        decoding="async"
      />

      {/* Branch picker — the multi-turn thread can fork a tangent; the bookmark
          carries the active branch and lets the reader return to the trunk. */}
      {branchCount > 1 && (
        <div className="flex items-center gap-1.5 border-b border-rule dark:border-charcoal-1 px-3 py-1.5 overflow-x-auto" data-testid="talk-branches">
          {thread.state.branches.map((b, i) => (
            <button
              key={b.branch_id}
              type="button"
              onClick={() => thread.setActiveBranch(b.branch_id)}
              aria-pressed={b.branch_id === thread.activeBranchId}
              className={`shrink-0 rounded px-2 py-0.5 text-[11px] font-mono ${
                b.branch_id === thread.activeBranchId
                  ? "bg-ink text-white"
                  : "bg-ice-3 dark:bg-charcoal-1 text-ink dark:text-bright hover:bg-ice-4"
              }`}
            >
              {b.forked_from === null ? "main" : `tangent ${i}`}
            </button>
          ))}
        </div>
      )}

      <div className="flex-1 min-h-0 overflow-y-auto px-3 py-2 flex flex-col gap-3">
        {thread.messages.length === 0 && (
          <p className="text-[13px] text-shadow-1 dark:text-moonlight italic">
            Ask anything about this book. Answers cite the pages they come from —
            click a citation to jump there.
          </p>
        )}
        {thread.messages.map((m) => (
          <TalkMessageView
            key={m.id}
            message={m}
            onJumpToPage={onJumpToPage}
            onBranch={() => thread.branchFrom(m.id)}
            onJudged={(verdict) => thread.setJudgment(m.id, verdict)}
            documentId={documentId}
          />
        ))}
        {pending && (
          <p className="text-[12px] text-shadow-1 dark:text-moonlight italic" role="status">
            Reading the book…
          </p>
        )}
        {error && (
          <p className="text-[13px] text-emperor" role="alert">
            {error}
          </p>
        )}
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          void ask();
        }}
        className="flex items-end gap-2 border-t border-rule dark:border-charcoal-1 px-3 py-2"
      >
        <textarea
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="Ask about this book…"
          rows={2}
          className="flex-1 bg-ice-1 dark:bg-charcoal-1 text-ink dark:text-bright rounded-md px-2 py-1.5 text-[13px] resize-none outline-none border border-rule dark:border-charcoal-1"
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              void ask();
            }
          }}
        />
        <LemonButton type="submit" size="sm" variant="primary" disabled={pending || !draft.trim()}>
          Ask
        </LemonButton>
      </form>
    </aside>
  );
}

function TalkMessageView({
  message,
  onJumpToPage,
  onBranch,
  onJudged,
  documentId,
}: {
  message: TalkMessage;
  onJumpToPage: (pageIndex: number) => void;
  onBranch: () => void;
  onJudged: (verdict: "good" | "bad") => void;
  documentId: string;
}) {
  const [judging, setJudging] = useState<"good" | "bad" | null>(null);
  const [judgmentError, setJudgmentError] = useState(false);

  const judge = async (verdict: "good" | "bad") => {
    if (!message.answer_id || judging || message.judgment) return;
    setJudging(verdict);
    setJudgmentError(false);
    try {
      await judgeBookAnswer(documentId, message.answer_id, verdict);
      onJudged(verdict);
    } catch {
      setJudgmentError(true);
    } finally {
      setJudging(null);
    }
  };

  return (
    <div className="flex flex-col gap-1.5">
      {/* The reader's question — visibly user-sourced. */}
      <p className="text-[13px] font-serif text-ink dark:text-bright">
        <span className="text-[10px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight block mb-0.5">
          you
        </span>
        {message.question}
      </p>
      {message.answer !== null && (
        <div className="rounded-md bg-ice-2 dark:bg-charcoal-1 px-2.5 py-2">
          <span className="text-[10px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight block mb-0.5">
            the book
          </span>
          <p className="text-[13px] text-ink dark:text-bright whitespace-pre-wrap leading-relaxed">
            {message.answer}
          </p>

          {message.answer_id && (
            <div className="mt-2 flex items-center gap-2" aria-label="Rate this answer">
              {message.judgment ? (
                <span className="text-[11px] font-mono text-shadow-1 dark:text-moonlight" role="status">
                  Marked {message.judgment}
                </span>
              ) : (
                <>
                  <button
                    type="button"
                    onClick={() => void judge("good")}
                    disabled={judging !== null}
                    className="text-[11px] font-mono text-shadow-1 dark:text-moonlight hover:text-ink dark:hover:text-bright disabled:opacity-50"
                    aria-label="Mark answer good"
                  >
                    {judging === "good" ? "Saving…" : "Good"}
                  </button>
                  <button
                    type="button"
                    onClick={() => void judge("bad")}
                    disabled={judging !== null}
                    className="text-[11px] font-mono text-shadow-1 dark:text-moonlight hover:text-emperor disabled:opacity-50"
                    aria-label="Mark answer bad"
                  >
                    {judging === "bad" ? "Saving…" : "Bad"}
                  </button>
                </>
              )}
              {judgmentError && (
                <span className="text-[11px] text-emperor" role="alert">Couldn’t save judgment.</span>
              )}
            </div>
          )}
          {message.capture_unavailable && (
            <p className="mt-2 text-[11px] text-sun-deep dark:text-sun" role="status">
              Answer delivered, but rating is unavailable because its evidence record could not be saved.
            </p>
          )}

          {!message.grounded && (
            <p className="mt-1 text-[12px] text-sun-deep dark:text-sun italic">
              No readable passages backed this — it isn’t grounded in the book’s text.
            </p>
          )}

          {/* Page-level citations → jump into the SPR-07 reader. An unresolved
              page is shown honestly as "open the book", never a fake page. */}
          {message.citations.length > 0 && (
            <ul className="mt-1.5 flex flex-wrap gap-1" aria-label="Citations">
              {message.citations.map((c) => (
                <CitationChip key={c.chunk_id} citation={c} onJumpToPage={onJumpToPage} />
              ))}
            </ul>
          )}

          <div className="mt-2 flex items-center gap-2">
            {/* TTS via the SPR-14 shared service — reads THIS answer aloud. The
                answer is model-generated prose with no withheld §9.0 chunk
                (the gate already excluded any), so no chunkId guard is needed
                here; ReadAloud still labels it model-sourced. */}
            <ReadAloud text={message.answer} label="🔊 Read aloud" />
            <button
              type="button"
              onClick={onBranch}
              className="text-[11px] font-mono text-shadow-1 dark:text-moonlight hover:underline"
              title="Explore a tangent from here"
            >
              ↳ what about that?
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function CitationChip({
  citation,
  onJumpToPage,
}: {
  citation: BookCitation;
  onJumpToPage: (pageIndex: number) => void;
}) {
  const resolved = citation.page_resolved && citation.page_index !== null;
  if (resolved) {
    return (
      <li>
        <button
          type="button"
          onClick={() => onJumpToPage(citation.page_index as number)}
          title={citation.snippet}
          className="rounded bg-aurora/15 text-aurora-deep dark:text-aurora px-1.5 py-0.5 text-[11px] font-mono hover:bg-aurora/25"
        >
          p.{(citation.page_index as number) + 1}
        </button>
      </li>
    );
  }
  // Unresolved page — honest label, no jump (we don't invent a page).
  return (
    <li>
      <span
        title={citation.snippet}
        className="rounded bg-ice-3 dark:bg-charcoal-1 text-shadow-1 dark:text-moonlight px-1.5 py-0.5 text-[11px] font-mono italic"
      >
        in the book (page not pinpointed)
      </span>
    </li>
  );
}
