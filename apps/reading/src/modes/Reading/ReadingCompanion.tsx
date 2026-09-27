import { useEffect, useId, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";

import { useInvestigation } from "../../hooks/useInvestigation";
import { useInvestigationList } from "../../hooks/useInvestigationList";
import {
  API_BASE,
  applySourceMerge,
  commitSourceMerge,
  composeResearchArtifacts,
  type InvestigationSummary,
  type ResearchArtifactComposeResponse,
  type SourceMergeApplyResponse,
  type SourceMergeCommitResponse,
  type SourceMergePreviewResponse,
  type SourceMergeReviewPacket,
  type SourceMergeRestoreResponse,
  previewSourceMerge,
  restoreSourceMerge,
} from "../../lib/api";
import { useChaseDraftHandoffs } from "../ResearchWorkstation/chaseHandoffs";
import { deriveNotes } from "../ResearchWorkstation/NotesPanel";
import {
  CompanionRebuildFailedError,
  getDocumentCompanion,
  isCompanionNotFound,
  listDocumentEvidence,
  refreshDocumentCompanion,
  type BuiltCompanion,
  type CompanionResponse,
  type EvidenceRowItem,
} from "../../api/companions";
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
  /** Called after commit/restore changes the served source body. */
  onSourceBodyChanged?: () => void;
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
  onSourceBodyChanged,
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
  const [copiedSourceReviewPacket, setCopiedSourceReviewPacket] = useState(false);
  const [sourceApplyAck, setSourceApplyAck] = useState(false);
  const [sourceApplyConflictAck, setSourceApplyConflictAck] = useState(false);
  const [sourcePreviewBusy, setSourcePreviewBusy] = useState(false);
  const [sourcePreviewReceipt, setSourcePreviewReceipt] = useState<SourceMergePreviewResponse | null>(null);
  const [sourcePreviewError, setSourcePreviewError] = useState<string | null>(null);
  const [sourceCommitAck, setSourceCommitAck] = useState(false);
  const [sourceCommitBusy, setSourceCommitBusy] = useState(false);
  const [sourceCommitReceipt, setSourceCommitReceipt] = useState<SourceMergeCommitResponse | null>(null);
  const [sourceCommitError, setSourceCommitError] = useState<string | null>(null);
  const [sourceRestoreAck, setSourceRestoreAck] = useState(false);
  const [sourceRestoreBusy, setSourceRestoreBusy] = useState(false);
  const [sourceRestoreReceipt, setSourceRestoreReceipt] = useState<SourceMergeRestoreResponse | null>(null);
  const [sourceRestoreError, setSourceRestoreError] = useState<string | null>(null);
  const [sourceApplyBusy, setSourceApplyBusy] = useState(false);
  const [sourceApplyReceipt, setSourceApplyReceipt] = useState<SourceMergeApplyResponse | null>(null);
  const [sourceApplyError, setSourceApplyError] = useState<string | null>(null);
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
      next_step: "open the child researches, export completed artifacts, then draft a merge before changing the book asset",
      no_spend: true,
    };
    await navigator.clipboard?.writeText(JSON.stringify(payload, null, 2));
    setCopiedMergePacket(true);
  }

  async function copySourceMergeReviewPacket() {
    if (!draftMergeReceipt) return;
    const payload = buildSourceMergeReviewPacket({
      documentId,
      title,
      readingThreadId,
      draftMergeReceipt,
      draftMergeIds,
    });
    await navigator.clipboard?.writeText(
      JSON.stringify(
        {
          ...payload,
          next_step: "review the draft merge before any source book or twin-document mutation",
        },
        null,
        2,
      ),
    );
    setCopiedSourceReviewPacket(true);
  }

  function buildSourceMergeApplyRequest() {
    if (!draftMergeReceipt || !sourceApplyAck) return;
    if (draftMergeReceipt.hash_conflicts.length > 0 && !sourceApplyConflictAck) return;
    const packet = buildSourceMergeReviewPacket({
      documentId,
      title,
      readingThreadId,
      draftMergeReceipt,
      draftMergeIds,
    });
    return {
      reviewed_packet: packet,
      expected_content_hashes: Object.fromEntries(
        draftMergeReceipt.members.map((member) => [member.investigation_id, member.content_hash]),
      ),
      acknowledge_reviewed_draft: true,
      acknowledge_source_book_mutation: true,
      acknowledge_twin_document_mutation: true,
      acknowledge_hash_conflicts: sourceApplyConflictAck,
      operator_reviewer: "reader-companion",
    };
  }

  async function previewSourceMergeReceipt() {
    const request = buildSourceMergeApplyRequest();
    if (!request) return;
    setSourcePreviewBusy(true);
    setSourcePreviewError(null);
    try {
      const result = await previewSourceMerge(request);
      setSourcePreviewReceipt(result);
      setSourceCommitAck(false);
      setSourceCommitReceipt(null);
      setSourceCommitError(null);
      setSourceRestoreAck(false);
      setSourceRestoreReceipt(null);
      setSourceRestoreError(null);
    } catch (error) {
      setSourcePreviewError(error instanceof Error ? error.message : String(error));
    } finally {
      setSourcePreviewBusy(false);
    }
  }

  async function commitSourceMergeReceipt() {
    const request = buildSourceMergeApplyRequest();
    if (!request || !sourcePreviewReceipt || !sourceCommitAck) return;
    setSourceCommitBusy(true);
    setSourceCommitError(null);
    try {
      const result = await commitSourceMerge({
        ...request,
        expected_source_revision_id: sourcePreviewReceipt.source_revision_id,
        expected_twin_revision_id: sourcePreviewReceipt.twin_revision_id,
        expected_before_source_hash: sourcePreviewReceipt.before_source_hash,
        expected_after_source_hash: sourcePreviewReceipt.after_source_hash,
        expected_before_twin_hash: sourcePreviewReceipt.before_twin_hash,
        expected_after_twin_hash: sourcePreviewReceipt.after_twin_hash,
        acknowledge_body_rewrite: true,
      });
      setSourceCommitReceipt(result);
      setSourceRestoreAck(false);
      setSourceRestoreReceipt(null);
      setSourceRestoreError(null);
      onSourceBodyChanged?.();
    } catch (error) {
      setSourceCommitError(error instanceof Error ? error.message : String(error));
    } finally {
      setSourceCommitBusy(false);
    }
  }

  async function restoreSourceMergeReceipt() {
    if (!sourceCommitReceipt || !sourceRestoreAck) return;
    setSourceRestoreBusy(true);
    setSourceRestoreError(null);
    try {
      const result = await restoreSourceMerge({
        document_id: sourceCommitReceipt.document_id,
        parent_reading_thread_id: readingThreadId,
        source_revision_id: sourceCommitReceipt.source_revision_id,
        twin_revision_id: sourceCommitReceipt.twin_revision_id,
        expected_after_source_hash: sourceCommitReceipt.after_source_hash,
        expected_before_source_hash: sourceCommitReceipt.before_source_hash,
        acknowledge_restore: true,
        operator_reviewer: "reader-companion",
      });
      setSourceRestoreReceipt(result);
      onSourceBodyChanged?.();
    } catch (error) {
      setSourceRestoreError(error instanceof Error ? error.message : String(error));
    } finally {
      setSourceRestoreBusy(false);
    }
  }

  async function applySourceMergeReceipt() {
    const request = buildSourceMergeApplyRequest();
    if (!request) return;
    setSourceApplyBusy(true);
    setSourceApplyError(null);
    try {
      const result = await applySourceMerge(request);
      setSourceApplyReceipt(result);
    } catch (error) {
      setSourceApplyError(error instanceof Error ? error.message : String(error));
    } finally {
      setSourceApplyBusy(false);
    }
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
      setCopiedSourceReviewPacket(false);
      setSourceApplyAck(false);
      setSourceApplyConflictAck(false);
      setSourcePreviewReceipt(null);
      setSourcePreviewError(null);
      setSourceCommitAck(false);
      setSourceCommitReceipt(null);
      setSourceCommitError(null);
      setSourceRestoreAck(false);
      setSourceRestoreReceipt(null);
      setSourceRestoreError(null);
      setSourceApplyReceipt(null);
      setSourceApplyError(null);
    } catch (error) {
      setDraftError(error instanceof Error ? error.message : String(error));
    } finally {
      setDraftBusy(false);
    }
  }

  return (
    <aside
      className="w-80 flex-shrink-0 border-l border-rule dark:border-charcoal-1 overflow-y-auto bg-ice-1 dark:bg-charcoal-2 hidden reader-lg:flex reader-lg:flex-col"
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
              <div className="mt-1 flex items-center justify-between gap-2 border-t border-rule pt-1 dark:border-charcoal-1">
                <p>Review only · book not changed</p>
                <button
                  type="button"
                  onClick={() => void copySourceMergeReviewPacket()}
                  className="shrink-0 text-ink underline dark:text-bright"
                  title="Copy a review-only packet for deciding whether to merge into the source book"
                >
                  {copiedSourceReviewPacket ? "copied review" : "copy review"}
                </button>
              </div>
              <label className="mt-1 flex items-start gap-1.5 border-t border-rule pt-1 dark:border-charcoal-1">
                <input
                  type="checkbox"
                  checked={sourceApplyAck}
                  onChange={(event) => setSourceApplyAck(event.target.checked)}
                  className="mt-0.5"
                />
                <span>Reviewed draft · create receipt only</span>
              </label>
              {draftMergeReceipt.hash_conflicts.length > 0 ? (
                <label className="mt-1 flex items-start gap-1.5">
                  <input
                    type="checkbox"
                    checked={sourceApplyConflictAck}
                    onChange={(event) => setSourceApplyConflictAck(event.target.checked)}
                    className="mt-0.5"
                  />
                  <span>Conflict reviewed</span>
                </label>
              ) : null}
              <div className="mt-1 flex items-center justify-between gap-2">
                <p>Ledger only · body not rewritten</p>
                <button
                  type="button"
                  onClick={() => void previewSourceMergeReceipt()}
                  disabled={
                    sourcePreviewBusy ||
                    !sourceApplyAck ||
                    (draftMergeReceipt.hash_conflicts.length > 0 && !sourceApplyConflictAck)
                  }
                  className="shrink-0 text-ink underline disabled:cursor-not-allowed disabled:text-ink-mute dark:text-bright dark:disabled:text-moonlight"
                  title="Preview revision evidence without rewriting the book body"
                >
                  {sourcePreviewBusy ? "previewing" : "preview"}
                </button>
                <button
                  type="button"
                  onClick={() => void applySourceMergeReceipt()}
                  disabled={
                    sourceApplyBusy ||
                    !sourceApplyAck ||
                    (draftMergeReceipt.hash_conflicts.length > 0 && !sourceApplyConflictAck)
                  }
                  className="shrink-0 text-ink underline disabled:cursor-not-allowed disabled:text-ink-mute dark:text-bright dark:disabled:text-moonlight"
                  title="Record the reviewed source/twin apply receipt without rewriting the book body"
                >
                  {sourceApplyBusy ? "applying" : "apply receipt"}
                </button>
              </div>
              {sourcePreviewReceipt ? (
                <div
                  className="mt-1 border-t border-rule pt-1 dark:border-charcoal-1"
                  aria-label="Source merge preview"
                  role="region"
                >
                  <p>Preview {sourcePreviewReceipt.status}</p>
                  <p>{sourcePreviewReceipt.source_bytes_before} → {sourcePreviewReceipt.source_bytes_after} bytes</p>
                  <p className="truncate" title={sourcePreviewReceipt.before_source_hash}>
                    before {sourcePreviewReceipt.before_source_hash}
                  </p>
                  <p className="truncate" title={sourcePreviewReceipt.after_source_hash}>
                    after {sourcePreviewReceipt.after_source_hash}
                  </p>
                  <p>writes performed {String(sourcePreviewReceipt.writes_performed)}</p>
                  <label className="mt-1 flex items-start gap-1.5 border-t border-rule pt-1 dark:border-charcoal-1">
                    <input
                      type="checkbox"
                      checked={sourceCommitAck}
                      onChange={(event) => setSourceCommitAck(event.target.checked)}
                      className="mt-0.5"
                    />
                    <span>Rewrite source from preview</span>
                  </label>
                  <div className="mt-1 flex items-center justify-between gap-2">
                    <p>Requires preview hash match</p>
                    <button
                      type="button"
                      onClick={() => void commitSourceMergeReceipt()}
                      disabled={sourceCommitBusy || !sourceCommitAck}
                      className="shrink-0 text-ink underline disabled:cursor-not-allowed disabled:text-ink-mute dark:text-bright dark:disabled:text-moonlight"
                      title="Commit the reviewed draft into the source body using the preview hashes"
                    >
                      {sourceCommitBusy ? "rewriting" : "rewrite source"}
                    </button>
                  </div>
                </div>
              ) : null}
              {sourcePreviewError ? (
                <p className="mt-1 text-emperor">{sourcePreviewError}</p>
              ) : null}
              {sourceCommitReceipt ? (
                <div
                  className="mt-1 border-t border-rule pt-1 dark:border-charcoal-1"
                  aria-label="Source merge commit"
                  role="region"
                >
                  <p>Commit {sourceCommitReceipt.status}</p>
                  <p>{sourceCommitReceipt.source_bytes_before} → {sourceCommitReceipt.source_bytes_after} bytes</p>
                  <p className="truncate" title={sourceCommitReceipt.event_id}>
                    {sourceCommitReceipt.event_id}
                  </p>
                  <p>writes performed {String(sourceCommitReceipt.writes_performed)}</p>
                  <label className="mt-1 flex items-start gap-1.5 border-t border-rule pt-1 dark:border-charcoal-1">
                    <input
                      type="checkbox"
                      checked={sourceRestoreAck}
                      onChange={(event) => setSourceRestoreAck(event.target.checked)}
                      className="mt-0.5"
                    />
                    <span>Restore previous source body</span>
                  </label>
                  <div className="mt-1 flex items-center justify-between gap-2">
                    <p>Requires current hash match</p>
                    <button
                      type="button"
                      onClick={() => void restoreSourceMergeReceipt()}
                      disabled={sourceRestoreBusy || !sourceRestoreAck}
                      className="shrink-0 text-ink underline disabled:cursor-not-allowed disabled:text-ink-mute dark:text-bright dark:disabled:text-moonlight"
                      title="Restore the previous source body from the commit snapshot"
                    >
                      {sourceRestoreBusy ? "restoring" : "restore"}
                    </button>
                  </div>
                </div>
              ) : null}
              {sourceCommitError ? (
                <p className="mt-1 text-emperor">{sourceCommitError}</p>
              ) : null}
              {sourceRestoreReceipt ? (
                <div
                  className="mt-1 border-t border-rule pt-1 dark:border-charcoal-1"
                  aria-label="Source merge restore"
                  role="region"
                >
                  <p>Restore {sourceRestoreReceipt.status}</p>
                  <p className="truncate" title={sourceRestoreReceipt.event_id}>
                    {sourceRestoreReceipt.event_id}
                  </p>
                  <p>writes performed {String(sourceRestoreReceipt.writes_performed)}</p>
                </div>
              ) : null}
              {sourceRestoreError ? (
                <p className="mt-1 text-emperor">{sourceRestoreError}</p>
              ) : null}
              {sourceApplyReceipt ? (
                <div
                  className="mt-1 border-t border-rule pt-1 dark:border-charcoal-1"
                  aria-label="Source merge receipt"
                  role="region"
                >
                  <p>Receipt {sourceApplyReceipt.status}</p>
                  <p className="truncate" title={sourceApplyReceipt.source_revision_id}>
                    {sourceApplyReceipt.source_revision_id}
                  </p>
                  <p className="truncate" title={sourceApplyReceipt.twin_revision_id}>
                    {sourceApplyReceipt.twin_revision_id}
                  </p>
                  <p>Book body not rewritten</p>
                </div>
              ) : null}
              {sourceApplyError ? (
                <p className="mt-1 text-emperor">{sourceApplyError}</p>
              ) : null}
              {draftMergeReceipt.hash_conflicts.length > 0 ? (
                <p className="text-emperor">
                  {draftMergeReceipt.hash_conflicts.length} hash conflict
                  {draftMergeReceipt.hash_conflicts.length === 1 ? "" : "s"} need review
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

      <CompanionSection key={documentId} documentId={documentId} />

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

function buildSourceMergeReviewPacket({
  documentId,
  title,
  readingThreadId,
  draftMergeReceipt,
  draftMergeIds,
}: {
  documentId: string;
  title?: string | null;
  readingThreadId: string;
  draftMergeReceipt: ResearchArtifactComposeResponse;
  draftMergeIds: string[];
}): SourceMergeReviewPacket {
  return {
    kind: "antiek.reader.source_merge_review_packet",
    document_id: documentId,
    title: title ?? null,
    parent_reading_thread_id: readingThreadId,
    draft_merge_path: draftMergeReceipt.draft_merge_path ?? draftMergeReceipt.path,
    compose_index_path: draftMergeReceipt.path,
    member_investigation_ids: draftMergeReceipt.members.map((member) => member.investigation_id),
    requested_investigation_ids: draftMergeIds,
    hash_conflict_count: draftMergeReceipt.hash_conflicts.length,
    hash_conflicts: draftMergeReceipt.hash_conflicts,
    source_book_mutated: false,
    twin_document_mutated: false,
    no_spend: true,
  };
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

type CompanionView =
  | { phase: "idle" }
  | { phase: "loading" }
  | { phase: "building" }
  | { phase: "unavailable" }
  | { phase: "load_failed" }
  | { phase: "build_failed" }
  | { phase: "refresh_failed" }
  | {
      phase: "built";
      payload: BuiltCompanion;
      refreshing: boolean;
      /** A refresh that failed while this companion stayed in hand. */
      notice: "rebuild_failed" | null;
    };

const COMPANION_COPY = {
  loading: "Loading the companion…",
  building: "Building the companion…",
  rebuilding: "Rebuilding the companion…",
  unavailable: "The companion isn't available for this document.",
  loadFailed: "Couldn't load the companion.",
  buildFailed: "Couldn't build the companion yet.",
  rebuildFailed: "Couldn't rebuild the companion. The last version is shown.",
  refreshFailed: "Couldn't refresh the companion.",
  ready: "Companion ready.",
} as const;

function companionLine(view: CompanionView): string | null {
  switch (view.phase) {
    case "idle":
      return null;
    case "loading":
      return COMPANION_COPY.loading;
    case "building":
      return COMPANION_COPY.building;
    case "unavailable":
      return COMPANION_COPY.unavailable;
    case "load_failed":
      return COMPANION_COPY.loadFailed;
    case "build_failed":
      return COMPANION_COPY.buildFailed;
    case "refresh_failed":
      return COMPANION_COPY.refreshFailed;
    case "built":
      if (view.refreshing) return COMPANION_COPY.rebuilding;
      if (view.notice === "rebuild_failed") return COMPANION_COPY.rebuildFailed;
      return COMPANION_COPY.ready;
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
 *
 * LAZY: a collapsed disclosure that requests nothing until first opened —
 * every reader open used to trigger a rebuild under the single writer lock.
 * First open reads the last build; `not_built` asks for one rebuild; Refresh
 * is the only other write. The loaded state survives collapse and re-open;
 * the parent keys this section by documentId, so a new document starts idle.
 * Failure copy is chosen from the state alone — no status number, server code
 * or error type ever renders.
 */
function CompanionSection({ documentId }: { documentId: string }) {
  const regionId = useId();
  const statusId = `${regionId}-status`;
  const [open, setOpen] = useState(false);
  const [view, setView] = useState<CompanionView>({ phase: "idle" });
  const [inspectRows, setInspectRows] = useState<EvidenceRowItem[] | null>(null);
  // One request at a time, even across a double click inside one frame.
  const inFlight = useRef(false);
  const mounted = useRef(true);
  const actionRef = useRef<HTMLButtonElement>(null);
  const statusRef = useRef<HTMLParagraphElement>(null);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  function focusStatusFromAction() {
    if (actionRef.current && document.activeElement === actionRef.current) {
      statusRef.current?.focus();
    }
  }

  function showUnavailable() {
    focusStatusFromAction();
    setView({ phase: "unavailable" });
  }

  async function exclusive(task: () => Promise<void>) {
    if (inFlight.current || !mounted.current) return;
    inFlight.current = true;
    try {
      await task();
    } finally {
      inFlight.current = false;
    }
  }

  function showBuilt(payload: BuiltCompanion, notice: "rebuild_failed" | null = null) {
    setView({ phase: "built", payload, refreshing: false, notice });
  }

  async function load() {
    setView({ phase: "loading" });
    let answer: CompanionResponse;
    try {
      answer = await getDocumentCompanion(documentId);
    } catch (err) {
      if (!mounted.current) return;
      if (isCompanionNotFound(err)) showUnavailable();
      else setView({ phase: "load_failed" });
      return;
    }
    if (!mounted.current) return;
    if (answer.state === "built") showBuilt(answer);
    else if (answer.state === "withheld") showUnavailable();
    else await rebuild(null); // not_built: ask for exactly one build
  }

  async function rebuild(inHand: BuiltCompanion | null) {
    setView(
      inHand
        ? { phase: "built", payload: inHand, refreshing: true, notice: null }
        : { phase: "building" },
    );
    try {
      const answer = await refreshDocumentCompanion(documentId);
      if (!mounted.current) return;
      if (answer.state === "built") showBuilt(answer);
      else if (answer.state === "withheld") showUnavailable();
      else await rebuildFailed(inHand, false);
    } catch (err) {
      if (!mounted.current) return;
      if (isCompanionNotFound(err)) {
        showUnavailable();
        return;
      }
      const hasLastBuild =
        err instanceof CompanionRebuildFailedError ? err.hasLastBuild : null;
      await rebuildFailed(inHand, hasLastBuild);
    }
  }

  async function rebuildFailed(inHand: BuiltCompanion | null, hasLastBuild: boolean | null) {
    focusStatusFromAction();
    if (inHand) {
      setView({
        phase: "built",
        payload: inHand,
        refreshing: false,
        notice: "rebuild_failed",
      });
      return;
    }
    if (hasLastBuild !== true) {
      setView({ phase: hasLastBuild === false ? "build_failed" : "refresh_failed" });
      return;
    }
    // The server kept a last build this rail never received. Read it (the GET
    // never writes) so "the last version is shown" is true.
    try {
      const answer = await getDocumentCompanion(documentId);
      if (!mounted.current) return;
      if (answer.state === "built") showBuilt(answer, "rebuild_failed");
      else if (answer.state === "withheld") showUnavailable();
      else setView({ phase: "build_failed" });
    } catch (err) {
      if (!mounted.current) return;
      if (isCompanionNotFound(err)) showUnavailable();
      else setView({ phase: "load_failed" });
    }
  }

  function toggle() {
    const next = !open;
    setOpen(next);
    if (next && view.phase === "idle") void exclusive(load);
  }

  function retry() {
    if (inFlight.current) return;
    focusStatusFromAction();
    if (view.phase === "load_failed") void exclusive(load);
    else if (view.phase === "build_failed" || view.phase === "refresh_failed") {
      void exclusive(() => rebuild(null));
    }
    else if (view.phase === "built") void exclusive(() => rebuild(view.payload));
  }

  const line = companionLine(view);
  const canRetry =
    view.phase === "load_failed" ||
    view.phase === "build_failed" ||
    view.phase === "refresh_failed" ||
    (view.phase === "built" && !view.refreshing && view.notice !== null);
  const payload = view.phase === "built" ? view.payload : null;
  const refreshing = view.phase === "built" && view.refreshing;

  return (
    <section
      className="border-b border-rule px-4 py-3 dark:border-charcoal-1"
      aria-label="Document companion"
      data-companion-section
    >
      <button
        type="button"
        onClick={toggle}
        aria-expanded={open}
        aria-controls={regionId}
        className="flex w-full items-center justify-between gap-2 text-left font-mono text-xxs uppercase tracking-wide text-shadow-1 hover:text-ink dark:text-moonlight dark:hover:text-bright"
      >
        The companion so far
        <span aria-hidden="true">{open ? "−" : "+"}</span>
      </button>
      <div id={regionId} hidden={!open} className="mt-2">
        <div className={`flex items-baseline justify-between gap-2 ${line ? "mb-1.5" : ""}`}>
          <p
            id={statusId}
            ref={statusRef}
            tabIndex={-1}
            role="status"
            aria-live="polite"
            className="font-serif text-xs italic text-ink-mute focus-visible:outline focus-visible:outline-2 focus-visible:outline-sun dark:text-moonlight"
          >
            {line}
          </p>
          {canRetry && (
            <button
              type="button"
              ref={actionRef}
              onClick={retry}
              className="shrink-0 font-mono text-xxs text-shadow-1 underline decoration-dotted underline-offset-2 hover:text-ink dark:text-moonlight dark:hover:text-bright"
            >
              Retry
            </button>
          )}
        </div>
        {payload && (
          <>
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
                {payload.claims.slice(0, 5).map((claim) => {
                  const label = claimKindLabel(claim.kind);
                  return (
                    <li
                      key={claim.evidence_id}
                      data-evidence-id={claim.evidence_id}
                      className="font-serif text-xs leading-relaxed text-ink dark:text-bright"
                    >
                      {label && (
                        <span className="mr-1 font-mono text-xxs uppercase tracking-wide text-shadow-1 dark:text-moonlight">
                          {label} ·
                        </span>
                      )}
                      {claim.text ?? <span className="italic">grounded in a withheld source</span>}
                    </li>
                  );
                })}
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
              <div className="flex shrink-0 items-center gap-2">
                {!canRetry && (
                  <button
                    type="button"
                    ref={actionRef}
                    onClick={() => void exclusive(() => rebuild(payload))}
                    aria-disabled={refreshing}
                    aria-describedby={refreshing ? statusId : undefined}
                    className="font-mono text-xxs text-shadow-1 underline decoration-dotted underline-offset-2 hover:text-ink aria-disabled:cursor-not-allowed aria-disabled:text-ink-mute dark:text-moonlight dark:hover:text-bright dark:aria-disabled:text-moonlight"
                    title={refreshing ? "A rebuild is already running" : "Rebuild the companion from this book's latest notes and evidence"}
                  >
                    Refresh
                  </button>
                )}
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
          </>
        )}
      </div>
    </section>
  );
}

/**
 * The claim row's label, by the payload's real kind. The server sends the
 * grounded node's type (insight | question); claim and evidence are labelled
 * if they ever arrive; an unknown kind gets no label rather than a wrong one.
 */
function claimKindLabel(kind: string): string | null {
  switch (kind) {
    case "insight":
      return "Finding";
    case "question":
      return "Open question";
    case "claim":
      return "Claim";
    case "evidence":
      return "Evidence";
    default:
      return null;
  }
}
