import { useState } from "react";

import type {
  Claim,
  ClaimChallengeRaisedPayload,
  ConfidenceLevel,
} from "../generated/types";
import { postTypedEvent } from "../lib/api";
import { emitWernerExperience } from "../werner/reactionBus";

/**
 * The derived grounding state for a single Claim, computed by the
 * parent (NotesPanel) by scanning the event stream for
 * ``claim.grounding_check_passed`` / ``_failed`` events that
 * reference this claim's ``claim_id``.
 *
 * ``null`` means no grounding check has been requested or returned
 * yet. The card renders no status badge in that case.
 */
export type GroundingStatus =
  | {
      result: "passed";
      located_region_id: string;
      confidence: number;
      eventId: string;
    }
  | {
      result: "failed";
      reason: "absent_from_source" | "paraphrased_not_stated" | "out_of_scope" | "ambiguous";
      searched_regions: string[];
      eventId: string;
    }
  | { result: "pending"; eventId: string }
  | null;

interface ClaimCardProps {
  claim: Claim;
  investigationId: string;
  documentId: string;
  /** Optional derived grounding result for this claim. Renders below
   *  the claim text when set. */
  grounding?: GroundingStatus;
  /** Called when the operator clicks the "↪ region" affordance on a
   *  passed status. Future hookup: scroll the PdfViewer to the
   *  located region. */
  onLocateRegion?: (regionId: string) => void;
}

// Default challenge prompt sent when the user clicks "challenge". A
// future iteration will pop a modal asking the user for the specific
// challenge text; for Sprint 2 we ship the default so the round-trip
// works end-to-end.
const DEFAULT_CHALLENGE_PROMPT =
  "Is this claim well-grounded? Show me the source passage that supports it, " +
  "and flag anywhere the source is weaker than the claim implies.";

