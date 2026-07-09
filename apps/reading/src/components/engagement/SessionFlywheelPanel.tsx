/**
 * SessionFlywheelPanel — complete floating deep-research session flywheel.
 *
 * Residual (cl): records output + optional twins/promote into research context
 * and feeds Antiek-bench usage events (server-side best-effort).
 * Residual (ee): onCompleted notifies parent so research context remounts
 * after twins/usage land.
 * Residual (hj): session-flywheel-metrics machine attrs for recursive
 * note-taker + Antiek-bench audit (parity twin-notes / twin-promote metrics).
 * Residual (ii): Settings deep-link for driver + budget before complete.
 * Residual (jt): surface research_tier + Antiek-bench task_class from usage
 * event so recursive rewrite feed is operator-auditable on flywheel close.
 * Composes shipped completeSessionFlywheel. HTML-first context pack.
 */

import { useCallback, useState } from "react";
import {
  completeSessionFlywheel,
  type SessionFlywheelResponse,
} from "../../api/engagement";

export type SessionFlywheelPanelProps = {
  sessionId: string;
  /** Seed output from selection / goal when operator has not edited. */
  defaultOutputText?: string;
  /** Residual (ee): after successful flywheel complete. */
  onCompleted?: (result: SessionFlywheelResponse) => void;
};

export function SessionFlywheelPanel({
  sessionId,
  defaultOutputText = "",
  onCompleted,
}: SessionFlywheelPanelProps) {
  const [output, setOutput] = useState(defaultOutputText);
  const [recordTwins, setRecordTwins] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<SessionFlywheelResponse | null>(null);

  const complete = useCallback(async () => {
    const sid = sessionId.trim();
    const text = output.trim();
    if (!sid) {
      setError("sessionId is required");
      return;
    }
    if (text.length < 3) {
      setError("Output text must be at least 3 characters");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const out = await completeSessionFlywheel({
        session_id: sid,
        output_text: text,
        record_twins: recordTwins,
        include_twin_promote: recordTwins,
      });
      if (out.view_format !== "html") {
        throw new Error("flywheel view_format must be html");
      }
      setResult(out);
      onCompleted?.(out);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }, [sessionId, output, recordTwins, onCompleted]);

  const flywheelTwinCount = (r: SessionFlywheelResponse): number => {
    const ctx = r.context;
    if (typeof ctx?.twin_count === "number") return ctx.twin_count;
    if (Array.isArray(ctx?.twin_units)) return ctx.twin_units.length;
    return 0;
  };
  const flywheelRefCount = (r: SessionFlywheelResponse): number => {
    const ctx = r.context;
    if (typeof ctx?.ref_count === "number") return ctx.ref_count;
    if (Array.isArray(ctx?.source_references)) return ctx.source_references.length;
    return 0;
  };

  return (
    <section
      className="space-y-2"
      data-testid="session-flywheel-panel"
      data-view-format="html"
      aria-label="Complete research flywheel"
    >
      <header>
        <h2 className="text-sm font-medium text-ink dark:text-parchment">
          Complete session flywheel
        </h2>
        <p className="text-[11px] font-mono text-shadow-1 dark:text-moonlight">
          Land output → twins/context pack → usage events for Antiek-bench
        </p>
        {/* Residual (ii): Settings deep-link for model driver + budget. */}
        <p className="text-[11px] font-mono">
          <a
            href="/settings"
            data-testid="session-flywheel-settings-link"
            className="underline opacity-80 hover:opacity-100"
            title="Open Settings for decision-tree driver and daily budget"
          >
            Settings · driver & budget
          </a>
        </p>
      </header>
      <textarea
        data-testid="session-flywheel-output"
        value={output}
        onChange={(e) => setOutput(e.target.value)}
        disabled={busy}
        rows={3}
        placeholder="Synthesis / findings to record for this session…"
        className="w-full rounded border border-ink/20 bg-transparent px-2 py-1 text-[12px] font-mono dark:border-bright/20"
      />
      <label className="flex items-center gap-2 text-[11px] font-mono">
        <input
          type="checkbox"
          data-testid="session-flywheel-record-twins"
          checked={recordTwins}
          onChange={(e) => setRecordTwins(e.target.checked)}
          disabled={busy}
        />
        Record twin notes + promote to context
      </label>
      <button
        type="button"
        data-testid="session-flywheel-complete"
        disabled={busy || output.trim().length < 3}
        onClick={() => void complete()}
        className="rounded border border-ink/30 px-2 py-1 text-[12px] font-mono hover:bg-ink/5 disabled:opacity-50 dark:border-bright/30"
      >
        {busy ? "Completing…" : "Complete flywheel"}
      </button>
      {error ? (
        <p className="text-[11px] font-mono text-emperor" role="alert">
          {error}
        </p>
      ) : null}
      {result ? (
        <div
          className="space-y-1 rounded border border-ink/10 p-2 text-[11px] font-mono dark:border-bright/10"
          data-testid="session-flywheel-result"
          data-view-format="html"
        >
          {/* Residual (hj/jt): machine-readable flywheel close + bench tier. */}
          <div
            data-testid="session-flywheel-metrics"
            data-status={result.status ?? ""}
            data-session-id={result.session_id ?? ""}
            data-spawn-id={result.spawn_id ?? ""}
            data-twin-count={String(flywheelTwinCount(result))}
            data-ref-count={String(flywheelRefCount(result))}
            data-record-twins={String(recordTwins)}
            data-research-tier={
              (result.research_tier ||
                result.usage_event?.task_class ||
                "") as string
            }
            data-usage-task-class={
              (result.usage_event?.task_class || "") as string
            }
            data-usage-outcome={(result.usage_event?.outcome || "") as string}
            data-view-format="html"
            role="status"
          >
            Session flywheel · status={result.status} · twins=
            {flywheelTwinCount(result)} · refs={flywheelRefCount(result)}
            {result.research_tier
              ? ` · tier=${result.research_tier}`
              : ""}
            {result.usage_event?.task_class
              ? ` · bench=${result.usage_event.task_class}`
              : ""}
          </div>
          <p>
            status=<code>{result.status}</code> · session=
            <code>{result.session_id}</code> · spawn=
            <code>{result.spawn_id}</code>
            {result.research_tier ? (
              <>
                {" "}
                · tier=<code data-testid="session-flywheel-research-tier">
                  {result.research_tier}
                </code>
              </>
            ) : null}
          </p>
          {result.usage_event?.task_class ? (
            <p
              className="opacity-80"
              data-testid="session-flywheel-usage-task-class"
            >
              Antiek-bench task_class=
              <code>{result.usage_event.task_class}</code>
              {result.usage_event.outcome
                ? ` · outcome=${result.usage_event.outcome}`
                : ""}
            </p>
          ) : null}
          {result.prompt_block ? (
            <pre
              className="max-h-32 overflow-auto whitespace-pre-wrap"
              data-testid="session-flywheel-prompt-block"
            >
              {result.prompt_block}
            </pre>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}

export default SessionFlywheelPanel;
