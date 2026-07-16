import { startRegistration } from "@simplewebauthn/browser";
import { type KeyboardEvent, useEffect, useMemo, useRef, useState } from "react";
import { useViewportTier } from "../../workspace/useViewportTier";
import LemonCard from "../../components/lemon/LemonCard";
import { LemonButton } from "../../components/lemon";
import {
  beginPasskeyRegistration,
  finishPasskeyRegistration,
  listPasskeys,
  removePasskey,
  type SavedPasskey,
} from "../../lib/auth";
import {
  estimatePromptCost,
  fetchModelDecision,
  fetchSettingsBudget,
  fetchSettingsModels,
  type BudgetResponse,
  type ModelDecisionResponse,
  type ModelDecisionTask,
  type ModelRow,
  type PromptCostEstimateResponse,
} from "../../api/settings";
import thinkingArt from "../../brand/werner/poses/session/werner_thinking_session_v1.png";
import livingTvArt from "../../brand/werner/poses/session/werner_living_tv_session_v1.webp";
import AddModelPanel from "./AddModelPanel";
import AntiekBenchPanel from "./AntiekBenchPanel";
import { ModelDecisionTreeTab } from "./modelSelection/ModelDecisionTreeTab";
import { NotDiamondShadowToggle } from "./modelSelection/NotDiamondShadowToggle";
import { MidnightOilPanel } from "./modelSelection/MidnightOilPanel";
import type { NotDiamondMode } from "./modelSelection/notDiamondPolicy";
import { emitWernerExperience } from "../../werner/reactionBus";

/**
 * Operator Settings — model inventory + budget + prompt projection (SPR-01).
 *
 * Honesty: spent/pricing may be unknown; UI never invents $0.00 when the
 * ledger or rate table is unset. Add-model securely registers BYOK providers;
 * granting one dispatch-route authority remains a separate, explicit sprint.
 */