export default function ClaimCard({
  claim,
  investigationId,
  documentId,
  grounding,
  onLocateRegion,
}: ClaimCardProps) {
  const [busy, setBusy] = useState(false);
  const [challenged, setChallenged] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onChallenge() {
    setBusy(true);
    setError(null);
    const payload: ClaimChallengeRaisedPayload = {
      action_type: "claim.challenge_raised",
      challenged_claim_id: claim.claim_id,
      claim_text: claim.text,
      anchor_region_id: claim.attribution_region_ids[0] ?? null,
      user_question: DEFAULT_CHALLENGE_PROMPT,
    };
    try {
      await postTypedEvent({
        investigation_id: investigationId,
        document_id: documentId,
        payload,
        role: "user_agent",
      });
      setChallenged(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="border border-rule dark:border-charcoal-1 rounded-md bg-ice-0 dark:bg-charcoal-2 px-3 py-2.5 flex flex-col gap-1.5">
      <div className="flex items-start justify-between gap-2">
        <p className="text-sm text-ink dark:text-bright leading-snug flex-1">
          {claim.text}
        </p>
        <ConfidenceBadge level={claim.confidence} />
      </div>
      {claim.attribution_region_ids.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {claim.attribution_region_ids.map((rid) => (
            <span
              key={rid}
              className="text-[10px] font-mono text-shadow-1 dark:text-moonlight bg-ice-3 dark:bg-charcoal-1 px-1.5 py-0.5 rounded"
              title={rid}
            >
              ↳ {shortenRegionId(rid)}
            </span>
          ))}
        </div>
      )}
      <div className="flex items-center gap-2 pt-0.5">
        <button
          onClick={onChallenge}
          disabled={busy || challenged}
          className="text-[11px] px-2 py-0.5 rounded border border-rule dark:border-charcoal-1 text-ink dark:text-bright hover:bg-ice-3 dark:bg-charcoal-1 disabled:text-ink-mute dark:text-moonlight disabled:cursor-not-allowed transition-colors"
        >
          {challenged ? "challenged" : busy ? "…" : "challenge this claim"}
        </button>
        <button
          type="button"
          onClick={() => {
            // S7 acceptance — "Add to notebook" from ClaimCard.
            // Lazy-import the workspace action so the bundle doesn't
            // bring TipTap into the main chunk via ClaimCard.
            import("../workspace/actions").then(({ openNotebook }) => {
              openNotebook({
                kind: "NotebookEditor",
                mode: "floating",
                notebookId: `claim-${claim.claim_id}`,
                title: "Add to notebook",
              });
            });
          }}
          className="text-[11px] px-2 py-0.5 rounded border border-rule dark:border-charcoal-1 text-ink dark:text-bright hover:bg-sun/15 dark:hover:bg-sun/10 transition-colors"
        >
          add to notebook
        </button>
        <button
          type="button"
          onClick={() => {
            // S6 WP-6.3 acceptance — "Clicking a claim chip opens it
            // as a floating panel near the cursor. Two claims can be
            // inspected at once — the operator drags one aside."
            import("../workspace/actions").then(({ openClaimInspector }) => {
              openClaimInspector({
                claimId: claim.claim_id,
                investigationId,
                documentId,
              });
            });
          }}
          className="text-[11px] px-2 py-0.5 rounded border border-rule dark:border-charcoal-1 text-ink dark:text-bright hover:bg-sun/15 dark:hover:bg-sun/10 transition-colors"
          title="Open as floating inspector panel"
        >
          inspect
        </button>
        {error && (
          <span className="text-[10px] font-mono text-emperor">{error}</span>
        )}
      </div>
      {grounding && (
        <GroundingBadge grounding={grounding} onLocateRegion={onLocateRegion} />
      )}
    </div>
  );
}


/**
 * Renders the grounder's verdict inline on the claim card.
 *
 * - Passed → green ✓ with the located region as a clickable chip
 *   that calls ``onLocateRegion`` (future: PdfViewer scroll-to).
 * - Failed → amber/red ⚠ with the failure reason + searched-region
 *   count for transparency.
 * - Pending → neutral spinner until the verdict event arrives.
 */
function GroundingBadge({
  grounding,
  onLocateRegion,
}: {
  grounding: NonNullable<GroundingStatus>;
  onLocateRegion?: (regionId: string) => void;
}) {
  if (grounding.result === "pending") {
    return (
      <div className="text-[11px] font-mono text-shadow-1 dark:text-moonlight italic flex items-center gap-1.5 mt-0.5">
        <span className="inline-block h-2 w-2 rounded-full bg-amber-400 animate-pulse" />
        grounding check in flight…
      </div>
    );
  }

  if (grounding.result === "passed") {
    const conf = Math.round(grounding.confidence * 100);
    return (
      <div className="text-[11px] font-mono flex items-center gap-1.5 mt-0.5 text-emerald-700">
        <span>✓ grounded</span>
        <span className="text-shadow-1 dark:text-moonlight">·</span>
        <button
          onClick={() => onLocateRegion?.(grounding.located_region_id)}
          className="px-1.5 py-0.5 rounded bg-emerald-50 border border-emerald-200 hover:bg-emerald-100 transition-colors text-emerald-800"
          title={`open region ${grounding.located_region_id} in viewer`}
        >
          ↪ {shortenRegionId(grounding.located_region_id)}
        </button>
        <span className="text-ink-mute dark:text-moonlight">· {conf}%</span>
      </div>
    );
  }

  // result === "failed"
  const tone = grounding.reason === "ambiguous" ? "amber" : "red";
  const reasonStyles: Record<typeof tone, string> = {
    red: "text-emperor bg-red-50 border-red-200",
    amber: "text-sun-deep dark:text-sun bg-sun/10 border-amber-200",
  };
  const reasonLabels: Record<typeof grounding.reason, string> = {
    absent_from_source: "not in source",
    paraphrased_not_stated: "paraphrase, not stated",
    out_of_scope: "out of scope",
    ambiguous: "ambiguous",
  };
  return (
    <div className="text-[11px] font-mono flex items-center gap-1.5 mt-0.5">
      <span className={tone === "red" ? "text-emperor" : "text-sun-deep dark:text-sun"}>⚠ not located</span>
      <span className="text-shadow-1 dark:text-moonlight">·</span>
      <span className={`px-1.5 py-0.5 rounded border ${reasonStyles[tone]}`}>
        {reasonLabels[grounding.reason]}
      </span>
      <span className="text-ink-mute dark:text-moonlight">
        · searched {grounding.searched_regions.length} region
        {grounding.searched_regions.length === 1 ? "" : "s"}
      </span>
    </div>
  );
}

function ConfidenceBadge({ level }: { level: ConfidenceLevel }) {
  const styles: Record<ConfidenceLevel, string> = {
    high: "bg-emerald-100 text-emerald-800",
    moderate: "bg-sun/20 text-amber-800",
    low: "bg-orange-100 text-orange-800",
    unknown: "bg-ice-4 dark:bg-charcoal-1 text-ink-soft dark:text-starlight",
  };
  return (
    <span
      className={`text-[10px] font-mono px-1.5 py-0.5 rounded uppercase tracking-wide ${styles[level]}`}
    >
      {level}
    </span>
  );
}

function shortenRegionId(rid: string): string {
  // region_id format: r-<12hex>-<base36 timestamp>
  return rid.length > 14 ? rid.slice(0, 14) : rid;
}
