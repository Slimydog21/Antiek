/**
 * UsageBarPanel — operator budget/usage bar + prompt projection (advisory).
 *
 * Consumes POST /settings/usage-bar/project (PR #795). Does not spend or
 * dispatch. remaining / would_exceed / fraction_used null render as unknown.
 *
 * Mount from Settings/index.tsx when free (#770 currently owns it).
 */

import { useMemo, useState } from "react";
import { LemonButton, LemonCard, LemonInput } from "../../components/lemon";
import {
  formatFractionUsed,
  formatMoney,
  formatOverBudget,
  formatWouldExceed,
  projectUsageBar,
  type UsageBarProjectResponse,
} from "../../api/usageBar";

export interface UsageBarPanelProps {
  projectFn?: typeof projectUsageBar;
  initialCap?: number | null;
  initialSpent?: number | null;
  initialProjectionHigh?: number | null;
}

function parseOptionalNumber(raw: string): number | null {
  const t = raw.trim();
  if (!t) return null;
  const n = Number(t);
  return Number.isFinite(n) ? n : null;
}

export default function UsageBarPanel({
  projectFn = projectUsageBar,
  initialCap = null,
  initialSpent = null,
  initialProjectionHigh = null,
}: UsageBarPanelProps) {
  const [capRaw, setCapRaw] = useState(
    initialCap === null || initialCap === undefined ? "" : String(initialCap),
  );
  const [spentRaw, setSpentRaw] = useState(
    initialSpent === null || initialSpent === undefined ? "" : String(initialSpent),
  );
  const [projLowRaw, setProjLowRaw] = useState("");
  const [projHighRaw, setProjHighRaw] = useState(
    initialProjectionHigh === null || initialProjectionHigh === undefined
      ? ""
      : String(initialProjectionHigh),
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<UsageBarProjectResponse | null>(null);

  const cap = useMemo(() => parseOptionalNumber(capRaw), [capRaw]);
  const spent = useMemo(() => parseOptionalNumber(spentRaw), [spentRaw]);
  const projLow = useMemo(() => parseOptionalNumber(projLowRaw), [projLowRaw]);
  const projHigh = useMemo(() => parseOptionalNumber(projHighRaw), [projHighRaw]);

  async function onProject() {
    setBusy(true);
    setError(null);
    try {
      const body = await projectFn({
        daily_cap_usd: cap,
        spent_usd: spent,
        projected_cost_usd_low: projLow,
        projected_cost_usd_high: projHigh,
      });
      setResult(body);
    } catch (e) {
      setResult(null);
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  const bar = result?.usage_bar;
  const proj = result?.prompt_projection;

  return (
    <div data-testid="usage-bar-panel">
      <LemonCard title="Budget usage & prompt projection" className="usage-bar-panel">
        <p className="text-sm opacity-80" data-testid="usage-bar-blurb">
          Shows spend vs your cap and how a proposed prompt would affect remaining.
          Unknown values stay unknown — never invented as $0.
        </p>

        <div className="flex flex-col gap-3 mt-3">
          <label className="text-sm flex flex-col gap-1">
            <span>Daily cap USD (empty = unknown)</span>
            <LemonInput
              value={capRaw}
              onChange={(e) => setCapRaw(e.target.value)}
              placeholder="unknown"
              data-testid="usage-bar-cap"
              aria-label="Daily cap USD"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Spent / reserved USD (empty = unknown)</span>
            <LemonInput
              value={spentRaw}
              onChange={(e) => setSpentRaw(e.target.value)}
              placeholder="unknown"
              data-testid="usage-bar-spent"
              aria-label="Spent USD"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Proposed prompt cost high USD (optional)</span>
            <LemonInput
              value={projHighRaw}
              onChange={(e) => setProjHighRaw(e.target.value)}
              placeholder="optional"
              data-testid="usage-bar-proj-high"
              aria-label="Projected cost high USD"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Proposed prompt cost low USD (optional)</span>
            <LemonInput
              value={projLowRaw}
              onChange={(e) => setProjLowRaw(e.target.value)}
              placeholder="optional"
              data-testid="usage-bar-proj-low"
              aria-label="Projected cost low USD"
            />
          </label>

          <LemonButton
            variant="primary"
            disabled={busy}
            onClick={() => void onProject()}
            data-testid="usage-bar-project"
          >
            {busy ? "Computing…" : "Update usage bar"}
          </LemonButton>

          {error ? (
            <div className="text-sm text-danger" data-testid="usage-bar-error">
              {error}
            </div>
          ) : null}

          {bar ? (
            <div data-testid="usage-bar-result">
              <div data-testid="usage-bar-remaining">
                Remaining: {formatMoney(bar.remaining_usd)}
              </div>
              <div data-testid="usage-bar-spent-display">
                Spent: {formatMoney(bar.spent_usd)}
              </div>
              <div data-testid="usage-bar-cap-display">
                Cap: {formatMoney(bar.daily_cap_usd)}
              </div>
              <div data-testid="usage-bar-fraction">
                Used: {formatFractionUsed(bar.fraction_used)}
              </div>
              <div data-testid="usage-bar-over">
                Status: {formatOverBudget(bar.over_budget)}
              </div>
              {proj ? (
                <div className="mt-2" data-testid="usage-bar-projection">
                  <div data-testid="usage-bar-would-exceed">
                    Prompt effect: {formatWouldExceed(proj.would_exceed)}
                  </div>
                  <div data-testid="usage-bar-after-high">
                    Remaining after high: {formatMoney(proj.remaining_after_high_usd)}
                  </div>
                </div>
              ) : null}
            </div>
          ) : null}
        </div>
      </LemonCard>
    </div>
  );
}
