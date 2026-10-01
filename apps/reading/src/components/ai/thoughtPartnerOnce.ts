/**
 * thoughtPartnerOnce.ts — the ONE one-shot wire to /thought-partner.
 *
 * The FloatMenu Dialogue action (floatMenuActions.dialogueOverSelection)
 * and the companion's dialogue agent tab both go through here, so the
 * endpoint, the payload shape, and the response normalization
 * (`text ?? body`, the shape vocabulary) exist exactly once. One-shot by
 * contract: a single prompt → a single reply, never a chat loop.
 *
 * PROVENANCE (unchanged from the FloatMenu action): the prompt is
 * USER-sourced; the reply is MODEL-sourced; the two are never conflated.
 * When no provider is configured the endpoint 503s — the caller surfaces
 * the shared AIActionFailure no-key state, never a fabricated reply.
 */
import { ApiError, apiFetch } from "../../lib/api";
import {
  normalizeThoughtPartnerShape,
  type ThoughtPartnerShape,
} from "../../hooks/useThoughtPartnerThread";
import { composeThoughtPartnerSystemContext } from "./thoughtPartnerSeed";

export interface ThoughtPartnerOnceReply {
  /** The user's prompt — visibly USER-sourced above the reply. */
  prompt: string;
  /** The model's reply — MODEL-sourced, never relabelled. */
  reply: string;
  shape: ThoughtPartnerShape;
}

export async function thoughtPartnerOnce(args: {
  /** The typed-event bucket the exchange is scoped to (an investigation id,
   *  or a named ambient scope like AISidecar's "__sidecar__"). */
  investigationId: string;
  prompt: string;
}): Promise<ThoughtPartnerOnceReply> {
  const resp = await apiFetch("/thought-partner", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      investigation_id: args.investigationId,
      prompt: args.prompt,
      system_context: composeThoughtPartnerSystemContext(null),
    }),
  });
  if (!resp.ok) {
    throw new ApiError(
      `POST /thought-partner failed: HTTP ${resp.status}`,
      resp.status,
      await resp.text(),
    );
  }
  const data = await resp.json();
  return {
    prompt: args.prompt,
    reply: data.text ?? data.body ?? "",
    shape: normalizeThoughtPartnerShape(data.shape),
  };
}
