import { useState, useMemo } from "react";
import { Link } from "react-router-dom";

import { useInvestigation } from "../../hooks/useInvestigation";
import { useInvestigationList } from "../../hooks/useInvestigationList";
import {
  API_BASE,
  composeResearchArtifacts,
  type InvestigationSummary,
} from "../../lib/api";
import { useChaseDraftHandoffs } from "../ResearchWorkstation/chaseHandoffs";
import { deriveNotes } from "../ResearchWorkstation/NotesPanel";
import Thinking from "../../shared/Thinking";

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
  const handoffs = useChaseDraftHandoffs(readingThreadId);
  const { investigations } = useInvestigationList({ limit: 200, pollIntervalMs: 0 });
  const summariesById = useMemo(
    () => new Map(investigations.map((item) => [item.investigation_id, item])),
    [investigations],
  );
  const [copiedMergePacket, setCopiedMergePacket] = useState(false);
  const [draftBusy, setDraftBusy] = useState(false);
  const [draftMergePath, setDraftMergePath] = useState<string | null>(null);
  const [draftMergeIds, setDraftMergeIds] = useState<string[]>([]);
  const [draftError, setDraftError] = useState<string | null>(null);

  // "Working" only when the thread is genuinely running (a distill / talk in
  // flight). A not_found thread (nothing has happened on this book yet) is
  // calm, not "thinking".
  const working = reading.status === "in_progress";
  const readyHandoffs = useMemo(
    () =>
      handoffs.filter(
        (handoff) => summariesById.get(handoff.child_investigation_id)?.status === "completed",
      ),
    [handoffs, summariesById],
  );
  const readyIds = useMemo(
    () => readyHandoffs.map((handoff) => handoff.child_investigation_id),
    [readyHandoffs],
  );

  async function copyMergePacket() {
    const payload = {
      kind: "antiek.reader.chase_merge_packet",
      document_id: documentId,
      title: title ?? null,
      parent_reading_thread_id: readingThreadId,
      child_investigation_ids: handoffs.map((handoff) => handoff.child_investigation_id),
      ready_child_investigation_ids: readyHandoffs.map((handoff) => handoff.child_investigation_id),
      source_passages: handoffs.map((handoff) => handoff.source_passage),
      next_step: "open the child researches, export completed artifacts, then draft a merge before changing the book asset",
      no_spend: true,
    };
    await navigator.clipboard?.writeText(JSON.stringify(payload, null, 2));
    setCopiedMergePacket(true);
  }

  async function draftReadyChases() {
    if (readyIds.length < 2) {
      setDraftError("Two completed chases are needed for a draft merge.");
      return;
    }
    setDraftBusy(true);
    setDraftError(null);
    try {
      const result = await composeResearchArtifacts(readyIds, true);
      setDraftMergePath(result.draft_merge_path ?? result.path);
      setDraftMergeIds(readyIds);
    } catch (error) {
      setDraftError(error instanceof Error ? error.message : String(error));
    } finally {
      setDraftBusy(false);
    }
  }

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

      {handoffs.length > 0 ? (
        <section
          className="border-b border-rule px-4 py-3 dark:border-charcoal-1"
          aria-label="Saved research handoffs"
        >
          <div className="mb-2 flex items-center justify-between gap-2">
            <p className="font-mono text-[10px] uppercase tracking-wide text-shadow-1 dark:text-moonlight">
              Saved chases
            </p>
            <div className="flex shrink-0 items-center gap-2">
              <button
                type="button"
                onClick={() => void draftReadyChases()}
                disabled={draftBusy || readyIds.length < 2}
                className="font-mono text-[11px] text-ink hover:underline disabled:cursor-not-allowed disabled:text-ink-mute dark:text-bright dark:disabled:text-moonlight"
                title={
                  readyIds.length >= 2
                    ? "Draft a no-mutation merge of completed chase artifacts"
                    : "Two completed chases are needed for a draft merge"
                }
              >
                {draftBusy ? "drafting" : "draft ready"}
              </button>
              <button
                type="button"
                onClick={copyMergePacket}
                className="font-mono text-[11px] text-ink hover:underline dark:text-bright"
                title="Copy a no-spend packet for a later draft merge"
              >
                {copiedMergePacket ? "copied" : "copy packet"}
              </button>
            </div>
          </div>
          {draftMergePath ? (
            <p className="mb-2 font-mono text-[10px] text-shadow-1 dark:text-moonlight">
              Draft written{" "}
              {draftMergeIds.length >= 2 ? (
                <a
                  href={draftMergeHref(draftMergeIds)}
                  target="_blank"
                  rel="noreferrer"
                  className="text-ink underline dark:text-bright"
                >
                  open
                </a>
              ) : null}
            </p>
          ) : null}
          {draftError ? (
            <p className="mb-2 font-serif text-[12px] text-emperor">{draftError}</p>
          ) : null}
          <ol className="space-y-1.5">
            {handoffs.map((handoff) => (
              <li
                key={`${handoff.parent_investigation_id}:${handoff.child_investigation_id}`}
                className="rounded-hog border border-rule bg-ice-0 px-2 py-1.5 dark:bg-charcoal-2"
              >
                <span className="mb-1 inline-flex rounded-hog border border-rule px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-wide text-shadow-1 dark:text-moonlight">
                  {handoffStatusLabel(summariesById.get(handoff.child_investigation_id))}
                </span>
                <p className="line-clamp-2 font-serif text-[13px] leading-snug text-ink dark:text-bright">
                  {handoff.source_passage}
                </p>
                <Link
                  to={`/inv/${handoff.child_investigation_id}`}
                  className="mt-1 inline-flex font-mono text-[11px] text-shadow-1 hover:text-ink hover:underline dark:text-moonlight dark:hover:text-bright"
                >
                  open research
                </Link>
              </li>
            ))}
          </ol>
        </section>
      ) : null}

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
    </aside>
  );
}

function draftMergeHref(investigationIds: string[]): string {
  const params = new URLSearchParams();
  for (const id of investigationIds) params.append("investigation_ids", id);
  return `${API_BASE}/research/artifacts/compose/draft-merge.html?${params.toString()}`;
}

function handoffStatusLabel(summary: InvestigationSummary | undefined): string {
  if (!summary) return "saved locally";
  switch (summary.status) {
    case "completed":
      return "ready to export";
    case "in_progress":
      return "still working";
    case "failed":
    case "stopped":
      return "needs attention";
    case "not_found":
      return "not found";
  }
}
