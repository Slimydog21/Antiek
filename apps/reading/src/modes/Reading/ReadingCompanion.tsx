import { useEffect, useMemo, useRef, useState } from "react";

import { createResearchCompose, previewResearchCompose } from "../../api/research";
import { useInvestigation } from "../../hooks/useInvestigation";
import { useInvestigationList } from "../../hooks/useInvestigationList";
import { deriveNotes } from "../ResearchWorkstation/NotesPanel";
import Thinking from "../../shared/Thinking";
import LemonButton from "../../components/lemon/LemonButton";
import {
  completedReadingChases,
  reconcileChaseSelection,
  toggleChaseSelection,
} from "./chaseCollective";

/**
 * ReadingCompanion — the Read glass-box (Read SPR-06 M2).
 *
 * The Read analog of the Research vertical's SPR-02/03 surfaces: a calm rail
 * docked beside the open book that makes the AI FELT while you read. It does
 * three things, all by REUSING Wave-1 primitives rather than re-inventing
 * them:
 *
 *  1. The shared "AI is working" beat (``Thinking`` → SPR-02's
 *     ``WernerThinking``) — the same penguin-and-aurora-dots signal every
 *     other door uses, so "the AI is thinking" reads the same in Read as in
 *     Research. Shown only while the book's reading thread is actually
 *     running (a distill / talk-to-book in flight), never as decoration.
 *
 *  2. The running thread of notes + open questions for THIS book — derived
 *     with SPR-03's exact ``deriveNotes`` collapse (insight/question +
 *     living-note refinement, idempotent on reconnect). The notes are the
 *     ones a reader's voice notes distil onto this book's reading thread
 *     (``read-<documentId>``); they are not fabricated. With no provider key
 *     no notes are emitted, so the rail honestly shows its empty state — a
 *     working reader next to an empty companion, not a faked one.
 *
 *  3. Talk-to-book / go-deeper is NOT a second writer. It runs through the
 *     SAME chase path the paragraph rabbit-hole uses (SPR-04 ChaseThread,
 *     mounted by the reader). This rail is read/display only: it introduces
 *     no new endpoint and emits no event of its own, so DuckDB single-writer
 *     is trivially preserved.
 *
 * §9.0 servability: the companion reads the book's reading thread, whose
 * notes were distilled under the same retrieval-time gate as everything else
 * — a gated/restricted book's full text never reaches a note. Reading itself
 * is never AI-gated; only this companion is, so a key being absent dims the
 * companion, not the book.
 *
 * No substrate vocabulary leaks here (copy-lint): "this book", "your notes",
 * "open questions" — never an ``inv-…`` id or "investigation".
 */

export interface ReadingCompanionProps {
  /** The open book. */
  documentId: string;
  /** The book title, for the rail's human framing (never the raw id). */
  title?: string | null;
  /**
   * The book's reading thread id (``read-<documentId>``). The companion
   * READS this thread's events for notes; it is the same id the reader's
   * voice notes distil onto, and the parent the chase descends from. Passed
   * in (not minted here) so the reader and companion agree on one thread.
   */
  readingThreadId: string;
}

