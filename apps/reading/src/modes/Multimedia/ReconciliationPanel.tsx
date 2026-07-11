import { useRef, useState } from "react";

import {
  executeChapterTtsReconciliation,
  getChapterTtsReconciliation,
  getNarrationRunReconciliation,
} from "../../api/multimedia";
import type {
  ChapterTtsReconciliation,
  NarrationRunReconciliation,
  TtsReconciliationAction,
} from "../../api/multimedia";
import { LemonButton, LemonInput, LemonTag } from "../../components/lemon";

const ACTION_LABELS: Record<TtsReconciliationAction, string> = {
  quarantine_send: "Quarantine stale send",
  recover_unknown: "Recover provider audio",
  release_seal: "Release stale seal",
};

function eligibleAction(
  view: ChapterTtsReconciliation | null,
  visibleExecutionId: string,
): TtsReconciliationAction | null {
  if (!view?.action_eligible || view.execution_id !== visibleExecutionId.trim()) return null;
  return view.next_action in ACTION_LABELS ? (view.next_action as TtsReconciliationAction) : null;
}

function errorMessage(error: unknown): string {
  const value = error instanceof Error ? error.message : "";
  if (value === "multimedia_reconciliation_runtime_unavailable") return "Recovery runtime unavailable";
  if (value === "multimedia_reconciliation_action_conflict") return "Recovery state changed";
  if (value.includes("unavailable")) return "Recovery record unavailable";
  return "Recovery request failed";
}

export function ReconciliationPanel() {
  const [executionId, setExecutionId] = useState("");
  const [runId, setRunId] = useState("");
  const [chapter, setChapter] = useState<ChapterTtsReconciliation | null>(null);
  const [run, setRun] = useState<NarrationRunReconciliation | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const requestGeneration = useRef(0);
  const action = eligibleAction(chapter, executionId);

  async function inspectExecution() {
    if (!executionId.trim()) return;
    const generation = ++requestGeneration.current;
    const requestedId = executionId.trim();
    setPending(true);
    try {
      const result = await getChapterTtsReconciliation(requestedId);
      if (requestGeneration.current !== generation) return;
      setChapter(result);
      setError(null);
    } catch (caught) {
      if (requestGeneration.current !== generation) return;
      setChapter(null);
      setError(errorMessage(caught));
    } finally {
      if (requestGeneration.current === generation) setPending(false);
    }
  }

  async function executeAction() {
    if (!action || !chapter) return;
    const generation = ++requestGeneration.current;
    setPending(true);
    try {
      const result = await executeChapterTtsReconciliation(chapter.execution_id, action);
      if (requestGeneration.current !== generation) return;
      setChapter(result);
      setError(null);
    } catch (caught) {
      if (requestGeneration.current !== generation) return;
      setError(errorMessage(caught));
    } finally {
      if (requestGeneration.current === generation) setPending(false);
    }
  }

  async function inspectRun() {
    if (!runId.trim()) return;
    const generation = ++requestGeneration.current;
    const requestedId = runId.trim();
    setPending(true);
    try {
      const result = await getNarrationRunReconciliation(requestedId);
      if (requestGeneration.current !== generation) return;
      setRun(result);
      setError(null);
    } catch (caught) {
      if (requestGeneration.current !== generation) return;
      setRun(null);
      setError(errorMessage(caught));
    } finally {
      if (requestGeneration.current === generation) setPending(false);
    }
  }

  return (
    <section
      className="rounded-md border border-rule bg-ice-1 p-3 dark:border-charcoal-1 dark:bg-charcoal-2"
      data-testid="multimedia-reconciliation"
    >
      <div className="flex items-center justify-between gap-2">
        <p className="font-mono text-[12px] text-shadow-2 dark:text-moonlight">Recovery</p>
        {chapter && <LemonTag colour={chapter.action_eligible ? "danger" : "muted"}>{chapter.attempt_status}</LemonTag>}
      </div>

      <label className="mt-3 block font-mono text-[11px] text-shadow-2 dark:text-moonlight" htmlFor="multimedia-execution-id">
        Execution ID
      </label>
      <div className="mt-1 flex gap-2">
        <LemonInput
          id="multimedia-execution-id"
          value={executionId}
          onChange={(event) => {
            requestGeneration.current += 1;
            setExecutionId(event.target.value);
            setChapter(null);
            setError(null);
            setPending(false);
          }}
          wrapperClassName="min-w-0 flex-1"
        />
        <LemonButton type="button" size="sm" variant="secondary" disabled={pending || !executionId.trim()} onClick={inspectExecution}>
          Inspect
        </LemonButton>
      </div>

      {chapter && (
        <dl className="mt-3 grid grid-cols-[1fr_auto] gap-x-3 gap-y-1 text-[12px]" data-testid="chapter-reconciliation-status">
          <dt className="text-shadow-1 dark:text-moonlight">Provider</dt>
          <dd className="text-right text-ink dark:text-bright">{chapter.provider_status}</dd>
          <dt className="text-shadow-1 dark:text-moonlight">Charged</dt>
          <dd className="text-right text-ink dark:text-bright">${(chapter.charged_cents / 100).toFixed(2)}</dd>
          <dt className="text-shadow-1 dark:text-moonlight">Next</dt>
          <dd className="text-right text-ink dark:text-bright">{chapter.next_action.replaceAll("_", " ")}</dd>
          {(chapter.send_age_seconds !== null || chapter.seal_age_seconds !== null) && (
            <>
              <dt className="text-shadow-1 dark:text-moonlight">Age</dt>
              <dd className="text-right text-ink dark:text-bright">
                {chapter.seal_age_seconds ?? chapter.send_age_seconds}s
              </dd>
            </>
          )}
        </dl>
      )}
      {action && (
        <LemonButton type="button" size="sm" variant="primary" className="mt-3 w-full" disabled={pending} onClick={executeAction}>
          {pending ? "Working..." : ACTION_LABELS[action]}
        </LemonButton>
      )}

      <label className="mt-4 block border-t border-rule pt-3 font-mono text-[11px] text-shadow-2 dark:border-charcoal-1 dark:text-moonlight" htmlFor="multimedia-run-id">
        Narration run ID
      </label>
      <div className="mt-1 flex gap-2">
        <LemonInput
          id="multimedia-run-id"
          value={runId}
          onChange={(event) => {
            requestGeneration.current += 1;
            setRunId(event.target.value);
            setRun(null);
            setError(null);
            setPending(false);
          }}
          wrapperClassName="min-w-0 flex-1"
        />
        <LemonButton type="button" size="sm" variant="secondary" disabled={pending || !runId.trim()} onClick={inspectRun}>
          Inspect
        </LemonButton>
      </div>
      {run && (
        <div className="mt-3" data-testid="run-reconciliation-status">
          <div className="flex items-center justify-between gap-2 text-[12px]">
            <span className="text-shadow-1 dark:text-moonlight">Blocked chapters</span>
            <LemonTag colour={run.blocked_chapter_count ? "danger" : "default"}>{run.blocked_chapter_count}</LemonTag>
          </div>
          <ol className="mt-2 space-y-1">
            {run.children.map((child) => (
              <li key={child.execution_id} className="flex items-center justify-between gap-2 text-[12px]">
                <span className="truncate text-ink dark:text-bright">{child.chapter_id}</span>
                <span className="text-shadow-2 dark:text-moonlight">{child.state}</span>
              </li>
            ))}
          </ol>
        </div>
      )}
      {error && <p className="mt-3 text-[12px] text-danger" role="alert">{error}</p>}
    </section>
  );
}
