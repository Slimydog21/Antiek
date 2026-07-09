/**
 * Residual (jj): shared Settings depth-tier → researchTier for FloatMenu hosts.
 *
 * HighlightToolbar / Reading FloatMenu / BlockDetail open deep research without
 * an on-page budget panel. They still need the operator's durable Settings
 * depth preference so launchFloatingDeepResearch records the same closed tier
 * as ResearchThis / Write / Marketplace (parity ji).
 *
 * Default researchTier is "deep" until fetch settles (or on error / unset).
 */

import { useEffect, useState } from "react";

import { fetchDepthTiers } from "../api/settings";
import type { ResearchTier } from "./api";
import { mapDepthTierToResearchTier } from "./researchTier";

export type DepthPrefillState = "pending" | "installed" | "none" | "error";

export type SettingsResearchTierState = {
  researchTier: ResearchTier;
  depthPrefill: DepthPrefillState;
};

const DEFAULT_TIER: ResearchTier = "deep";

/**
 * Prefill researchTier from GET /settings/depth-tier (flash|pro|wrestle →
 * fast|deep|wrestle). Offline-honest: fetch failure → depthPrefill "error",
 * keep default deep.
 */
export function useSettingsResearchTier(
  defaultTier: ResearchTier = DEFAULT_TIER,
): SettingsResearchTierState {
  const [researchTier, setResearchTier] = useState<ResearchTier>(defaultTier);
  const [depthPrefill, setDepthPrefill] =
    useState<DepthPrefillState>("pending");

  useEffect(() => {
    let cancelled = false;
    void fetchDepthTiers()
      .then((resp) => {
        if (cancelled) return;
        const mapped = mapDepthTierToResearchTier(resp.active_depth_tier);
        if (mapped) {
          setResearchTier(mapped);
          setDepthPrefill("installed");
        } else {
          setDepthPrefill("none");
        }
      })
      .catch(() => {
        if (!cancelled) setDepthPrefill("error");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return { researchTier, depthPrefill };
}