export default function Settings() {
  const tier = useViewportTier();
  const isDark =
    typeof window !== "undefined" &&
    typeof window.matchMedia === "function" &&
    window.matchMedia("(prefers-color-scheme: dark)").matches;
  const reduceMotion =
    typeof window !== "undefined" &&
    typeof window.matchMedia === "function" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  const [models, setModels] = useState<ModelRow[] | null>(null);
  const [modelsError, setModelsError] = useState<string | null>(null);
  const [budget, setBudget] = useState<BudgetResponse | null>(null);
  const [budgetError, setBudgetError] = useState<string | null>(null);
  const [inputChars, setInputChars] = useState(2000);
  const [outTokens, setOutTokens] = useState(500);
  const [estimate, setEstimate] = useState<PromptCostEstimateResponse | null>(
    null,
  );
  const [estimateError, setEstimateError] = useState<string | null>(null);
  const [estimating, setEstimating] = useState(false);
  const [activeTab, setActiveTab] = useState<"overview" | "decision">("overview");
  // NotDiamond is advisory-only — shared state drives the heuristic decision-tree chip.
  const [notDiamondMode, setNotDiamondMode] =
    useState<NotDiamondMode>("disabled");

  function onTabKeyDown(event: KeyboardEvent<HTMLButtonElement>) {
    const tabs = ["overview", "decision"] as const;
    const current = tabs.indexOf(activeTab);
    let next = current;
    if (event.key === "ArrowRight") next = (current + 1) % tabs.length;
    else if (event.key === "ArrowLeft") next = (current - 1 + tabs.length) % tabs.length;
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = tabs.length - 1;
    else return;
    event.preventDefault();
    const selected = tabs[next];
    setActiveTab(selected);
    document.getElementById(`settings-${selected}-tab`)?.focus();
  }

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const m = await fetchSettingsModels();
        if (!cancelled) setModels(m.models);
      } catch (e) {
        if (!cancelled)
          setModelsError(e instanceof Error ? e.message : String(e));
      }
      try {
        const b = await fetchSettingsBudget();
        if (!cancelled) setBudget(b);
      } catch (e) {
        if (!cancelled)
          setBudgetError(e instanceof Error ? e.message : String(e));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const spendPct = useMemo(() => {
    if (
      !budget ||
      budget.daily_cap_usd == null ||
      budget.reserved_estimated_usd == null ||
      budget.daily_cap_usd <= 0
    ) {
      return null;
    }
    return Math.min(
      100,
      (budget.reserved_estimated_usd / budget.daily_cap_usd) * 100,
    );
  }, [budget]);

  async function onEstimate() {
    setEstimating(true);
    setEstimateError(null);
    try {
      const res = await estimatePromptCost({
        tier: "pro",
        input_chars: inputChars,
        expected_output_tokens: outTokens,
      });
      setEstimate(res);
      // Living-TV beat: over-budget projection makes Werner dizzy; safe stays calm.
      if (res.would_exceed_budget === true) {
        emitWernerExperience("fail");
      } else if (res.would_exceed_budget === false) {
        emitWernerExperience("highlight");
      }
    } catch (e) {
      setEstimateError(e instanceof Error ? e.message : String(e));
      emitWernerExperience("fail");
    } finally {
      setEstimating(false);
    }
  }

  return (
    <div className="h-full overflow-y-auto bg-ice-2 dark:bg-space-2">
      <div className="max-w-3xl mx-auto px-6 py-8 space-y-6">
        <header>
          <div className="flex items-center gap-3">
            <img
              src={thinkingArt}
              alt=""
              aria-hidden="true"
              data-testid="settings-home-werner-brand"
              className="h-12 w-12 shrink-0 object-contain"
            />
            <h1 className="text-2xl font-serif text-ink dark:text-bright">
              Operator settings
            </h1>
          </div>
          <img
            src={livingTvArt}
            alt=""
            aria-hidden="true"
            data-testid="settings-home-living-tv-art"
            className="mt-2 h-16 w-full max-w-md rounded-md object-cover object-center"
            loading="lazy"
            decoding="async"
          />
          <p className="text-sm text-ink-soft dark:text-starlight font-serif italic mt-1">
            Models, budget ceiling, and prompt cost projection. Numbers over
            placeholders — unknown spend stays unknown.
          </p>
          <div className="mt-5 flex gap-1 border-b border-ink/15 dark:border-bright/15" role="tablist" aria-label="Settings views">
            <button
              id="settings-overview-tab"
              type="button"
              role="tab"
              aria-selected={activeTab === "overview"}
              aria-controls="settings-overview-panel"
              tabIndex={activeTab === "overview" ? 0 : -1}
              onClick={() => setActiveTab("overview")}
              onKeyDown={onTabKeyDown}
              className={`px-3 py-2 text-sm font-semibold ${activeTab === "overview" ? "border-b-2 border-ink text-ink dark:border-bright dark:text-bright" : "text-ink-soft dark:text-starlight"}`}
            >
              Overview
            </button>
            <button
              id="settings-decision-tab"
              type="button"
              role="tab"
              aria-selected={activeTab === "decision"}
              aria-controls="settings-decision-panel"
              tabIndex={activeTab === "decision" ? 0 : -1}
              onClick={() => setActiveTab("decision")}
              onKeyDown={onTabKeyDown}
              className={`px-3 py-2 text-sm font-semibold ${activeTab === "decision" ? "border-b-2 border-ink text-ink dark:border-bright dark:text-bright" : "text-ink-soft dark:text-starlight"}`}
            >
              Decision tree
            </button>
          </div>
        </header>

        {activeTab === "overview" ? (
          <div
            id="settings-overview-panel"
            role="tabpanel"
            aria-labelledby="settings-overview-tab"
            tabIndex={0}
            className="space-y-6"
          >
        <LemonCard title="Environment" elevation="z1">
          <div className="p-4 space-y-3 font-mono text-[13px]">
            <Row label="Viewport tier" value={tier} />
            <Row label="OS theme" value={isDark ? "dark" : "light"} />
            <Row
              label="Reduce motion"
              value={reduceMotion ? "yes" : "no"}
            />
            <Row
              label="UI version"
              value={
                (import.meta.env.VITE_ANTIEK_UI as string | undefined) ?? "v2"
              }
            />
          </div>
        </LemonCard>

        <PasskeySettings />

        <LemonCard title="Models & providers" elevation="z1">
          <div className="p-4 space-y-3">
            {modelsError && (
              <p className="text-sm text-red-700 dark:text-red-300 font-mono">
                {modelsError}
              </p>
            )}
            {models === null && !modelsError && (
              <p className="text-sm text-ink-soft dark:text-starlight">
                Loading providers…
              </p>
            )}
            {models && models.length === 0 && (
              <p className="text-sm text-ink-soft dark:text-starlight">
                No providers registered and none configured in dispatch
                config.
              </p>
            )}
            {models && models.length > 0 && (
              <ul className="space-y-2">
                {models.map((m) => (
                  <li
                    key={m.provider_id}
                    className="flex flex-wrap items-baseline justify-between gap-2 border-b border-ink/10 dark:border-bright/10 pb-2 font-mono text-[13px]"
                  >
                    <span className="text-ink dark:text-bright font-semibold">
                      {m.provider_id}
                      {m.primary_model ? (
                        <span className="font-normal text-ink-soft dark:text-starlight">
                          {" "}
                          · {m.primary_model}
                        </span>
                      ) : null}
                    </span>
                    <span
                      className={
                        m.ready
                          ? "text-emerald-700 dark:text-emerald-300"
                          : "text-amber-700 dark:text-amber-300"
                      }
                    >
                      {m.ready ? "ready" : m.registered ? "registered" : "not registered"}
                    </span>
                    {m.tier_bindings.length > 0 && (
                      <span className="w-full text-[11px] text-ink-soft dark:text-starlight">
                        tiers: {m.tier_bindings.join(", ")}
                      </span>
                    )}
                    {m.notes && (
                      <span className="w-full text-[11px] text-ink-soft dark:text-starlight">
                        {m.notes}
                      </span>
                    )}
                  </li>
                ))}
              </ul>
            )}
            <p className="text-[11px] text-ink-soft dark:text-starlight font-serif italic">
              Add your own models with the card below. Decision-tree
              per-prompt override lands in SPR-03.
            </p>
          </div>
        </LemonCard>

        <LemonCard title="Budget" elevation="z1">
          <div className="p-4 space-y-3">
            {budgetError && (
              <p className="text-sm text-red-700 dark:text-red-300 font-mono">
                {budgetError}
              </p>
            )}
            {budget && (
              <>
                <div className="font-mono text-[13px] space-y-2">
                  <Row
                    label="Daily cap"
                    value={
                      budget.daily_cap_usd == null
                        ? "unset"
                        : `$${budget.daily_cap_usd.toFixed(2)}`
                    }
                  />
                  <Row
                    label="Reserved estimate today"
                    value={
                      budget.spend_basis === "reserved_estimate" &&
                      budget.reserved_estimated_usd != null
                        ? `$${budget.reserved_estimated_usd.toFixed(4)}`
                        : "unknown (ledger not inventing $0)"
                    }
                  />
                  <Row
                    label="Remaining"
                    value={
                      budget.remaining_usd == null
                        ? "unknown"
                        : `$${budget.remaining_usd.toFixed(4)}`
                    }
                  />
                  {budget.cap_env && (
                    <Row label="Cap source" value={budget.cap_env} />
                  )}
                  {budget.enforcement_cap_usd != null && (
                    <Row
                      label="Daemon enforcement cap"
                      value={`$${budget.enforcement_cap_usd.toFixed(2)}`}
                    />
                  )}
                </div>
                <div
                  className="h-2 w-full rounded-full bg-ink/10 dark:bg-bright/10 overflow-hidden"
                  role="progressbar"
                  aria-valuemin={0}
                  aria-valuemax={100}
                  aria-valuenow={spendPct ?? 0}
                  aria-label="Budget usage"
                >
                  {spendPct != null ? (
                    <div
                      className="h-full bg-ink dark:bg-bright transition-all"
                      style={{ width: `${spendPct}%` }}
                    />
                  ) : (
                    <div className="h-full w-full bg-dashed opacity-30" />
                  )}
                </div>
                {spendPct == null && (
                  <p className="text-[11px] text-ink-soft dark:text-starlight">
                    Usage bar empty when spend is unknown or cap is unset.
                  </p>
                )}
                {budget.notes.length > 0 && (
                  <ul className="text-[11px] text-ink-soft dark:text-starlight list-disc list-inside space-y-1">
                    {budget.notes.map((n) => (
                      <li key={n}>{n}</li>
                    ))}
                  </ul>
                )}
              </>
            )}
          </div>
        </LemonCard>

        <LemonCard title="Prompt cost projection" elevation="z1" colour="glacial">
          <div className="p-4 space-y-3">
            <p className="text-sm text-ink dark:text-bright">
              Estimate how a proposed pro-tier prompt would hit today&apos;s
              remaining budget. Projection uses dispatch config rates —
              placeholder 0.0 rates yield an honest null, not a fake price.
            </p>
            <div className="grid grid-cols-2 gap-3 font-mono text-[13px]">
              <label className="flex flex-col gap-1">
                <span className="text-[11px] uppercase tracking-wider text-ink-soft dark:text-starlight">
                  Input chars
                </span>
                <input
                  type="number"
                  min={0}
                  value={inputChars}
                  onChange={(e) => setInputChars(Number(e.target.value) || 0)}
                  className="border border-ink/20 dark:border-bright/20 bg-transparent px-2 py-1 rounded"
                />
              </label>
              <label className="flex flex-col gap-1">
                <span className="text-[11px] uppercase tracking-wider text-ink-soft dark:text-starlight">
                  Expected output tokens
                </span>
                <input
                  type="number"
                  min={0}
                  value={outTokens}
                  onChange={(e) => setOutTokens(Number(e.target.value) || 0)}
                  className="border border-ink/20 dark:border-bright/20 bg-transparent px-2 py-1 rounded"
                />
              </label>
            </div>
            <button
              type="button"
              onClick={onEstimate}
              disabled={estimating}
              className="px-3 py-1.5 rounded border border-ink dark:border-bright text-sm font-mono hover:bg-ink/5 dark:hover:bg-bright/10 disabled:opacity-50"
            >
              {estimating ? "Estimating…" : "Project cost"}
            </button>
            {estimateError && (
              <p className="text-sm text-red-700 dark:text-red-300 font-mono">
                {estimateError}
              </p>
            )}
            {estimate && (
              <div className="font-mono text-[13px] space-y-1">
                <Row
                  label="Pricing known"
                  value={estimate.pricing_known ? "yes" : "no"}
                />
                <Row
                  label="Estimate low"
                  value={
                    estimate.estimated_usd_low == null
                      ? "—"
                      : `$${estimate.estimated_usd_low.toFixed(6)}`
                  }
                />
                <Row
                  label="Estimate high"
                  value={
                    estimate.estimated_usd_high == null
                      ? "—"
                      : `$${estimate.estimated_usd_high.toFixed(6)}`
                  }
                />
                <Row
                  label="Would exceed budget"
                  value={
                    estimate.would_exceed_budget == null
                      ? "unknown"
                      : estimate.would_exceed_budget
                        ? "yes"
                        : "no"
                  }
                />
                {estimate.notes.map((n) => (
                  <p
                    key={n}
                    className="text-[11px] text-ink-soft dark:text-starlight"
                  >
                    {n}
                  </p>
                ))}
              </div>
            )}
          </div>
        </LemonCard>

        <AddModelPanel />

        <AntiekBenchPanel />

        {/* Heuristic demo tree + NotDiamond advisor + Midnight Oil preflight.
            Lives on Overview so the Decision tree tab keeps a single live
            Task control (server-owned compare) without label collisions. */}
        <LemonCard
          title="Heuristic tree · NotDiamond · Midnight Oil"
          elevation="z1"
          colour="glacial"
        >
          <div className="p-4 space-y-6">
            <ModelDecisionTreeTab notDiamondMode={notDiamondMode} />
            <NotDiamondShadowToggle
              mode={notDiamondMode}
              onModeChange={setNotDiamondMode}
            />
            <MidnightOilPanel />
          </div>
        </LemonCard>

        <LemonCard title="Coming later" elevation="z1">
          <ul className="p-4 space-y-2 text-sm text-ink dark:text-bright list-disc list-inside">
            <li>Recursive Antiek-bench evolution from usage outcomes</li>
            <li>NotDiamond live HTTP adapter (bench promotion gate — not this UI)</li>
            <li>Keyboard map customisation + layout export</li>
          </ul>
        </LemonCard>
          </div>
        ) : (
          <div
            id="settings-decision-panel"
            role="tabpanel"
            aria-labelledby="settings-decision-tab"
            tabIndex={0}
          >
            <DecisionTreePanel
              inputChars={inputChars}
              setInputChars={setInputChars}
              outputTokens={outTokens}
              setOutputTokens={setOutTokens}
            />
          </div>
        )}
      </div>
    </div>
  );
}
const DECISION_TASKS: Array<{ value: ModelDecisionTask; label: string }> = [
  { value: "deep_research", label: "Deep research" },
  { value: "research_synthesis", label: "Research synthesis" },
  { value: "reading", label: "Reading" },
  { value: "twin_note", label: "Twin note" },
  { value: "writing", label: "Writing" },
  { value: "multimedia", label: "Multimedia" },
  { value: "general", label: "General" },
];

