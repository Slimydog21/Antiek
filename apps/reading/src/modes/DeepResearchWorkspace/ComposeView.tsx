/**
 * ComposeView.tsx — the v1 context composition: the extended composed
 * evidence view (thread-merge + document fork SPR-03).
 *
 * Two or more research threads' OUTCOMES — insights and open questions, the
 * existing distill reads — rendered side by side with per-item selection,
 * the compose pair model's cross-thread duplicates shown honestly where
 * members agree word-for-word, and "merge selected into a fork…" flowing
 * into SPR-02's receipted preview → conflict picker → commit.
 *
 * The honest boundary is DISPLAYED, not implied (BOUNDARY_COPY, rendered
 * wherever selection is offered): this view composes outcomes for REVIEW
 * and selective document merge. It does NOT merge the researches
 * themselves — graphs, trajectories and lineages stay distinct — and no
 * control here claims otherwise (the copy contract is grepped by the
 * suite). Automatic composition stays unit-7's (the diligence pipeline's
 * gate-safe spawn contexts) — cross-referenced, untouched.
 *
 * The view writes NOTHING itself: selection state is client-local
 * (useState, gone on close); every mutation goes through SPR-02's routes.
 * Fetch discipline: distill reads + the SPR-01 forks read + the SPR-02
 * preview/commit — no new read endpoints (asserted by the network mock
 * surface in the suite).
 */
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import LemonButton from "../../components/lemon/LemonButton";
import { getDistillation, type DistilledNode } from "../../lib/api";
import { listForks, type DocumentFork } from "../../api/forks";
import {
  commitForkMerge,
  previewForkMerge,
  type ForkMergePreview,
} from "../../api/forkMerge";
import ConflictPicker, { refKey, type PickerChoice } from "./ConflictPicker";

/** The honest boundary — rendered wherever selection is offered. The copy
 *  contract: this string is DOM-asserted by the suite, and no control in
 *  this view may claim to merge the researches themselves. */
export const COMPOSE_BOUNDARY_COPY =
  "Reviewing outcomes side by side — this does not merge these researches. Their graphs, histories and lineage stay separate; only items you select can merge into a fork, and only with your review.";

/** The unit-7 cross-reference (automatic composition, untouched). */
export const COMPOSE_AUTOMATIC_NOTE =
  "Automatic composition for agent work stays with the diligence pipeline — this view is for your review.";

export interface ComposeViewProps {
  /** The threads being composed (2+). */
  investigationIds: string[];
  /** The fork context when the view was opened from a fork's surface —
   *  merge targets it directly. Absent (the monitor path): the operator
   *  picks a fork of the selected items' source documents. */
  fork?: { forkId: string; documentId: string; title: string | null } | null;
  /** Human thread labels where the caller knows them (the monitor's
   *  sub-questions); threads render by position otherwise. */
  threadTitles?: Record<string, string>;
  onClose: () => void;
  /** A merge committed — the host reloads what it's showing. */
  onMerged?: () => void;
}

interface ThreadItems {
  investigationId: string;
  insights: DistilledNode[];
  questions: DistilledNode[];
  error: string | null;
}

interface MergeItemRef {
  investigation_id: string;
  node_id: string;
}

type MergePhase =
  | { phase: "choose_fork"; candidates: DocumentFork[]; loading: boolean }
  | { phase: "previewing" }
  | { phase: "review"; preview: ForkMergePreview; fork: DocumentFork | { fork_id: string; fork_document_id: string } }
  | { phase: "committing" }
  | { phase: "merged"; commitMergeId: string; forkDocumentId: string; afterHash: string }
  | { phase: "merge_failed"; message: string };

function normalizeClaim(text: string): string {
  return text.replace(/\s+/g, " ").trim();
}

/** The compose pair model (compose.py) at item granularity: one claim text
 *  reached by two threads. Detection only — never a merge, never a hidden
 *  dedupe. */
