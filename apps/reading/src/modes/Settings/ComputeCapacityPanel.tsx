/**
 * ComputeCapacityPanel — Antiek-hosted agent compute capacity slider.
 *
 * BYO Token spend lives in UsagePanel. This panel is the managed-CPU
 * monthly ACU budget (predictable bill). No BYO CPU by default; used
 * stays unmetered until a real meter exists — never invents usage.
 */
import { useCallback, useEffect, useState } from "react";
import LemonCard from "../../components/lemon/LemonCard";
import { LemonButton } from "../../components/lemon";
import {
  fetchComputeCapacity,
  setComputeCapacity,
  type ComputeCapacityResponse,
  type ComputeCapacityTier,
} from "../../api/settingsComputeCapacity";

const TIER_LABELS: Record<ComputeCapacityTier, string> = {
  starter: "Starter (100 ACU)",
  standard: "Standard (500 ACU)",
  power: "Power (2000 ACU)",
  custom: "Custom",
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
          billing; usage unmetered until a meter ships.
        </p>
      </div>

      {error ? (
        <p className="text-sm text-rose-700 dark:text-rose-300" role="alert">
          {error}
        </p>
      ) : null}

      {cap ? (
        <>
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
