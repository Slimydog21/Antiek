/**
 * researchSuggestion — the suggest-NOT-autoship bridge from a meta-reading
 * asset into a related Research investigation (Read SPR-08 M4).
 *
 * THE INVARIANT (operator decision 2 + out-of-scope list): promoting a Read
 * asset into Research is NEVER automatic. This module computes a SUGGESTION the
 * surface offers; the promotion only happens when the user EXPLICITLY accepts.
 * `acceptPromotion` is the only function that mutates anything, and it is wired
 * to a user click — never called on render, never on generate.
 *
 * It reuses the EXISTING seam (`seam.read_to_research`, the `document_region`
 * handoff) via the typed-event funnel — promotion is not a new silo and the
 * one-graph invariant is untouched. The launched investigation id is recorded
 * on the seam event so the asset can link to what it spawned.
 */

import { postTypedEvent, startInvestigation } from "./api";

export interface PromotionSuggestion {
  /** The investigation question the promotion would seed (the asset's prompt). */
  question: string;
  /** A plain-language reason the surface shows ("this asset touches…"). */
  rationale: string;
}

/**
 * Build the promote-to-Research SUGGESTION for a meta-reading asset. PURE — it
 * computes a suggestion, it does NOT promote. Returns null when there's nothing
 * coherent to promote (an empty asset), so the surface shows no suggestion
 * rather than a hollow one.
 */
export function suggestPromotion(args: {
  prompt: string;
  corpusDocumentIds: string[];
}): PromotionSuggestion | null {
  if (!args.prompt.trim() || args.corpusDocumentIds.length === 0) return null;
  const n = args.corpusDocumentIds.length;
  return {
    question: args.prompt.trim(),
    rationale: `This reading drew on ${n} of your book${n === 1 ? "" : "s"}. Want to chase it further as a full research?`,
  };
}

export interface PromotionResult {
  investigation_id: string;
}

/**
 * EXPLICIT promotion — call ONLY from a user-accept handler. Starts a Research
 * investigation seeded with the asset's prompt, then records the
 * `seam.read_to_research` handoff (the asset's region → the launched research)
 * through the single-writer funnel. Never auto-invoked.
 *
 * The seam event is best-effort: if it fails the research still launched (the
 * handoff is an audit link, not the launch). Returns the launched id.
 */
export async function acceptPromotion(args: {
  assetId: string;
  prompt: string;
  /** A representative owned document the asset drew on — the seam's region
   * provenance (`document_id`). */
  documentId: string;
}): Promise<PromotionResult> {
  const started = await startInvestigation({
    question: args.prompt,
    context: "Promoted from a meta-reading asset (Read → Research).",
    spawn_context: `read-meta-asset:${args.assetId}`,
  });

  // Record the read → research seam (reuses the EXISTING typed event — no new
  // silo). entity_kind document_region; provenance_ref the asset; the launched
  // investigation named so the asset can link back.
  try {
    await postTypedEvent({
      investigation_id: started.investigation_id,
      document_id: args.documentId,
      payload: {
        action_type: "seam.read_to_research",
        entity_id: `read-meta-asset:${args.assetId}`,
        entity_kind: "document_region",
        provenance_ref: args.assetId,
        terminates: true,
        from_workflow: "read",
        to_workflow: "research",
        document_id: args.documentId,
        launched_investigation_id: started.investigation_id,
      },
      role: "read/meta_reading",
      policy_id: "read/meta_reading/promote",
    });
  } catch {
    /* the seam is an audit link; the research already launched */
  }

  return { investigation_id: started.investigation_id };
}
