/**
 * ComputeCapacityPanel — Antiek-hosted agent compute capacity slider.
 *
 * BYO Token spend lives in UsagePanel. This panel is the managed-CPU
 * monthly ACU budget. Metered used ACU shows when used_status=known.
 * No fake billing — numbers come from GET /settings/compute-capacity only.
 */
import { useCallback, useEffect, useState } from "react";
import LemonCard from "../../components/lemon/LemonCard";
import { LemonButton } from "../../components/lemon";
import {
  fetchComputeCapacity,
  setComputeCapacity,
  type ComputeCapacityResponse,
  type ComputeCapacityTier,
  type ComputeEnforcement,
} from "../../api/settingsComputeCapacity";

const TIER_LABELS: Record<ComputeCapacityTier, string> = {
  starter: "Starter (100 ACU)",
  standard: "Standard (500 ACU)",
  power: "Power (2000 ACU)",
  custom: "Custom",
};

const ENFORCEMENT_LABELS: Record<ComputeEnforcement, string> = {
  off: "Off — meter only, starts never refused",
  soft: "Soft — warn near/over capacity; starts still allowed",
  hard: "Hard — refuse new starts when used ≥ monthly ACU",
};

export default function ComputeCapacityPanel() {
  const [cap, setCap] = useState<ComputeCapacityResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [slider, setSlider] = useState(500);

  const load = useCallback(async () => {
    try {
      const next = await fetchComputeCapacity();
      setCap(next);
      setSlider(next.monthly_compute_units);
      setError(null);
    } catch {
      setError("Could not load compute capacity.");
      setCap(null);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function applyTier(tier: ComputeCapacityTier) {
    setSaving(true);
    try {
      const next = await setComputeCapacity({
        tier,
        monthly_compute_units: tier === "custom" ? slider : null,
      });
      setCap(next);
      setSlider(next.monthly_compute_units);
      setError(null);
    } catch {
      setError("Could not save capacity.");
    } finally {
      setSaving(false);
    }
  }

  async function applySlider() {
    setSaving(true);
    try {
      const next = await setComputeCapacity({
        tier: "custom",
        monthly_compute_units: slider,
      });
      setCap(next);
      setError(null);
    } catch {
      setError("Could not save capacity.");
    } finally {
      setSaving(false);
    }
  }

  const used =
    cap && cap.used_status === "known" && cap.used_compute_units != null
      ? cap.used_compute_units
      : null;
  const monthly = cap?.monthly_compute_units ?? 0;
  const usedPct =
    used != null && monthly > 0
      ? Math.min(100, Math.round((used / monthly) * 100))
      : null;
  const softOver = Boolean(cap?.evaluation?.soft_over);
  const wouldHardBlock = Boolean(cap?.evaluation?.would_hard_block);
  const enforcement = cap?.enforcement ?? "off";

  return (
    <div data-testid="compute-capacity-panel">
    <LemonCard className="space-y-3 p-4">
      <div>
        <h2 className="font-serif text-lg text-ink dark:text-bright">
          Agent compute capacity
        </h2>
        <p className="text-sm text-ink-mute dark:text-moonlight mt-1">
          Antiek-hosted agent CPU (ACU / month). BYO Token keys stay in Usage
          above — this slider is managed compute, not LLM cents. No fake
          billing; used ACU is shown only when the meter has recorded starts
          or wall-time top-ups.
        </p>
      </div>

      {error ? (
        <p className="text-sm text-rose-700 dark:text-rose-300" role="alert">
          {error}
        </p>
      ) : null}

      {cap ? (
        <>
          <div
            data-testid="compute-capacity-usage"
            className="rounded-md border border-rule/60 dark:border-shadow-2/40 px-3 py-2 space-y-1.5"
          >
            <div className="flex justify-between text-xs font-mono uppercase tracking-wider text-ink-mute dark:text-moonlight">
              <span>Used this month</span>
              <span data-testid="compute-capacity-used-label">
                {used != null
                  ? used + " / " + monthly + " ACU (" + usedPct + "%)"
                  : "unmetered (no starts recorded yet)"}
              </span>
            </div>
            {usedPct != null ? (
              <div className="h-2 w-full overflow-hidden rounded bg-ice-2 dark:bg-shadow-2">
                <div
                  data-testid="compute-capacity-used-bar"
                  className={
                    wouldHardBlock
                      ? "h-full bg-rose-500"
                      : softOver || usedPct >= 80
                        ? "h-full bg-amber-500"
                        : "h-full bg-accent"
                  }
                  style={{ width: usedPct + "%" }}
                />
              </div>
            ) : null}
            {wouldHardBlock ? (
              <p
                role="alert"
                data-testid="compute-capacity-hard-block"
                className="text-xs text-rose-800 dark:text-rose-200"
              >
                At or over monthly capacity with hard enforcement — new
                research starts are refused (HTTP 429) until you raise the ACU
                limit or usage resets. BYO Token spend is separate.
              </p>
            ) : softOver ? (
              <p
                role="status"
                data-testid="compute-capacity-soft-over"
                className="text-xs text-amber-800 dark:text-amber-200"
              >
                Near or over monthly capacity — soft warn on new research starts.
                {enforcement === "hard"
                  ? " Hard refuse applies once used ≥ monthly ACU."
                  : " Starts still allowed."}{" "}
                BYO Token spend is separate.
              </p>
            ) : null}
            <p
              data-testid="compute-capacity-metering-note"
              className="text-xs text-ink-mute dark:text-moonlight"
            >
              Metering: 1 ACU per investigation start, plus wall-time top-up
              after long runs (300s quantum, capped). Not LLM token cents.
            </p>
          </div>

          <div
            data-testid="compute-capacity-enforcement"
            className="rounded-md border border-rule/60 dark:border-shadow-2/40 px-3 py-2 space-y-1"
          >
            <div className="text-xs font-mono uppercase tracking-wider text-ink-mute dark:text-moonlight">
              Enforcement
            </div>
            <p className="text-sm text-ink dark:text-bright">
              {ENFORCEMENT_LABELS[enforcement]}
            </p>
            <p className="text-xs text-ink-mute dark:text-moonlight">
              Mode is set by the operator env (
              <span className="font-mono">ANTIEK_COMPUTE_CAPACITY_ENFORCEMENT</span>
              ); this panel does not flip it. Current:{" "}
              <span className="font-mono">{enforcement}</span>.
            </p>
          </div>

          <div className="flex flex-wrap gap-2" role="group" aria-label="Capacity tiers">
            {(["starter", "standard", "power"] as const).map((tier) => (
              <LemonButton
                key={tier}
                size="sm"
                variant={cap.tier === tier ? "primary" : "tertiary"}
                disabled={saving}
                onClick={() => void applyTier(tier)}
              >
                {TIER_LABELS[tier]}
              </LemonButton>
            ))}
          </div>

          <label className="block space-y-1">
            <span className="text-xs font-mono uppercase tracking-wider text-ink-mute dark:text-moonlight">
              Monthly ACU ({slider})
            </span>
            <input
              type="range"
              min={0}
              max={10000}
              step={50}
              value={slider}
              disabled={saving}
              aria-label="Monthly agent compute units"
              data-testid="compute-capacity-slider"
              className="w-full"
              onChange={(e) => setSlider(Number(e.target.value))}
            />
          </label>

          <div className="flex items-center gap-2">
            <LemonButton
              size="sm"
              variant="secondary"
              disabled={saving || slider === cap.monthly_compute_units}
              onClick={() => void applySlider()}
            >
              Save custom
            </LemonButton>
            <span className="text-xs text-ink-mute dark:text-moonlight">
              tier={cap.tier} · used={cap.used_status} · enforce={cap.enforcement}
              {cap.is_default ? " · default" : ""}
            </span>
          </div>
        </>
      ) : !error ? (
        <p className="text-sm text-ink-mute dark:text-moonlight">Loading…</p>
      ) : null}
    </LemonCard>
    </div>
  );
}