function DecisionTreePanel({
  inputChars,
  setInputChars,
  outputTokens,
  setOutputTokens,
}: {
  inputChars: number;
  setInputChars: (value: number) => void;
  outputTokens: number;
  setOutputTokens: (value: number) => void;
}) {
  const [task, setTask] = useState<ModelDecisionTask>("deep_research");
  const [decision, setDecision] = useState<ModelDecisionResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const requestVersion = useRef(0);

  function invalidateDecision() {
    requestVersion.current += 1;
    setDecision(null);
    setError(null);
    setLoading(false);
  }

  async function compare() {
    const version = requestVersion.current + 1;
    requestVersion.current = version;
    setLoading(true);
    setError(null);
    try {
      const response = await fetchModelDecision({
        task,
        input_chars: inputChars,
        expected_output_tokens: outputTokens,
      });
      if (requestVersion.current === version) setDecision(response);
    } catch (caught) {
      if (requestVersion.current === version) {
        setError(caught instanceof Error ? caught.message : String(caught));
      }
    } finally {
      if (requestVersion.current === version) setLoading(false);
    }
  }

  return (
    <section aria-labelledby="decision-tree-title" className="space-y-5">
      <div>
        <h2 id="decision-tree-title" className="font-serif text-xl text-ink dark:text-bright">Model decision</h2>
        <p className="mt-1 text-sm text-ink-soft dark:text-starlight">Advisory comparison from registered providers, the operator budget, and measured Antiek-bench evidence when available.</p>
      </div>
      <div className="grid gap-3 border-y border-ink/15 py-4 dark:border-bright/15 sm:grid-cols-3">
        <label className="text-xs font-semibold text-ink-soft dark:text-starlight">
          Task
          <select
            value={task}
            onChange={(event) => {
              invalidateDecision();
              setTask(event.target.value as ModelDecisionTask);
            }}
            className="mt-1 block h-10 w-full border border-ink/20 bg-transparent px-2 text-sm text-ink dark:border-bright/20 dark:text-bright"
          >
            {DECISION_TASKS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
          </select>
        </label>
        <label className="text-xs font-semibold text-ink-soft dark:text-starlight">
          Input characters
          <input type="number" min={0} value={inputChars} onChange={(event) => { invalidateDecision(); setInputChars(Number(event.target.value) || 0); }} className="mt-1 block h-10 w-full border border-ink/20 bg-transparent px-2 text-sm text-ink dark:border-bright/20 dark:text-bright" />
        </label>
        <label className="text-xs font-semibold text-ink-soft dark:text-starlight">
          Output tokens
          <input type="number" min={0} value={outputTokens} onChange={(event) => { invalidateDecision(); setOutputTokens(Number(event.target.value) || 0); }} className="mt-1 block h-10 w-full border border-ink/20 bg-transparent px-2 text-sm text-ink dark:border-bright/20 dark:text-bright" />
        </label>
      </div>
      <LemonButton type="button" variant="primary" size="md" disabled={loading} onClick={() => void compare()}>
        {loading ? "Comparing..." : "Compare models"}
      </LemonButton>
      {error && <p role="alert" className="text-sm text-red-700 dark:text-red-300">{error}</p>}
      {decision && (
        <div className="space-y-4">
          <div className="flex flex-wrap items-baseline justify-between gap-3 border-b border-ink/15 pb-3 dark:border-bright/15">
            <p className="text-sm text-ink dark:text-bright">
              Recommended tier: <strong>{decision.recommended_tier ?? "none available"}</strong>
            </p>
            <p className="font-mono text-xs text-ink-soft dark:text-starlight">
              {decision.benchmark_status === "measured" ? "Measured evidence" : "Static quality prior"}
            </p>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[680px] border-collapse text-left text-sm">
              <thead className="border-b-2 border-ink/70 text-xs text-ink-soft dark:border-bright/70 dark:text-starlight">
                <tr><th className="py-2 pr-3">Rank</th><th className="py-2 pr-3">Tier</th><th className="py-2 pr-3">Model</th><th className="py-2 pr-3">Quality</th><th className="py-2 pr-3">Estimate high</th><th className="py-2">Status</th></tr>
              </thead>
              <tbody>
                {decision.candidates.map((candidate) => (
                  <tr key={`${candidate.tier}:${candidate.provider}:${candidate.model}`} className="border-b border-ink/10 dark:border-bright/10">
                    <td className="py-3 pr-3 font-mono">{candidate.rank}</td>
                    <td className="py-3 pr-3 font-semibold">{candidate.tier}</td>
                    <td className="py-3 pr-3"><span className="block">{candidate.model}</span><span className="text-xs text-ink-soft dark:text-starlight">{candidate.provider}</span></td>
                    <td className="py-3 pr-3 font-mono">{candidate.quality_score.toFixed(2)} <span className="text-xs text-ink-soft dark:text-starlight">{candidate.quality_basis === "measured" ? `n=${candidate.benchmark_samples}` : "prior"}</span></td>
                    <td className="py-3 pr-3 font-mono">{candidate.estimated_usd_high == null ? "unknown" : `$${candidate.estimated_usd_high.toFixed(6)}`}</td>
                    <td className="py-3">
                      {!candidate.ready
                        ? "Unavailable"
                        : candidate.would_exceed_budget === true
                          ? "Over budget"
                          : candidate.would_exceed_budget === false
                            ? "Within budget"
                            : "Budget unknown"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {decision.notes.map((note) => <p key={note} className="text-xs text-ink-soft dark:text-starlight">{note}</p>)}
        </div>
      )}
    </section>
  );
}

function PasskeySettings() {
  const [passkeys, setPasskeys] = useState<SavedPasskey[] | null>(null);
  const [working, setWorking] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  async function refreshPasskeys() {
    try {
      setPasskeys(await listPasskeys());
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Couldn't load passkeys.");
    }
  }

  useEffect(() => {
    void refreshPasskeys();
  }, []);

  async function addPasskey() {
    setWorking(true);
    setMessage(null);
    try {
      const { ceremony_id, ...optionsJSON } = await beginPasskeyRegistration();
      const credential = await startRegistration({ optionsJSON });
      await finishPasskeyRegistration(ceremony_id, credential, "Personal passkey");
      setMessage("Passkey added. Your next unlock can use this device.");
      await refreshPasskeys();
    } catch (error) {
      if (!(error instanceof DOMException && error.name === "NotAllowedError")) {
        setMessage(error instanceof Error ? error.message : "Couldn't add that passkey.");
      }
    } finally {
      setWorking(false);
    }
  }

  async function forgetPasskey(passkey: SavedPasskey) {
    if (!window.confirm(`Forget “${passkey.label}”? Email recovery will still work.`)) return;
    setWorking(true);
    setMessage(null);
    try {
      await removePasskey(passkey.id);
      setMessage("Passkey forgotten.");
      await refreshPasskeys();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Couldn't remove that passkey.");
    } finally {
      setWorking(false);
    }
  }

  return (
    <LemonCard title="Unlock & recovery" elevation="z1" colour="glacial">
      <div className="p-4 space-y-4">
        <div>
          <p className="text-sm text-ink dark:text-bright font-semibold">Passkeys</p>
          <p className="text-xs text-ink-soft dark:text-starlight mt-1">
            Face ID, Touch ID, or your device PIN unlocks Antiek. Email stays available for recovery.
          </p>
        </div>
        {passkeys === null ? (
          <p className="text-xs text-ink-soft dark:text-starlight">Reading your devices…</p>
        ) : passkeys.length ? (
          <ul className="space-y-2">
            {passkeys.map((passkey) => (
              <li key={passkey.id} className="flex items-center justify-between gap-3 rounded-hog border border-rule dark:border-slate-2 bg-ice-0 dark:bg-charcoal-2 px-3 py-2">
                <span>
                  <strong className="block text-sm text-ink dark:text-bright">{passkey.label}</strong>
                  <small className="text-[11px] text-ink-soft dark:text-starlight">
                    {passkey.backed_up ? "Synced passkey" : "This-device passkey"}
                    {passkey.last_used_at ? ` · used ${new Date(passkey.last_used_at * 1000).toLocaleDateString()}` : ""}
                  </small>
                </span>
                <button type="button" disabled={working} onClick={() => void forgetPasskey(passkey)} className="text-xs font-semibold text-emperor underline underline-offset-4 disabled:opacity-50">
                  Forget
                </button>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-xs text-ink-soft dark:text-starlight">No passkey saved yet.</p>
        )}
        <LemonButton type="button" variant="secondary" size="md" disabled={working} onClick={() => void addPasskey()}>
          {working ? "Waiting for your device…" : "Add another passkey"}
        </LemonButton>
        {message && <p className="text-xs text-ink-soft dark:text-starlight" role="status">{message}</p>}
      </div>
    </LemonCard>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <span className="text-ink-soft dark:text-starlight uppercase tracking-wider text-[11px]">
        {label}
      </span>
      <span className="text-ink dark:text-bright">{value}</span>
    </div>
  );
}
