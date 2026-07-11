import { startRegistration } from "@simplewebauthn/browser";
import { useEffect, useMemo, useState } from "react";
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
  fetchSettingsBudget,
  fetchSettingsModels,
  type BudgetResponse,
  type ModelRow,
  type PromptCostEstimateResponse,
} from "../../api/settings";
import {
  budgetStatusText,
  dualCapNote,
  formatRemaining,
  formatSpendAmount,
  spendAmountLabel,
  spendBasisNote,
  spendPct as computeSpendPct,
} from "./budgetHonesty";

/**
 * Operator Settings — model inventory + budget + prompt projection (SPR-01).
 *
 * Honesty: spent/pricing may be unknown; UI never invents $0.00 when the
 * ledger or rate table is unset. Reserved estimates are labeled as such
 * (not settled spend); display vs enforcement caps surface when they diverge.
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

  const spendPct = useMemo(
    () => (budget ? computeSpendPct(budget) : null),
    [budget],
  );
  const budgetStatus = budget ? budgetStatusText(budget) : "spend unknown";
  const dualCap = budget ? dualCapNote(budget) : null;
  const reservedNote = budget ? spendBasisNote(budget) : null;

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
    } catch (e) {
      setEstimateError(e instanceof Error ? e.message : String(e));
    } finally {
      setEstimating(false);
    }
  }

  return (
    <div className="h-full overflow-y-auto bg-ice-2 dark:bg-space-2">
      <div className="max-w-3xl mx-auto px-6 py-8 space-y-6">
        <header>
          <h1 className="text-2xl font-serif text-ink dark:text-bright">
            Operator settings
          </h1>
          <p className="text-sm text-ink-soft dark:text-starlight font-serif italic mt-1">
            Models, budget ceiling, and prompt cost projection. Numbers over
            placeholders — unknown spend stays unknown.
          </p>
        </header>

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
                      {m.ready ? "ready" : "not registered"}
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
              Adding API keys / new models lands in SPR-02. Decision-tree
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
                    label="Display cap"
                    value={
                      budget.daily_cap_usd == null
                        ? "unset"
                        : `$${budget.daily_cap_usd.toFixed(2)}`
                    }
                  />
                  <Row
                    label={spendAmountLabel(budget)}
                    value={formatSpendAmount(budget)}
                  />
                  <Row label="Remaining" value={formatRemaining(budget)} />
                  {budget.cap_env && (
                    <Row label="Display cap source" value={budget.cap_env} />
                  )}
                  {budget.caps_aligned === false &&
                    budget.enforcement_cap_usd != null && (
                      <Row
                        label="Enforcement cap"
                        value={`$${budget.enforcement_cap_usd.toFixed(2)}${
                          budget.enforcement_cap_env
                            ? ` (${budget.enforcement_cap_env})`
                            : " (daemon default)"
                        }`}
                      />
                    )}
                </div>
                <div
                  className="h-2 w-full rounded-full bg-ink/10 dark:bg-bright/10 overflow-hidden"
                  role="progressbar"
                  aria-valuemin={0}
                  aria-valuemax={100}
                  aria-valuenow={spendPct ?? 0}
                  aria-label={`Budget usage: ${budgetStatus}`}
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
                <p
                  className="text-[11px] text-ink-soft dark:text-starlight"
                  aria-live="polite"
                >
                  Budget status: {budgetStatus}.
                </p>
                {reservedNote && (
                  <p
                    className="text-[11px] text-ink-soft dark:text-starlight"
                    data-testid="spend-basis-note"
                  >
                    {reservedNote}
                  </p>
                )}
                {dualCap && (
                  <p
                    className="text-[11px] text-amber-800 dark:text-amber-200"
                    data-testid="dual-cap-note"
                  >
                    {dualCap}
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

        <LemonCard title="Coming later" elevation="z1">
          <ul className="p-4 space-y-2 text-sm text-ink dark:text-bright list-disc list-inside">
            <li>Add model + multi-provider secret vault (SPR-02)</li>
            <li>Decision-tree per-prompt model override (SPR-03)</li>
            <li>Antiek-bench weekly model quality report</li>
            <li>Midnight oil: time + goals + price-ceiling approve UI</li>
            <li>Keyboard map customisation + layout export</li>
          </ul>
        </LemonCard>
      </div>
    </div>
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