export default function ReadingCompanion({
  documentId,
  title,
  readingThreadId,
}: ReadingCompanionProps) {
  // Read/display only — subscribe to the book's reading thread for notes.
  const reading = useInvestigation(readingThreadId);
  const notes = useMemo(() => deriveNotes(reading.events), [reading.events]);
  const { investigations } = useInvestigationList({ limit: 200 });
  const completedChases = useMemo(
    () => completedReadingChases(investigations, readingThreadId),
    [investigations, readingThreadId],
  );
  const availableIds = useMemo(
    () => completedChases.map((chase) => chase.investigationId),
    [completedChases],
  );
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const selectedIdsRef = useRef(selectedIds);
  selectedIdsRef.current = selectedIds;
  const selectionTouched = useRef(false);
  const [review, setReview] = useState<Awaited<ReturnType<typeof previewResearchCompose>> | null>(null);
  const [composeBusy, setComposeBusy] = useState(false);
  const [composeError, setComposeError] = useState<string | null>(null);

  useEffect(() => {
    selectionTouched.current = false;
    setSelectedIds([]);
    setReview(null);
    setComposeError(null);
  }, [readingThreadId]);

  useEffect(() => {
    setSelectedIds((current) =>
      reconcileChaseSelection(availableIds, current, selectionTouched.current),
    );
  }, [availableIds]);

  const toggleChase = (investigationId: string) => {
    selectionTouched.current = true;
    setReview(null);
    setComposeError(null);
    setSelectedIds((current) =>
      toggleChaseSelection(availableIds, current, investigationId),
    );
  };

  const reviewChases = async () => {
    if (selectedIds.length < 2) return;
    const requested = [...selectedIds];
    setComposeBusy(true);
    setComposeError(null);
    try {
      const response = await previewResearchCompose(requested);
      if (
        selectedIdsRef.current.length === requested.length &&
        selectedIdsRef.current.every((id, index) => id === requested[index])
      ) {
        setReview(response);
      }
    } catch (error) {
      setComposeError(error instanceof Error ? error.message : "Couldn’t review these chases.");
    } finally {
      setComposeBusy(false);
    }
  };

  const createCollective = async () => {
    if (!review) return;
    const requested = [...selectedIds];
    setComposeBusy(true);
    setComposeError(null);
    try {
      const response = await createResearchCompose(requested, review.selection_fingerprint);
      if (
        selectedIdsRef.current.length === requested.length &&
        selectedIdsRef.current.every((id, index) => id === requested[index])
      ) {
        setReview(response);
      }
    } catch (error) {
      setReview(null);
      setComposeError(error instanceof Error ? error.message : "The chases changed. Review them again.");
    } finally {
      setComposeBusy(false);
    }
  };

  // "Working" only when the thread is genuinely running (a distill / talk in
  // flight). A not_found thread (nothing has happened on this book yet) is
  // calm, not "thinking".
  const working = reading.status === "in_progress";

  return (
    <aside
      className="w-80 flex-shrink-0 border-l border-rule dark:border-charcoal-1 overflow-y-auto bg-ice-1 dark:bg-charcoal-2 hidden lg:flex lg:flex-col"
      aria-label="Reading companion"
      data-document-id={documentId}
    >
      <header className="px-4 pt-4 pb-3 border-b border-rule dark:border-charcoal-1">
        <p className="font-serif text-sm text-ink dark:text-bright">
          Reading {title ? <span className="italic">{title}</span> : "this book"} with you
        </p>
        <p className="text-[11px] font-mono text-shadow-1 dark:text-moonlight mt-0.5">
          Notes and open questions gather here as you read.
        </p>
      </header>

      {working && (
        <div className="px-4 py-3 border-b border-rule dark:border-charcoal-1">
          <Thinking size={24} status="thinking it through…" />
        </div>
      )}

      <div className="flex-1 min-h-0">
        {notes.length === 0 ? (
          <p className="px-4 py-6 text-sm font-serif text-ink-mute dark:text-moonlight leading-relaxed">
            {working
              ? "Working on it — notes will appear here as the thoughts land."
              : "No notes yet. Highlight a passage and choose Note, or capture a voice note as you read — your notes show up here."}
          </p>
        ) : (
          <ol className="space-y-2.5 px-4 py-4">
            {notes.map((n) => (
              <li
                key={n.noteId}
                className="flex items-start gap-2.5 border-b border-rule pb-2.5 last:border-b-0 dark:border-charcoal-1"
              >
                <span
                  className={`mt-[7px] h-1.5 w-1.5 shrink-0 rounded-full ${
                    n.kind === "question" ? "bg-sun-deep dark:bg-sun" : "bg-aurora"
                  }`}
                  aria-hidden="true"
                />
                <p className="min-w-0 flex-1 font-serif text-[14px] leading-relaxed text-ink dark:text-bright">
                  {n.kind === "question" ? <span className="italic">Open question: </span> : null}
                  {/* §9 honest attribution — a note the reader authored in-book
                      (a marginalia note) is labelled as theirs, never shown as
                      if the AI distilled it. A model-emerged note carries no
                      such label (the absence is "model"). */}
                  {n.sourceKind === "user" ? (
                    <span className="mr-1 font-mono text-[11px] uppercase tracking-wide text-shadow-1 dark:text-moonlight">
                      Your note ·
                    </span>
                  ) : null}
                  {n.text}
                  {n.refinements > 0 && n.previousText && (
                    <span className="mt-1 block border-l-2 border-rule pl-2 font-serif text-[12px] italic leading-relaxed text-ink-mute dark:border-charcoal-1 dark:text-moonlight">
                      was: {n.previousText}
                    </span>
                  )}
                </p>
              </li>
            ))}
          </ol>
        )}
      </div>

      {completedChases.length > 0 && (
        <section className="border-t border-rule px-4 py-4 dark:border-charcoal-1">
          <fieldset>
            <legend className="font-serif text-sm text-ink dark:text-bright">
              Bring completed chases together
            </legend>
            <p className="mt-1 text-[11px] font-mono text-shadow-1 dark:text-moonlight">
              Choose at least two to make one reading.
            </p>
            <div className="mt-3 space-y-2">
              {completedChases.map((chase) => (
                <label key={chase.investigationId} className="flex cursor-pointer items-start gap-2 text-sm font-serif text-ink dark:text-bright">
                  <input
                    type="checkbox"
                    checked={selectedIds.includes(chase.investigationId)}
                    onChange={() => toggleChase(chase.investigationId)}
                    disabled={composeBusy}
                    className="mt-1"
                  />
                  <span>{chase.question}</span>
                </label>
              ))}
            </div>
          </fieldset>

          <div className="mt-3" aria-live="polite">
            {composeError && <p role="alert" className="mb-2 text-xs text-emperor">{composeError}</p>}
            {!review && (
              <LemonButton
                type="button"
                variant="secondary"
                size="sm"
                disabled={selectedIds.length < 2 || composeBusy}
                onClick={() => void reviewChases()}
              >
                {composeBusy ? "Reviewing…" : "Review selected chases"}
              </LemonButton>
            )}
            {review && !review.view_url && (
              <div className="space-y-2">
                <p className="text-xs text-shadow-1 dark:text-moonlight">
                  {review.members.length} sources ready in the order shown.
                </p>
                <LemonButton type="button" variant="primary" size="sm" disabled={composeBusy} onClick={() => void createCollective()}>
                  {composeBusy ? "Creating…" : "Create collective reading"}
                </LemonButton>
              </div>
            )}
            {review?.view_url && (
              <a className="text-sm font-semibold text-ink underline dark:text-bright" href={review.view_url} target="_blank" rel="noreferrer">
                Open collective reading ↗
              </a>
            )}
          </div>
        </section>
      )}
    </aside>
  );
}
