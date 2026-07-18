import { useEffect, useRef, useState } from "react";

import {
  executeChapterTtsReconciliation,
  getAssetReconciliationLinks,
  getChapterTtsReconciliation,
  getNarrationRunReconciliation,
} from "../../api/multimedia";
import type {
  AssetReconciliationLinks,
  ChapterTtsReconciliation,
  NarrationRunReconciliation,
  TtsReconciliationAction,
} from "../../api/multimedia";
import { LemonButton, LemonTag } from "../../components/lemon";
import { emitWernerExperience } from "../../werner/reactionBus";

const ACTION_LABELS: Record<TtsReconciliationAction, string> = {
  quarantine_send: "Quarantine stale send",
  recover_unknown: "Recover provider audio",
  release_seal: "Release stale seal",
};

function eligibleAction(view: ChapterTtsReconciliation | null): TtsReconciliationAction | null {
  if (!view?.action_eligible) return null;
  return view.next_action in ACTION_LABELS ? (view.next_action as TtsReconciliationAction) : null;
}

function errorMessage(error: unknown): string {
  const value = error instanceof Error ? error.message : "";
  if (value === "multimedia_reconciliation_runtime_unavailable") return "Recovery runtime unavailable";
  if (value === "multimedia_reconciliation_action_conflict") return "Recovery state changed";
  if (value.includes("unavailable")) return "Recovery record unavailable";
  return "Recovery request failed";
}

export function ReconciliationPanel({ assetId }: { assetId: string | null }) {
  const [links, setLinks] = useState<AssetReconciliationLinks | null>(null);
  const [chapter, setChapter] = useState<ChapterTtsReconciliation | null>(null);
  const [run, setRun] = useState<NarrationRunReconciliation | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const requestGeneration = useRef(0);
  const action = eligibleAction(chapter);

  useEffect(() => {
    const generation = ++requestGeneration.current;
    setLinks(null);
    setChapter(null);
    setRun(null);
    setError(null);
    if (!assetId) {
      setPending(false);
      return;
    }
    setPending(true);
    getAssetReconciliationLinks(assetId)
      .then(async (result) => {
        if (requestGeneration.current !== generation || result.asset_id !== assetId) return;
        setLinks(result);
        const linked = result.executions.find((item) => item.reconciliation_available);
        if (!linked) return;
        const view = await getChapterTtsReconciliation(linked.execution_id);
        if (requestGeneration.current !== generation || view.execution_id !== linked.execution_id) return;
        setChapter(view);
      })
      .catch((caught) => {
        if (requestGeneration.current !== generation) return;
        setError(errorMessage(caught));
      })
      .finally(() => {
        if (requestGeneration.current === generation) setPending(false);
      });
  }, [assetId]);

  async function executeAction() {
    if (!action || !chapter || !links) return;
    const generation = ++requestGeneration.current;
    const executionId = chapter.execution_id;
    setPending(true);
    try {
      const result = await executeChapterTtsReconciliation(executionId, action);
      if (requestGeneration.current !== generation || result.execution_id !== executionId) return;
      setChapter(result);
      setLinks({
        ...links,
        executions: links.executions.map((item) =>
          item.execution_id === executionId ? { ...item, status: result.provider_status } : item,
        ),
      });
      setError(null);
      // Living-TV: operator recovered TTS reconciliation state.
      emitWernerExperience("note_saved");
    } catch (caught) {
      if (requestGeneration.current !== generation) return;
      setChapter(null);
      setError(errorMessage(caught));
      emitWernerExperience("fail");
    } finally {
      if (requestGeneration.current === generation) setPending(false);
    }
  }

  async function inspectExecution(executionId: string) {
    const generation = ++requestGeneration.current;
    setPending(true);
    try {
      const result = await getChapterTtsReconciliation(executionId);
      if (requestGeneration.current !== generation || result.execution_id !== executionId) return;
      setChapter(result);
      setRun(null);
      setError(null);
    } catch (caught) {
      if (requestGeneration.current !== generation) return;
      setChapter(null);
      setError(errorMessage(caught));
    } finally {
      if (requestGeneration.current === generation) setPending(false);
    }
  }

  async function inspectRun(runId: string) {
    const generation = ++requestGeneration.current;
    setPending(true);
    try {
      const result = await getNarrationRunReconciliation(runId);
      if (requestGeneration.current !== generation || result.run_id !== runId) return;
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

      {!assetId && <p className="mt-3 text-[12px] text-shadow-1 dark:text-moonlight">Select an asset to inspect recovery.</p>}
      {assetId && pending && !links && <p className="mt-3 text-[12px] text-shadow-1 dark:text-moonlight">Loading recovery state...</p>}
      {links && links.executions.length === 0 && links.narration_runs.length === 0 && (
        <p className="mt-3 text-[12px] text-shadow-1 dark:text-moonlight">No provider execution has started.</p>
      )}

      {links && links.executions.length > 0 && (
        <div className="mt-3">
          <p className="font-mono text-[11px] text-shadow-2 dark:text-moonlight">Chapter executions</p>
          <div className="mt-1 space-y-1">
            {links.executions.map((item) => (
              <LemonButton
                key={item.execution_id}
                type="button"
                size="sm"
                variant={chapter?.execution_id === item.execution_id ? "secondary" : "tertiary"}
                className="w-full justify-between"
                disabled={!item.reconciliation_available || pending}
                onClick={() => inspectExecution(item.execution_id)}
              >
                <span className="truncate">{item.provider}</span>
                <span>{chapter?.execution_id === item.execution_id ? chapter.attempt_status : item.status}</span>
              </LemonButton>
            ))}
          </div>
        </div>
      )}

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
              <dd className="text-right text-ink dark:text-bright">{chapter.seal_age_seconds ?? chapter.send_age_seconds}s</dd>
            </>
          )}
        </dl>
      )}
      {action && (
        <LemonButton type="button" size="sm" variant="primary" className="mt-3 w-full" disabled={pending} onClick={executeAction}>
          {pending ? "Working..." : ACTION_LABELS[action]}
        </LemonButton>
      )}

      {links && links.narration_runs.length > 0 && (
        <div className="mt-4 border-t border-rule pt-3 dark:border-charcoal-1">
          <p className="font-mono text-[11px] text-shadow-2 dark:text-moonlight">Narration runs</p>
          <div className="mt-1 space-y-1">
            {links.narration_runs.map((item) => (
              <LemonButton key={item.run_id} type="button" size="sm" variant="tertiary" className="w-full justify-between" aria-label={`Inspect narration run ${item.status}`} disabled={pending} onClick={() => inspectRun(item.run_id)}>
                <span>Narration</span><span>{item.status}</span>
              </LemonButton>
            ))}
          </div>
        </div>
      )}
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
