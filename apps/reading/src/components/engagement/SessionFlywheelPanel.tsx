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
 * Residual (re): Open Write twin_seed after flywheel complete.
 * Residual (acs): data-write-seed-has-body when output or prompt_block non-empty.
 * Residual (sn): float|full session complete HTML (output + prompt_block).
 * Residual (ant): budget soft-gate on Complete flywheel (budget-before-fire ·
 * parity merge ank/anl · continue-as-unit di · session land foresight).
 * Composes shipped completeSessionFlywheel. HTML-first context pack.
 */

import { useCallback, useMemo, useState } from "react";
import {
  completeSessionFlywheel,
  type SessionFlywheelResponse,
} from "../../api/engagement";
import { buildSessionFlywheelWriteHref } from "../../workspace/twinWriteSeed";
import { openWindow } from "../windows/openWindow";
import { DecisionTreeDriverBadge } from "./DecisionTreeDriverBadge";
import {
  ResearchLaunchBudgetPanel,
  type ResearchLaunchBudgetProjection,
  type ResearchLaunchTier,
} from "./ResearchLaunchBudgetPanel";

function buildSessionFlywheelHtml(opts: {
  sessionId: string;
  spawnId?: string | null;
  status?: string | null;
  outputText?: string | null;
  promptBlock?: string | null;
  researchTier?: string | null;
}): string {
  const escape = (s: string) =>
    String(s || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  const out = String(opts.outputText || "").trim();
  const pb = String(opts.promptBlock || "").trim();
  return [
    `<article data-source="session_flywheel_complete" data-view-format="html">`,
    `<h1>Session flywheel complete</h1>`,
    `<p class="meta">session=${escape(opts.sessionId)}`,
    opts.spawnId ? ` · spawn=${escape(String(opts.spawnId))}` : "",
    opts.status ? ` · status=${escape(String(opts.status))}` : "",
    opts.researchTier ? ` · tier=${escape(String(opts.researchTier))}` : "",
    `</p>`,
    out ? `<section><h2>Output</h2><pre>${escape(out)}</pre></section>` : "",
    pb
      ? `<section><h2>Context prompt_block</h2><pre>${escape(pb)}</pre></section>`
      : "",
    `</article>`,
  ].join("");
}

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
  // Residual (ant): budget soft-gate before session flywheel complete.
  const [budgetWarn, setBudgetWarn] = useState(false);
  const [forceOverBudget, setForceOverBudget] = useState(false);
  const [flywheelTier, setFlywheelTier] = useState<ResearchLaunchTier>(() => {
    const t = (researchTier || "").trim().toLowerCase();
    return t === "fast" || t === "deep" || t === "wrestle" ? t : "deep";
  });
  const onProjectionChange = useCallback((p: ResearchLaunchBudgetProjection) => {
    setBudgetWarn(p.wouldExceedBudget === true);
  }, []);

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
    // Residual (ant): budget-before-fire on session land complete.
    if (budgetWarn && !forceOverBudget) {
      setError(
        "Projected cost may exceed remaining daily budget — enable force override or reduce scope before complete flywheel.",
      );
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
  }, [
    sessionId,
    output,
    recordTwins,
    onCompleted,
    budgetWarn,
    forceOverBudget,
  ]);
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
    return fromProp || flywheelTier || "deep";
  }, [result, researchTier, flywheelTier]);

  const flywheelPromptText = useMemo(() => {
    const text = output.trim();
    if (text) return text.slice(0, 4000);
    return `session flywheel complete · ${sessionId.trim()}`;
  }, [output, sessionId]);

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
            href="/settings#decision-tree-panel"
            data-testid="session-flywheel-settings-link"
            className="underline opacity-80 hover:opacity-100"
            title="Open Settings decision-tree: driver, budget bar, sample cost projection"
          >
            Settings · driver & budget
          </a>
          <a
            href="/docs/campaigns/2026-07-09-research-reading-spine/DUAL-GATE-L1-L4-OPERATOR-CHECKLIST.md#l1-arxiv"
            data-testid="session-flywheel-dual-gate-checklist-link"
            className="underline opacity-80 hover:opacity-100"
            title="Dual-gate L1 arxiv hydrate checklist (prep only · offline default)"
          >
            Dual-gate L1 arxiv checklist
          </a>
          {/* Residual (aas): L2 Substack section (parity aal–aaq · session land). */}
          <a
            href="/docs/campaigns/2026-07-09-research-reading-spine/DUAL-GATE-L1-L4-OPERATOR-CHECKLIST.md#l2-substack"
            data-testid="session-flywheel-dual-gate-l2-link"
            className="underline opacity-80 hover:opacity-100"
            title="Dual-gate L2 Substack hydrate checklist (prep only · factory + ToS)"
          >
            Dual-gate L2 Substack checklist
          </a>
          {/* Residual (ajd): session land → competitive DR honesty map (parity progress/MO). */}
          <a
            href="/settings#settings-competitive-dr-scorecard"
            data-testid="session-flywheel-competitive-scorecard-link"
            className="underline opacity-80 hover:opacity-100"
            title="Settings competitive deep-research scorecard (usage→Antiek-bench flywheel honesty)"
          >
            Settings · competitive DR scorecard
          </a>
          <a
            href="/docs/campaigns/2026-07-09-research-reading-spine/FUTURE-AGENT-SPEC-competitive-deep-research-quality.md"
            data-testid="session-flywheel-competitive-dr-future-agent-link"
            className="underline opacity-80 hover:opacity-100"
            title="FUTURE-AGENT competitive deep-research quality brief"
          >
            FUTURE · competitive DR brief
          </a>
          {/* Residual (apy): hop/stage pipeline honesty (parity aps/apx). */}
          <span
            className="opacity-70"
            data-testid="session-flywheel-competitive-pipeline-hint"
            data-hop-pipeline="api"
            data-stage-pipeline="ape"
          >
            hops insights→questions→sources · stages plan→terminal
          </span>
          {/* Residual (ako): session land budget-before-fire → Settings prompt-cost (akk–akn). */}
          <a
            href="/settings#prompt-cost-projection"
            data-testid="session-flywheel-prompt-cost-projection-link"
            className="underline opacity-80 hover:opacity-100"
            title="Settings prompt-cost projection: estimate flywheel synthesis spend vs remaining daily budget"
          >
            Settings · prompt-cost projection
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
      {/* Residual (ant): budget foresight before session flywheel complete. */}
      <div
        className="space-y-2"
        data-testid="session-flywheel-budget-mount"
        data-view-format="html"
        data-research-tier={badgeResearchTier}
        data-budget-warn={String(budgetWarn)}
        data-budget-soft-gate="true"
      >
        <ResearchLaunchBudgetPanel
          promptText={flywheelPromptText}
          researchTier={
            badgeResearchTier === "fast" ||
            badgeResearchTier === "deep" ||
            badgeResearchTier === "wrestle"
              ? badgeResearchTier
              : flywheelTier
          }
          allowTierPick
          onResearchTierChange={setFlywheelTier}
          onProjectionChange={onProjectionChange}
        />
        {budgetWarn ? (
          <label
            className="flex items-center gap-2 text-[11px] font-mono text-emperor"
            data-testid="session-flywheel-over-budget-warn"
          >
            <input
              type="checkbox"
              data-testid="session-flywheel-force-over-budget"
              checked={forceOverBudget}
              onChange={(e) => setForceOverBudget(e.target.checked)}
              disabled={busy}
            />
            Force complete flywheel despite budget projection
          </label>
        ) : null}
      </div>
      <button
        type="button"
        data-testid="session-flywheel-complete"
        data-budget-soft-gate={String(budgetWarn && !forceOverBudget)}
        disabled={
          busy ||
          output.trim().length < 3 ||
          (budgetWarn && !forceOverBudget)
        }
        onClick={() => void complete()}
        className="rounded border border-ink/30 px-2 py-1 text-[12px] font-mono hover:bg-ink/5 disabled:opacity-50 dark:border-bright/30"
        title={
          budgetWarn && !forceOverBudget
            ? "Over budget — enable force override before complete flywheel"
            : "Land output → twins/context pack → usage events"
        }
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
          {/* Residual (sn): flywheel complete → float|full HTML reading windows. */}
          {(output.trim() || (result.prompt_block || "").trim()) ? (
            <p className="space-x-3">
              <button
                type="button"
                data-testid="session-flywheel-open-float"
                data-view-format="html"
                data-window-mode="floating"
                data-status={result.status ?? ""}
                className="underline opacity-90 hover:opacity-100 bg-transparent border-0 p-0 cursor-pointer font-mono text-[11px]"
                title="Open session flywheel complete as floating HTML window (never PDF)"
                onClick={() => {
                  const sid = result.session_id || sessionId;
                  const id = `session_flywheel:${sid}:${Date.now().toString(36)}`;
                  const tier = flywheelResearchTier(result).effective;
                  openWindow(
                    "hosted_html_document",
                    {
                      document_id: id,
                      title: `Session flywheel · ${sid}`,
                      html: buildSessionFlywheelHtml({
                        sessionId: sid,
                        spawnId: result.spawn_id,
                        status: result.status,
                        outputText: output,
                        promptBlock: result.prompt_block,
                        researchTier: tier,
                      }),
                      view_format: "html",
                      source: "session_flywheel_complete",
                      research_tier: tier || null,
                    },
                    {
                      id: `win:flywheel:${id}`,
                      title: "Session flywheel",
                      mode: "floating",
                    },
                  );
                }}
              >
                Open float (session HTML)
              </button>
              <button
                type="button"
                data-testid="session-flywheel-open-full"
                data-view-format="html"
                data-window-mode="full"
                data-status={result.status ?? ""}
                className="underline opacity-90 hover:opacity-100 bg-transparent border-0 p-0 cursor-pointer font-mono text-[11px]"
                title="Open session flywheel complete as full working-region HTML window (never PDF)"
                onClick={() => {
                  const sid = result.session_id || sessionId;
                  const id = `session_flywheel:${sid}:full:${Date.now().toString(36)}`;
                  const tier = flywheelResearchTier(result).effective;
                  openWindow(
                    "hosted_html_document",
                    {
                      document_id: id,
                      title: `Session flywheel · ${sid} (full)`,
                      html: buildSessionFlywheelHtml({
                        sessionId: sid,
                        spawnId: result.spawn_id,
                        status: result.status,
                        outputText: output,
                        promptBlock: result.prompt_block,
                        researchTier: tier,
                      }),
                      view_format: "html",
                      source: "session_flywheel_complete",
                      research_tier: tier || null,
                    },
                    {
                      id: `win:flywheel:${id}:full`,
                      title: "Session flywheel (full)",
                      mode: "full",
                    },
                  );
                }}
              >
                Open full (session HTML)
              </button>
            </p>
          ) : null}
          {/* Residual (re/acs/aex): flywheel complete → Write twin_seed + path. */}
          {(() => {
            const href = buildSessionFlywheelWriteHref({
              sessionId: result.session_id || sessionId,
              spawnId: result.spawn_id,
              outputText: output,
              promptBlock: result.prompt_block,
              status: result.status,
              researchTier: flywheelResearchTier(result).effective,
            });
            const hasBody = Boolean(
              String(output || "").trim() ||
                String(result.prompt_block || "").trim(),
            );
            const fwSession = String(
              result.session_id || sessionId || "",
            ).trim();
            const fwSpawn = String(result.spawn_id || "").trim();
            const fwTier = flywheelResearchTier(result).effective;
            return href ? (
              <p>
                <a
                  href={href}
                  data-testid="session-flywheel-open-write"
                  data-view-format="html"
                  data-has-twin-seed="1"
                  data-status={result.status ?? ""}
                  data-write-seed-has-body={String(hasBody)}
                  // Residual (aex): session flywheel → Write path honesty.
                  data-session-id={fwSession}
                  data-spawn-id={fwSpawn}
                  data-research-tier={
                    (fwTier || "").toString().trim().toLowerCase() || ""
                  }
                  data-seamless-flywheel-write={String(
                    Boolean(fwSession || fwSpawn),
                  )}
                  className="underline opacity-90 hover:opacity-100"
                  title="Open Write with session flywheel output as twin_seed (session complete · no invented document_id)"
                >
                  Open Write (session complete)
                </a>
              </p>
            ) : null;
          })()}
        </div>
      ) : null}
    </section>
  );
}

export default SessionFlywheelPanel;
