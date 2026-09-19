import { useCallback, useEffect, useLayoutEffect, useState } from "react";

import {
  ResearchLaunchBudgetPanel,
  type ResearchLaunchBudgetProjection,
  type ResearchLaunchTier,
} from "./ResearchLaunchBudgetPanel";

export type ResearchRunAuthorization = {
  approved: boolean;
  ceilingUsd: number | null;
  projection: ResearchLaunchBudgetProjection | null;
};

type Props = {
  promptText: string;
  researchTier: ResearchLaunchTier;
  disabled?: boolean;
  allowTierPick?: boolean;
  onResearchTierChange?: (tier: ResearchLaunchTier) => void;
  onAuthorizationChange: (authorization: ResearchRunAuthorization) => void;
  className?: string;
};

/**
 * One intentionally boring consent control for every interactive Loop One
 * launch. Projection is informative; the operator-entered ceiling is the
 * durable server-enforced authority. Unknown pricing cannot be approved.
 */
export function ResearchRunCeilingApproval({
  promptText,
  researchTier,
  disabled = false,
  allowTierPick = false,
  onResearchTierChange,
  onAuthorizationChange,
  className = "",
}: Props) {
  const [projection, setProjection] =
    useState<ResearchLaunchBudgetProjection | null>(null);
  const [ceilingText, setCeilingText] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [confirmedPricingFingerprint, setConfirmedPricingFingerprint] =
    useState<string | null>(null);
  const ceiling = Number(ceilingText);
  const ceilingValid =
    Number.isFinite(ceiling) && ceiling >= 0.01 && ceiling <= 100;
  const projectionReady =
    projection?.pricingKnown === true &&
    typeof projection.pricingFingerprint === "string" &&
    projection.pricingFingerprint.length > 0;
  const approved =
    confirmed &&
    ceilingValid &&
    projectionReady &&
    confirmedPricingFingerprint === projection?.pricingFingerprint;

  const invalidateQuote = useCallback(() => {
    setConfirmed(false);
    setConfirmedPricingFingerprint(null);
  }, []);

  useLayoutEffect(() => {
    // Consent binds the exact prompt/tier projection identity. A changed
    // command must return to unapproved before paint and before a fresh
    // projection callback can arrive.
    invalidateQuote();
    setProjection(null);
  }, [promptText, researchTier, invalidateQuote]);

  useEffect(() => {
    onAuthorizationChange({
      approved,
      ceilingUsd: ceilingValid ? ceiling : null,
      projection,
    });
  }, [approved, ceiling, ceilingValid, onAuthorizationChange, projection]);

  const onProjectionChange = useCallback(
    (next: ResearchLaunchBudgetProjection) => {
      setProjection(next);
      if (
        !next.pricingKnown ||
        !next.pricingFingerprint ||
        (confirmedPricingFingerprint !== null &&
          confirmedPricingFingerprint !== next.pricingFingerprint)
      ) {
        invalidateQuote();
      }
    },
    [confirmedPricingFingerprint, invalidateQuote],
  );

  return (
    <div className={`space-y-2 ${className}`} data-testid="research-run-authorization">
      <ResearchLaunchBudgetPanel
        promptText={promptText}
        researchTier={researchTier}
        allowTierPick={allowTierPick}
        onResearchTierChange={onResearchTierChange}
        onProjectionChange={onProjectionChange}
      />
      <div className="border border-rule p-3 text-[11px] font-mono space-y-2">
        <label className="block">
          Initial-run hard ceiling (USD)
          <input
            aria-label="Initial-run hard ceiling (USD)"
            type="number"
            min="0.01"
            max="100"
            step="0.01"
            value={ceilingText}
            disabled={disabled}
            onChange={(event) => {
              setCeilingText(event.target.value);
              invalidateQuote();
            }}
            className="ml-2 w-24 border border-ink bg-transparent px-2 py-1"
          />
        </label>
        <p className="text-ink-mute">
          {projectionReady
            ? "This separately caps paid calls in the initial research run. Launch obtains a short-lived server-signed quote for the exact final command before it can start."
            : "Exact route pricing is unavailable. Launch stays disabled until pricing authority is configured."}
        </p>
        <label className="flex gap-2">
          <input
            aria-label="Approve initial-run hard ceiling"
            type="checkbox"
            checked={confirmed}
            disabled={disabled || !ceilingValid || !projectionReady}
            onChange={(event) => {
              setConfirmed(event.target.checked);
              setConfirmedPricingFingerprint(
                event.target.checked ? projection?.pricingFingerprint ?? null : null,
              );
            }}
          />
          Approve this initial-run hard ceiling
        </label>
      </div>
    </div>
  );
}

export default ResearchRunCeilingApproval;
