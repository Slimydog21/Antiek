import { useEffect, useState, useMemo } from "react";
import { Link } from "react-router-dom";

import { useInvestigation } from "../../hooks/useInvestigation";
import { useInvestigationList } from "../../hooks/useInvestigationList";
import {
  API_BASE,
  composeResearchArtifacts,
  type InvestigationSummary,
  type ResearchArtifactComposeResponse,
} from "../../lib/api";
import { useChaseDraftHandoffs } from "../ResearchWorkstation/chaseHandoffs";
import { deriveNotes } from "../ResearchWorkstation/NotesPanel";
import {
  getDocumentCompanion,
  listDocumentEvidence,
  type CompanionPayload,
  type EvidenceRowItem,
} from "../../api/companions";
import ReformatReview from "./ReformatReview";
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
 *     ``BrainThinking``) — the same brain-and-aurora-dots signal every
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
  const [draftMergeReceipt, setDraftMergeReceipt] = useState<ResearchArtifactComposeResponse | null>(null);
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
      next_step: "open the child researches, export completed artifacts, then draft a merge; the book itself is never changed",
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
      setDraftMergeReceipt(result);
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
        <p className="text-xs font-mono text-shadow-1 dark:text-moonlight mt-0.5">
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
            <p className="font-mono text-xxs uppercase tracking-wide text-shadow-1 dark:text-moonlight">
              Saved chases
            </p>
            <div className="flex shrink-0 items-center gap-2">
              <button
                type="button"
                onClick={() => void draftReadyChases()}
                disabled={draftBusy || readyIds.length < 2}
                className="font-mono text-xs text-ink hover:underline disabled:cursor-not-allowed disabled:text-ink-mute dark:text-bright dark:disabled:text-moonlight"
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
                className="font-mono text-xs text-ink hover:underline dark:text-bright"
                title="Copy a no-spend packet for a later draft merge"
              >
                {copiedMergePacket ? "copied" : "copy packet"}
              </button>
            </div>
          </div>
          {draftMergeReceipt ? (
            <div
              className="mb-2 rounded-hog border border-rule bg-ice-0 px-2 py-1.5 font-mono text-xxs text-shadow-1 dark:bg-charcoal-2 dark:text-moonlight"
              aria-label="Draft merge receipt"
              role="region"
            >
              <p>
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
              <p className="truncate" title={draftMergeReceipt.draft_merge_path ?? draftMergeReceipt.path}>
                {draftMergeReceipt.draft_merge_path ?? draftMergeReceipt.path}
              </p>
              <p>
                {draftMergeReceipt.members.length} artifacts ·{" "}
                {draftMergeReceipt.members.filter((member) => member.twin_notes_path).length} notes twins
              </p>
              <p className="mt-1 border-t border-rule pt-1 dark:border-charcoal-1">
                Review only · the book is never changed
              </p>
              {draftMergeReceipt.hash_conflicts.length > 0 ? (
                <p className="text-emperor">
                  {draftMergeReceipt.hash_conflicts.length === 1
                    ? "1 hash conflict needs review"
                    : `${draftMergeReceipt.hash_conflicts.length} hash conflicts need review`}
                </p>
              ) : (
                <p>No hash conflicts</p>
              )}
            </div>
          ) : null}
          {draftError ? (
            <p className="mb-2 font-serif text-xs text-emperor">{draftError}</p>
          ) : null}
          <ol className="space-y-1.5">
            {handoffs.map((handoff) => (
              <li
                key={`${handoff.parent_investigation_id}:${handoff.child_investigation_id}`}
                className="rounded-hog border border-rule bg-ice-0 px-2 py-1.5 dark:bg-charcoal-2"
              >
                <span className="mb-1 inline-flex rounded-hog border border-rule px-1.5 py-0.5 font-mono text-xxs uppercase tracking-wide text-shadow-1 dark:text-moonlight">
                  {handoffStatusLabel(summariesById.get(handoff.child_investigation_id))}
                </span>
                <p className="line-clamp-2 font-serif text-sm leading-snug text-ink dark:text-bright">
                  {handoff.source_passage}
                </p>
                <Link
                  to={`/inv/${handoff.child_investigation_id}`}
                  className="mt-1 inline-flex font-mono text-xs text-shadow-1 hover:text-ink hover:underline dark:text-moonlight dark:hover:text-bright"
                >
                  open research
                </Link>
              </li>
            ))}
          </ol>
        </section>
      ) : null}

      {/* Reformat-provenance SPR-02: the review surface renders ONLY for a
          derived document (a plain book shows nothing). */}
      <ReformatReview documentId={documentId} />

      <CompanionSection documentId={documentId} />

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
                  className="mt-[7px] h-1.5 w-1.5 shrink-0 rounded-full bg-aurora"
                  aria-hidden="true"
                />
                <p className="min-w-0 flex-1 font-serif text-sm leading-relaxed text-ink dark:text-bright">
                  {n.kind === "question" ? <span className="italic">Open question: </span> : null}
                  {/* §9 honest attribution — a note the reader authored in-book
                      (a marginalia note) is labelled as theirs, never shown as
                      if the AI distilled it. A model-emerged note carries no
                      such label (the absence is "model"). */}
                  {n.sourceKind === "user" ? (
                    <span className="mr-1 font-mono text-xs uppercase tracking-wide text-shadow-1 dark:text-moonlight">
                      Your note ·
                    </span>
                  ) : null}
                  {n.text}
                  {n.refinements > 0 && n.previousText && (
                    <span className="mt-1 block border-l-2 border-rule pl-2 font-serif text-xs italic leading-relaxed text-ink-mute dark:border-charcoal-1 dark:text-moonlight">
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

/**
 * CompanionSection — the generated document companion in the rail
 * (companions SPR-02). READ-ONLY like the whole rail: it renders the
 * companion's STRUCTURED payload (the sanctioned path — generated content
 * arrives as data and renders as elements; raw generated HTML is never
 * injected anywhere in this path). Claims carry their evidence ids as
 * data attributes (provenance markers, never rendered as labels); a
 * withheld book's claims render metadata lines only (the server withholds
 * the text — the rail never receives it). The "inspect evidence base"
 * toggle is the index's ONLY user surface: an honest debug dump for trust
 * calibration, not a browsable index UI.
 */
function CompanionSection({ documentId }: { documentId: string }) {
  const [state, setState] = useState<
    | { kind: "loading" }
    | { kind: "ready"; payload: CompanionPayload }
    | { kind: "unavailable" }
  >({ kind: "loading" });
  const [inspectRows, setInspectRows] = useState<EvidenceRowItem[] | null>(null);

  useEffect(() => {
    // load-on-mount; a failed/malformed read is the honest unavailable state.
    let cancelled = false;
    void getDocumentCompanion(documentId)
      .then((payload) => {
        if (!cancelled) setState({ kind: "ready", payload });
      })
      .catch(() => {
        if (!cancelled) setState({ kind: "unavailable" });
      });
    return () => {
      cancelled = true;
    };
  }, [documentId]);

  if (state.kind === "loading") return null;
  if (state.kind === "unavailable") return null; // the rail stands alone honestly

  const { payload } = state;
  return (
    <section
      className="border-b border-rule px-4 py-3 dark:border-charcoal-1"
      aria-label="Document companion"
      data-companion-section
    >
      <p className="mb-2 font-mono text-xxs uppercase tracking-wide text-shadow-1 dark:text-moonlight">
        The companion so far
      </p>
      {!payload.servable && (
        <p className="mb-1.5 font-serif text-xs italic text-ink-mute dark:text-moonlight">
          This book's text is withheld — only its metadata shows here.
        </p>
      )}
      {payload.claims.length === 0 && payload.processes.length === 0 ? (
        <p className="font-serif text-xs italic text-ink-mute dark:text-moonlight">
          No companion yet — it gathers as you read and research this book.
        </p>
      ) : (
        <ol className="space-y-1.5" data-companion-claims>
          {payload.claims.slice(0, 5).map((claim) => (
            <li
              key={claim.evidence_id}
              data-evidence-id={claim.evidence_id}
              className="font-serif text-xs leading-relaxed text-ink dark:text-bright"
            >
              <span className="mr-1 font-mono text-xxs uppercase tracking-wide text-shadow-1 dark:text-moonlight">
                {claim.kind === "insight" ? "Finding" : "Open question"} ·
              </span>
              {claim.text ?? <span className="italic">grounded in a withheld source</span>}
            </li>
          ))}
          {payload.processes.slice(0, 4).map((process) => (
            <li
              key={process.evidence_id}
              data-evidence-id={process.evidence_id}
              className="font-mono text-xxs text-shadow-1 dark:text-moonlight"
            >
              {process.label} — {process.status_line}
            </li>
          ))}
        </ol>
      )}
      <div className="mt-2 flex items-center justify-between gap-2">
        <p className="font-mono text-xxs text-shadow-2 dark:text-moonlight">
          generated · rebuilt {payload.rebuilt_at.slice(0, 10)}
        </p>
        <button
          type="button"
          onClick={() => {
            if (inspectRows !== null) {
              setInspectRows(null);
              return;
            }
            void listDocumentEvidence(documentId)
              .then((resp) => setInspectRows(resp.rows))
              .catch(() => setInspectRows([]));
          }}
          className="font-mono text-xxs text-shadow-1 underline decoration-dotted underline-offset-2 hover:text-ink dark:text-moonlight dark:hover:text-bright"
          title="The evidence base's inspect dump — operator debug, read-only"
        >
          {inspectRows !== null ? "close inspect" : "inspect evidence base"}
        </button>
      </div>
      {inspectRows !== null && (
        <div
          className="mt-2 rounded-hog border border-rule bg-ice-0 px-2 py-1.5 font-mono text-xxs text-shadow-1 dark:border-charcoal-1 dark:bg-charcoal-2 dark:text-moonlight"
          data-companion-inspect
          role="region"
          aria-label="Evidence base inspect dump"
        >
          {inspectRows.length === 0 ? (
            <p className="italic">No evidence rows on record.</p>
          ) : (
            <ul className="space-y-1">
              {inspectRows.map((row) => (
                <li key={row.evidence_id} data-evidence-id={row.evidence_id}>
                  {row.kind} · {row.evidence_id}
                  {row.tombstone ? " · tombstone" : ""}
                  <span className="block truncate" title={row.refs.join(" · ")}>
                    {row.refs.join(" · ")}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </section>
  );
}