function crossThreadPairs(threads: ThreadItems[]): Set<string> {
  const claimants = new Map<string, Set<string>>();
  for (const thread of threads) {
    for (const node of [...thread.insights, ...thread.questions]) {
      const key = normalizeClaim(node.text);
      if (!key) continue;
      const set = claimants.get(key) ?? new Set<string>();
      set.add(thread.investigationId);
      claimants.set(key, set);
    }
  }
  const shared = new Set<string>();
  for (const [claimText, ids] of claimants) {
    if (ids.size > 1) shared.add(claimText);
  }
  return shared;
}

function threadLabel(titles: Record<string, string> | undefined, iid: string, index: number): string {
  const known = titles?.[iid]?.trim();
  return known || `research ${index + 1}`;
}

export default function ComposeView({
  investigationIds,
  fork = null,
  threadTitles,
  onClose,
  onMerged,
}: ComposeViewProps) {
  const ids = useMemo(
    () => [...new Set(investigationIds.filter(Boolean))],
    [investigationIds],
  );
  const [threads, setThreads] = useState<ThreadItems[] | null>(null);
  const [selected, setSelected] = useState<ReadonlySet<string>>(new Set());
  const [merge, setMerge] = useState<MergePhase | null>(null);
  const [choices, setChoices] = useState<Record<string, PickerChoice>>({});

  useEffect(() => {
    let cancelled = false;
    setThreads(null);
    setSelected(new Set());
    setMerge(null);
    setChoices({});
    void Promise.all(
      ids.map(async (investigationId): Promise<ThreadItems> => {
        try {
          const d = await getDistillation(investigationId);
          return {
            investigationId,
            insights: d.insights,
            questions: d.questions,
            error: null,
          };
        } catch (e) {
          return {
            investigationId,
            insights: [],
            questions: [],
            error: e instanceof Error ? e.message : String(e),
          };
        }
      }),
    ).then((loaded) => {
      if (!cancelled) setThreads(loaded);
    });
    return () => {
      cancelled = true;
    };
  }, [ids]);

  const pairs = useMemo(() => crossThreadPairs(threads ?? []), [threads]);

  function toggle(ref: MergeItemRef) {
    const key = refKey(ref);
    setSelected((s) => {
      const next = new Set(s);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  function selectedRefs(): MergeItemRef[] {
    const out: MergeItemRef[] = [];
    for (const thread of threads ?? []) {
      for (const node of [...thread.insights, ...thread.questions]) {
        const ref = { investigation_id: thread.investigationId, node_id: node.node_id };
        if (selected.has(refKey(ref))) out.push(ref);
      }
    }
    return out;
  }

  async function beginMerge() {
    const refs = selectedRefs();
    if (refs.length === 0) return;
    if (fork) {
      await previewInto({ fork_id: fork.forkId, fork_document_id: fork.documentId }, refs);
      return;
    }
    // The monitor path: forks of the selected items' source documents are
    // the lawful targets (SPR-01's read; no new endpoint).
    setMerge({ phase: "choose_fork", candidates: [], loading: true });
    const sourceIds = new Set<string>();
    for (const thread of threads ?? []) {
      for (const node of [...thread.insights, ...thread.questions]) {
        const ref = { investigation_id: thread.investigationId, node_id: node.node_id };
        if (selected.has(refKey(ref)) && node.source_document_id) {
          sourceIds.add(node.source_document_id);
        }
      }
    }
    const candidates: DocumentFork[] = [];
    const seen = new Set<string>();
    try {
      for (const docId of sourceIds) {
        const resp = await listForks(docId);
        for (const row of resp.forks) {
          if (!seen.has(row.fork_id)) {
            seen.add(row.fork_id);
            candidates.push(row);
          }
        }
      }
      setMerge({ phase: "choose_fork", candidates, loading: false });
    } catch {
      setMerge({ phase: "choose_fork", candidates: [], loading: false });
    }
  }

  async function previewInto(
    target: { fork_id: string; fork_document_id: string },
    refs: MergeItemRef[],
  ) {
    setMerge({ phase: "previewing" });
    setChoices({});
    try {
      const preview = await previewForkMerge({
        fork_id: target.fork_id,
        items: refs,
      });
      setMerge({ phase: "review", preview, fork: target });
    } catch (e) {
      setMerge({
        phase: "merge_failed",
        message: e instanceof Error ? e.message : String(e),
      });
    }
  }

  async function commit(preview: ForkMergePreview) {
    // Resolutions key on the PREVIEW's own conflict refs (never a re-parse
    // of the session's key encoding).
    const conflictedRefs = [
      ...new Map(
        preview.conflicts.flatMap((c) => c.item_refs).map((r) => [refKey(r), r]),
      ).values(),
    ];
    const resolutions = conflictedRefs.map((ref) => ({
      investigation_id: ref.investigation_id,
      node_id: ref.node_id,
      choice: choices[refKey(ref)],
    }));
    setMerge({ phase: "committing" });
    try {
      const receipt = await commitForkMerge({
        fork_id: preview.fork_id,
        items: preview.items.map((i) => ({
          investigation_id: i.investigation_id,
          node_id: i.node_id,
        })),
        expected_merge_id: preview.merge_id,
        expected_before_fork_hash: preview.before_fork_hash,
        resolutions,
        acknowledge_fork_document_mutation: true,
        acknowledge_conflicts: preview.conflicts.length > 0,
      });
      setMerge({
        phase: "merged",
        commitMergeId: receipt.merge_id,
        forkDocumentId: receipt.fork_document_id,
        afterHash: receipt.after_fork_hash,
      });
      onMerged?.();
    } catch (e) {
      setMerge({
        phase: "merge_failed",
        message: e instanceof Error ? e.message : String(e),
      });
    }
  }

  const unresolvedCount =
    merge?.phase === "review"
      ? new Set(merge.preview.conflicts.flatMap((c) => c.item_refs.map(refKey))).size -
        Object.keys(choices).length
      : 0;

  return (
    <section
      aria-label="Composed evidence review"
      data-compose-view
      className="flex h-full min-h-0 flex-col gap-3 overflow-y-auto"
    >
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-sm font-semibold text-ink dark:text-bright">
          Reviewing {ids.length} researches side by side
        </h2>
        <LemonButton variant="tertiary" size="sm" onClick={onClose}>
          close
        </LemonButton>
      </div>

      {/* The honest boundary, wherever selection is offered. */}
      <p
        data-compose-boundary
        className="rounded-hog border border-rule bg-ice-1 px-3 py-2 font-serif text-xs italic text-ink-soft dark:border-charcoal-1 dark:bg-charcoal-2 dark:text-starlight"
      >
        {COMPOSE_BOUNDARY_COPY}
      </p>
      <p className="font-mono text-xxs text-shadow-1 dark:text-moonlight">
        {COMPOSE_AUTOMATIC_NOTE}
      </p>

      {threads === null ? (
        <p role="status" className="font-serif text-sm text-ink-mute dark:text-moonlight">
          Gathering the threads' outcomes…
        </p>
      ) : (
        <div
          className="grid grid-cols-1 gap-3 md:grid-cols-2"
          data-compose-threads
        >
          {threads.map((thread, index) => (
            <article
              key={thread.investigationId}
              data-compose-thread={thread.investigationId}
              className="flex flex-col gap-2 rounded-hog border border-rule bg-ice-0 p-3 dark:border-charcoal-1 dark:bg-charcoal-2"
              aria-label={`outcomes of ${threadLabel(threadTitles, thread.investigationId, index)}`}
            >
              <header className="border-b border-hairline pb-1">
                <p className="font-mono text-xs text-shadow-1 dark:text-moonlight">
                  {threadLabel(threadTitles, thread.investigationId, index)}
                </p>
              </header>
              {thread.error !== null ? (
                <p className="font-serif text-xs italic text-ink-mute dark:text-moonlight">
                  This thread's outcomes couldn't be read — it stays unselected.
                </p>
              ) : thread.insights.length === 0 && thread.questions.length === 0 ? (
                <p className="font-serif text-xs italic text-ink-mute dark:text-moonlight">
                  No outcomes on record for this thread yet.
                </p>
              ) : (
                <>
                  {thread.insights.length > 0 && (
                    <OutcomeGroup
                      label="Insights"
                      thread={thread}
                      nodes={thread.insights}
                      selected={selected}
                      sharedClaims={pairs}
                      onToggle={toggle}
                    />
                  )}
                  {thread.questions.length > 0 && (
                    <OutcomeGroup
                      label="Open questions"
                      thread={thread}
                      nodes={thread.questions}
                      selected={selected}
                      sharedClaims={pairs}
                      onToggle={toggle}
                    />
                  )}
                </>
              )}
            </article>
          ))}
        </div>
      )}

      {/* The merge lane — selection is client-local until the operator
          previews; every write rides SPR-02's receipted path. */}
      <div
        className="mt-1 flex flex-col gap-2 border-t border-hairline pt-3"
        data-compose-merge-lane
      >
        <p
          data-compose-boundary
          className="font-serif text-xs italic text-ink-soft dark:text-starlight"
        >
          {COMPOSE_BOUNDARY_COPY}
        </p>
        {merge === null && (
          <div className="flex items-center gap-3">
            <LemonButton
              size="sm"
              variant="secondary"
              disabled={selected.size === 0}
              onClick={() => void beginMerge()}
              title={
                selected.size === 0
                  ? "Select outcomes above first"
                  : "Preview the merge into a fork — nothing writes until you review and commit"
              }
            >
              Merge selected into {fork ? "this fork" : "a fork"}… ({selected.size})
            </LemonButton>
            <span className="font-mono text-xxs text-shadow-1 dark:text-moonlight">
              preview first · conflicts never resolve themselves
            </span>
          </div>
        )}

        {merge?.phase === "choose_fork" && (
          <div data-fork-picker className="flex flex-col gap-1.5">
            <p className="font-mono text-xs text-shadow-1 dark:text-moonlight">
              {merge.loading
                ? "Finding forks of these threads' sources…"
                : merge.candidates.length === 0
                  ? "No forks of these threads' source documents yet — fork a book from its reader first."
                  : "Choose the fork to merge into:"}
            </p>
            {merge.candidates.map((candidate) => (
              <button
                key={candidate.fork_id}
                type="button"
                onClick={() =>
                  void previewInto(
                    {
                      fork_id: candidate.fork_id,
                      fork_document_id: candidate.fork_document_id,
                    },
                    selectedRefs(),
                  )
                }
                className="w-fit rounded border border-rule px-2 py-1 text-left font-serif text-sm text-ink hover:bg-ice-2 dark:border-charcoal-1 dark:text-bright dark:hover:bg-charcoal-1"
              >
                Fork of {candidate.parent_title?.trim() || "its source"} ·{" "}
                {candidate.created_at.slice(0, 10)}
                {candidate.note ? ` — ${candidate.note}` : ""}
              </button>
            ))}
            <LemonButton variant="tertiary" size="sm" onClick={() => setMerge(null)}>
              cancel
            </LemonButton>
          </div>
        )}

        {(merge?.phase === "previewing" || merge?.phase === "committing") && (
          <p role="status" className="font-serif text-sm text-ink-mute dark:text-moonlight">
            {merge.phase === "previewing"
              ? "Previewing the merge — nothing is written…"
              : "Committing the reviewed merge…"}
          </p>
        )}

        {merge?.phase === "review" && (
          <div className="flex flex-col gap-2" data-merge-review>
            <p className="font-serif text-sm text-ink dark:text-bright">
              The preview: {merge.preview.items.length} item
              {merge.preview.items.length === 1 ? "" : "s"} would land in your fork
              {merge.preview.conflicts.length > 0
                ? ` — ${merge.preview.conflicts.length} conflict${
                    merge.preview.conflicts.length === 1 ? "" : "s"
                  } wait for your call`
                : " — no conflicts"}
              .
            </p>
            {merge.preview.conflicts.length > 0 && (
              <ConflictPicker
                conflicts={merge.preview.conflicts}
                items={merge.preview.items}
                choices={choices}
                onChoose={(ref, choice) =>
                  setChoices((c) => ({ ...c, [refKey(ref)]: choice }))
                }
              />
            )}
            <div className="flex items-center gap-3">
              <LemonButton
                size="sm"
                variant="primary"
                disabled={unresolvedCount > 0}
                onClick={() => void commit(merge.preview)}
                title={
                  unresolvedCount > 0
                    ? `${unresolvedCount} conflicted item${unresolvedCount === 1 ? "" : "s"} still wait for your choice`
                    : "Writes the selected outcomes into your fork's body — the original book is never touched"
                }
              >
                Commit the merge into the fork
              </LemonButton>
              <LemonButton variant="tertiary" size="sm" onClick={() => setMerge(null)}>
                back
              </LemonButton>
            </div>
            <p className="font-mono text-xxs text-shadow-1 dark:text-moonlight">
              This writes into your fork's body. The original book is never
              touched.
            </p>
          </div>
        )}

        {merge?.phase === "merged" && (
          <div
            role="status"
            data-merge-done
            className="flex flex-col gap-1 rounded-hog border border-rule bg-ice-1 px-3 py-2 dark:border-charcoal-1 dark:bg-charcoal-2"
          >
            <p className="font-serif text-sm text-ink dark:text-bright">
              Merged — your fork carries the selected outcomes, each naming
              its source research. The original is untouched.
            </p>
            <Link
              to={`/read/${encodeURIComponent(merge.forkDocumentId)}`}
              className="w-fit font-mono text-xs text-ink underline dark:text-bright"
            >
              open the fork
            </Link>
          </div>
        )}

        {merge?.phase === "merge_failed" && (
          <div role="status" className="flex flex-col gap-1">
            <p className="font-serif text-sm text-emperor">
              The merge didn't go through — nothing was written.
            </p>
            <LemonButton variant="tertiary" size="sm" onClick={() => setMerge(null)}>
              back
            </LemonButton>
          </div>
        )}
      </div>
    </section>
  );
}

function OutcomeGroup({
  label,
  thread,
  nodes,
  selected,
  sharedClaims,
  onToggle,
}: {
  label: string;
  thread: ThreadItems;
  nodes: DistilledNode[];
  selected: ReadonlySet<string>;
  sharedClaims: ReadonlySet<string>;
  onToggle: (ref: MergeItemRef) => void;
}) {
  return (
    <section aria-label={label}>
      <p className="mb-1 font-mono text-xxs uppercase tracking-wide text-shadow-1 dark:text-moonlight">
        {label}
      </p>
      <ul className="space-y-1.5">
        {nodes.map((node) => {
          const ref = { investigation_id: thread.investigationId, node_id: node.node_id };
          const key = refKey(ref);
          const shared = sharedClaims.has(normalizeClaim(node.text));
          return (
            <li key={node.node_id} data-node-id={node.node_id}>
              <label className="flex cursor-pointer items-start gap-2 rounded border border-transparent px-1 py-0.5 hover:border-rule dark:hover:border-charcoal-1">
                <input
                  type="checkbox"
                  checked={selected.has(key)}
                  onChange={() => onToggle(ref)}
                  className="mt-1 accent-sun-deep"
                />
                <span className="min-w-0 flex-1 font-serif text-sm leading-snug text-ink dark:text-bright">
                  {node.kind === "question" ? (
                    <span className="italic">Open question: </span>
                  ) : null}
                  {node.text}
                  {shared && (
                    <span
                      data-pair-conflict
                      className="ml-1 inline-flex rounded-hog border border-sun px-1.5 py-0.5 font-mono text-xxs text-sun-deep dark:text-sun"
                      title="Another research you're reviewing reached this same claim — the merge preview lists it as a conflict for your call; it is never merged twice silently"
                    >
                      reached by both researches — review
                    </span>
                  )}
                </span>
              </label>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
