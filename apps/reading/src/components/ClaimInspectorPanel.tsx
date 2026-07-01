import type { Claim } from "../generated/types";
import ClaimCard from "./ClaimCard";

type Props = {
  claim?: Claim;
  claimId?: string;
  investigationId?: string;
  documentId?: string;
};

export default function ClaimInspectorPanel({
  claim,
  claimId,
  investigationId,
  documentId,
}: Props) {
  if (claim && investigationId && documentId) {
    return (
      <ClaimCard
        claim={claim}
        investigationId={investigationId}
        documentId={documentId}
      />
    );
  }

  return (
    <div className="h-full flex flex-col gap-2 bg-ice-0 dark:bg-charcoal-2 p-4 text-sm text-ink dark:text-bright">
      <p className="font-serif text-base">Claim details are not loaded here.</p>
      <p className="text-[12px] text-ink-soft dark:text-starlight">
        This panel has a claim reference, but not the full claim payload needed
        for challenge and grounding controls.
      </p>
      {claimId && (
        <p className="font-mono text-[11px] text-shadow-1 dark:text-moonlight">
          claim_id: {claimId}
        </p>
      )}
    </div>
  );
}
