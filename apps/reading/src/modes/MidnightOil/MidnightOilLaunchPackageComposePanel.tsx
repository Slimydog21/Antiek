/**
 * MidnightOilLaunchPackageComposePanel - full unattended launch package.
 *
 * Free-file. live_execution_authorized always false.
 */

import { useState } from "react";
import { LemonButton, LemonCard, LemonInput } from "../../components/lemon";
import {
  composeMidnightOilLaunchPackage,
  formatMidnightOilLaunchPackageSummary,
  type MidnightOilLaunchPackage,
} from "../../api/midnightOilLaunchPackageCompose";

export interface MidnightOilLaunchPackageComposePanelProps {
  composeFn?: typeof composeMidnightOilLaunchPackage;
  initialOperatorId?: string;
}

export default function MidnightOilLaunchPackageComposePanel({
  composeFn = composeMidnightOilLaunchPackage,
  initialOperatorId = "op-1",
}: MidnightOilLaunchPackageComposePanelProps) {
  const [operatorId, setOperatorId] = useState(initialOperatorId);
  const [minutesRaw, setMinutesRaw] = useState("60");
  const [ceilingRaw, setCeilingRaw] = useState("15");
  const [rateRaw, setRateRaw] = useState("10");
  const [goalsRaw, setGoalsRaw] = useState(
    "g1|Map arxiv scaling|2\ng2|Substack contrast|1",
  );
  const [approved, setApproved] = useState(false);
  const [ack, setAck] = useState(false);
  const [consent, setConsent] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<MidnightOilLaunchPackage | null>(null);

  function parseOptionalMoney(raw: string): number | null {
    const t = raw.trim();
    if (!t) return null;
    const n = Number(t);
    if (!Number.isFinite(n)) {
      throw new Error("money field must be finite or blank");
    }
    return n;
  }

  function onCompose() {
    setError(null);
    setResult(null);
    try {
      const goals = goalsRaw
        .split(/\r?\n/)
        .map((line) => line.trim())
        .filter(Boolean)
        .map((line, i) => {
          const parts = line.split("|").map((p) => p.trim());
          if (parts.length < 2) {
            throw new Error(
              `goals line ${i + 1} must be goal_id|statement|priority`,
            );
          }
          return {
            goal_id: parts[0],
            statement: parts[1],
            priority: parts[2] ? Number(parts[2]) : 1,
          };
        });
      setResult(
        composeFn({
          operator_id: operatorId.trim(),
          work_minutes: Number(minutesRaw),
          goals,
          price_ceiling_usd: parseOptionalMoney(ceilingRaw),
          usd_per_hour: parseOptionalMoney(rateRaw),
          operator_approved: approved,
          unattended_ack: ack,
          spend_consent: consent,
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div data-testid="mo-launch-package-compose-panel">
      <LemonCard
        title="Midnight Oil launch package"
        className="mo-launch-package-compose-panel"
      >
        <p className="text-sm opacity-80" data-testid="molp-blurb">
          Set work window, goals, and approve a recommended price ceiling for
          unattended deep research. Pure package — live_execution_authorized
          stays false.
        </p>
        <div className="flex flex-col gap-3 mt-3">
          <label className="text-sm flex flex-col gap-1">
            <span>Operator id</span>
            <LemonInput
              value={operatorId}
              onChange={(e) => setOperatorId(e.target.value)}
              data-testid="molp-operator"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Work minutes</span>
            <LemonInput
              value={minutesRaw}
              onChange={(e) => setMinutesRaw(e.target.value)}
              data-testid="molp-minutes"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>USD per hour (blank = unknown recommend)</span>
            <LemonInput
              value={rateRaw}
              onChange={(e) => setRateRaw(e.target.value)}
              data-testid="molp-rate"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Price ceiling USD (blank = unknown)</span>
            <LemonInput
              value={ceilingRaw}
              onChange={(e) => setCeilingRaw(e.target.value)}
              data-testid="molp-ceiling"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Goals (goal_id|statement|priority per line)</span>
            <textarea
              value={goalsRaw}
              onChange={(e) => setGoalsRaw(e.target.value)}
              data-testid="molp-goals"
              className="border border-border rounded px-2 py-1 text-sm min-h-[4rem]"
            />
          </label>
          <label className="text-sm flex items-center gap-2">
            <input
              type="checkbox"
              checked={approved}
              onChange={(e) => setApproved(e.target.checked)}
              data-testid="molp-approved"
            />
            operator_approved (brief)
          </label>
          <label className="text-sm flex items-center gap-2">
            <input
              type="checkbox"
              checked={ack}
              onChange={(e) => setAck(e.target.checked)}
              data-testid="molp-ack"
            />
            unattended_ack
          </label>
          <label className="text-sm flex items-center gap-2">
            <input
              type="checkbox"
              checked={consent}
              onChange={(e) => setConsent(e.target.checked)}
              data-testid="molp-consent"
            />
            spend_consent
          </label>
          <LemonButton
            variant="primary"
            onClick={onCompose}
            data-testid="molp-compose"
          >
            Compose launch package
          </LemonButton>
          {error ? (
            <div className="text-sm text-danger" data-testid="molp-error">
              {error}
            </div>
          ) : null}
          {result ? (
            <div
              data-testid="molp-result"
              className="text-sm flex flex-col gap-1"
            >
              <div data-testid="molp-summary">
                {formatMidnightOilLaunchPackageSummary(result)}
              </div>
              <div data-testid="molp-ready">
                package_ready={String(result.package_ready)}
              </div>
              <div data-testid="molp-exec">
                live_execution_authorized=
                {String(result.live_execution_authorized)}
              </div>
              <div data-testid="molp-recommended">
                recommended=
                {result.recommend.recommended_ceiling_usd === null
                  ? "null"
                  : String(result.recommend.recommended_ceiling_usd)}
              </div>
            </div>
          ) : null}
        </div>
      </LemonCard>
    </div>
  );
}
