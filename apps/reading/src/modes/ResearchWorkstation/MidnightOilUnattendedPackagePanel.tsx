/**
 * MidnightOilUnattendedPackagePanel — full unattended MO package UI.
 *
 * Free-file. live_execution_authorized always false.
 */

import { useState } from "react";
import { LemonButton, LemonCard, LemonInput } from "../../components/lemon";
import {
  composeMidnightOilUnattendedPackage,
  formatMidnightOilUnattendedPackageSummary,
  type MidnightOilUnattendedPackageCompose,
} from "../../api/midnightOilUnattendedPackageCompose";

export interface MidnightOilUnattendedPackagePanelProps {
  composeFn?: typeof composeMidnightOilUnattendedPackage;
}

export default function MidnightOilUnattendedPackagePanel({
  composeFn = composeMidnightOilUnattendedPackage,
}: MidnightOilUnattendedPackagePanelProps) {
  const [operatorId, setOperatorId] = useState("op-1");
  const [minutes, setMinutes] = useState("120");
  const [ceiling, setCeiling] = useState("40");
  const [ack, setAck] = useState(true);
  const [unattended, setUnattended] = useState(true);
  const [consent, setConsent] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<MidnightOilUnattendedPackageCompose | null>(null);

  function onCompose() {
    setError(null);
    setResult(null);
    try {
      setResult(
        composeFn({
          operator_id: operatorId.trim(),
          work_minutes: Number(minutes),
          goals: [
            { goal_id: "g1", title: "Survey arxiv" },
            { goal_id: "g2", title: "Draft notes" },
          ],
          usd_per_hour: 15,
          approved_ceiling_usd: ceiling.trim() ? Number(ceiling) : null,
          operator_ack: ack,
          unattended_ack: unattended,
          spend_consent: consent,
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div data-testid="mo-unattended-package-panel">
      <LemonCard
        title="Midnight Oil · unattended full package"
        className="mo-unattended-package-panel"
      >
        <p className="text-sm opacity-80" data-testid="mouap-blurb">
          Time + goals + price ceiling entry, launch brief, and unattended
          readiness in one pure package. Never launches workers.
        </p>
        <div className="flex flex-col gap-2 mt-3">
          <label className="text-sm flex flex-col gap-1">
            <span>Operator</span>
            <LemonInput
              value={operatorId}
              onChange={(e) => setOperatorId(e.target.value)}
              data-testid="mouap-op"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Work minutes</span>
            <LemonInput
              value={minutes}
              onChange={(e) => setMinutes(e.target.value)}
              data-testid="mouap-minutes"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Approved ceiling USD</span>
            <LemonInput
              value={ceiling}
              onChange={(e) => setCeiling(e.target.value)}
              data-testid="mouap-ceiling"
            />
          </label>
          <label className="text-sm flex items-center gap-2">
            <input
              type="checkbox"
              checked={ack}
              onChange={(e) => setAck(e.target.checked)}
              data-testid="mouap-ack"
            />
            <span>operator_ack</span>
          </label>
          <label className="text-sm flex items-center gap-2">
            <input
              type="checkbox"
              checked={unattended}
              onChange={(e) => setUnattended(e.target.checked)}
              data-testid="mouap-unattended"
            />
            <span>unattended_ack</span>
          </label>
          <label className="text-sm flex items-center gap-2">
            <input
              type="checkbox"
              checked={consent}
              onChange={(e) => setConsent(e.target.checked)}
              data-testid="mouap-consent"
            />
            <span>spend_consent</span>
          </label>
          <LemonButton
            variant="primary"
            onClick={onCompose}
            data-testid="mouap-compose"
          >
            Compose unattended package
          </LemonButton>
          {error ? (
            <p className="text-sm text-danger" data-testid="mouap-error">
              {error}
            </p>
          ) : null}
          {result ? (
            <div
              className="text-sm flex flex-col gap-1 mt-2"
              data-testid="mouap-result"
            >
              <div data-testid="mouap-ready">
                unattended_package_ready=
                {String(result.unattended_package_ready)}
              </div>
              <div data-testid="mouap-live">
                live_execution_authorized=
                {String(result.live_execution_authorized)}
              </div>
              <div data-testid="mouap-summary">
                {formatMidnightOilUnattendedPackageSummary(result)}
              </div>
            </div>
          ) : null}
        </div>
      </LemonCard>
    </div>
  );
}
