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
 * Residual (kq): fall back to context.research_tier (pack identity from kk)
 * when session research_tier is absent; expose data-context-research-tier.
 * Residual (lt): DecisionTreeDriverBadge with pre/post complete tier.
 * Residual (qn): DecisionTreeDriverBadge promptText from session output.
 * Residual (np): dual-gate L1–L4 checklist deep-link (prep only).
 * Composes shipped completeSessionFlywheel. HTML-first context pack.
 */

import { useCallback, useMemo, useState } from "react";
import {
  completeSessionFlywheel,
  type SessionFlywheelResponse,
} from "../../api/engagement";
import { DecisionTreeDriverBadge } from "./DecisionTreeDriverBadge";

export type SessionFlywheelPanelProps = {
  sessionId: string;
  /** Seed output from selection / goal when operator has not edited. */
  defaultOutputText?: string;
  /** Residual (ee): after successful flywheel complete. */
  onCompleted?: (result: SessionFlywheelResponse) => void;
  /**
   * Residual (lt): optional pre-complete research tier for driver badge;
   * after complete, session||context pack tier wins.
   */
  researchTier?: "fast" | "deep" | "wrestle" | string | null;
};

export function SessionFlywheelPanel({
  sessionId,
  defaultOutputText = "",
  onCompleted,
  researchTier = null,
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
  /** Residual (kq): session tier wins; pack context.research_tier is fallback. */
  const flywheelResearchTier = (
    r: SessionFlywheelResponse,
  ): { effective: string; pack: string } => {
    const pack = String(r.context?.research_tier || "")
      .trim()
      .toLowerCase();
    const session = String(r.research_tier || "")
      .trim()
      .toLowerCase();
    return { effective: session || pack, pack };
  };

  // Residual (lt): post-complete effective tier wins over prop / default deep.
  const badgeResearchTier = useMemo(() => {
    if (result) {
      const eff = flywheelResearchTier(result).effective;
      if (eff) return eff;
    }
    const fromProp = (researchTier || "").trim().toLowerCase();
    return fromProp || "deep";
  }, [result, researchTier]);

  return (
    <section
      className="space-y-2"
      data-testid="session-flywheel-panel"
      data-view-format="html"
      data-research-tier={badgeResearchTier}
      aria-label="Complete research flywheel"
    >
      <header>
        <h2 className="text-sm font-medium text-ink dark:text-parchment">
          Complete session flywheel
        </h2>
        <p className="text-[11px] font-mono text-shadow-1 dark:text-moonlight">
          Land output → twins/context pack → usage events for Antiek-bench
        </p>
        {/* Residual (ii/np): Settings + dual-gate checklist (flywheel prep). */}
        <p className="text-[11px] font-mono space-x-3">
          <a
            href="/settings"
            data-testid="session-flywheel-settings-link"
            className="underline opacity-80 hover:opacity-100"
            title="Open Settings for decision-tree driver and daily budget"
          >
            Settings · driver & budget
          </a>
          <a
            href="/docs/campaigns/2026-07-09-research-reading-spine/DUAL-GATE-L1-L4-OPERATOR-CHECKLIST.md"
            data-testid="session-flywheel-dual-gate-checklist-link"
            className="underline opacity-80 hover:opacity-100"
            title="Dual-gate L1–L4 checklist (prep only; offline default)"
          >
            Dual-gate L1–L4 checklist
          </a>
        </p>
        {/* Residual (lt): model+budget+depth before/after flywheel complete. */}
        <div
          data-testid="session-flywheel-driver-badge-mount"
          data-view-format="html"
          data-research-tier={badgeResearchTier}
        >
          <DecisionTreeDriverBadge
            researchTier={badgeResearchTier}
            promptText={
              (output || defaultOutputText || "").trim() ||
              `session flywheel · ${sessionId.trim()}`
            }
          />
        </div>
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
          data-research-tier={flywheelResearchTier(result).effective}
          data-context-research-tier={flywheelResearchTier(result).pack}
        >
          {/* Residual (hj/jt/kq): flywheel close + session/pack depth identity. */}
          <div
            data-testid="session-flywheel-metrics"
            data-status={result.status ?? ""}
            data-session-id={result.session_id ?? ""}
            data-spawn-id={result.spawn_id ?? ""}
            data-twin-count={String(flywheelTwinCount(result))}
            data-ref-count={String(flywheelRefCount(result))}
            data-record-twins={String(recordTwins)}
            data-research-tier={
              flywheelResearchTier(result).effective ||
              (result.usage_event?.task_class as string) ||
              ""
            }
            data-context-research-tier={flywheelResearchTier(result).pack}
            data-usage-task-class={
              (result.usage_event?.task_class || "") as string
            }
            data-usage-outcome={(result.usage_event?.outcome || "") as string}
            data-view-format="html"
            role="status"
          >
            Session flywheel · status={result.status} · twins=
            {flywheelTwinCount(result)} · refs={flywheelRefCount(result)}
            {flywheelResearchTier(result).effective
              ? ` · tier=${flywheelResearchTier(result).effective}`
              : ""}
            {result.usage_event?.task_class
              ? ` · bench=${result.usage_event.task_class}`
              : ""}
          </div>
          <p>
            status=<code>{result.status}</code> · session=
            <code>{result.session_id}</code> · spawn=
            <code>{result.spawn_id}</code>
            {flywheelResearchTier(result).effective ? (
              <>
                {" "}
                · tier=<code data-testid="session-flywheel-research-tier">
                  {flywheelResearchTier(result).effective}
                </code>
              </>
            ) : null}
          </p>
          {/* Residual (kq): pack context.research_tier when present (parity kk). */}
          {flywheelResearchTier(result).pack ? (
            <p
              className="opacity-80"
              data-testid="session-flywheel-context-research-tier"
              data-context-research-tier={flywheelResearchTier(result).pack}
              role="status"
            >
              Context pack research_tier=
              <code>{flywheelResearchTier(result).pack}</code>
            </p>
          ) : null}
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
