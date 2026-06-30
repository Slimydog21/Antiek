import { postTypedEvent } from "../../lib/api";
import type { ClaimReviewedPayload, Event } from "../../generated/types";
import type { ReviewDueClaimView } from "../../reading-physics/augmentations/review-due";

/**
 * Review-state resolver for SPR-08 review-due.
 *
 * The resolver reads persisted `claim.reviewed` events and marks a claim due
 * only when the LATEST event for that claim carries `next_due_at <= now`. It
 * does not invent first-review schedules for claims with no event: no event is
 * honest no-data, so review-due remains dark.
 */

export interface ClaimReviewedEventView {
  action_type: "claim.reviewed";
  claim_id: string;
  reviewed_at: string;
  next_due_at: string;
  due_label?: string | null;
}

type ReviewStateEventInput = Pick<
  Event,
  "action_type" | "payload" | "emitted_at"
> & {
  synthesis_id?: Event["synthesis_id"];
};

export function isClaimReviewedPayload(
  payload: unknown,
): payload is ClaimReviewedEventView {
  if (payload === null || typeof payload !== "object") return false;
  const p = payload as Record<string, unknown>;
  return (
    p.action_type === "claim.reviewed" &&
    typeof p.claim_id === "string" &&
    p.claim_id.length > 0 &&
    typeof p.reviewed_at === "string" &&
    typeof p.next_due_at === "string"
  );
}

function parseTimeMs(value: string): number | null {
  const ms = Date.parse(value);
  return Number.isFinite(ms) ? ms : null;
}

function eventOrderingTime(event: Pick<Event, "emitted_at">): number {
  return parseTimeMs(event.emitted_at) ?? 0;
}

export function resolveDueClaimsFromEvents(
  events: readonly ReviewStateEventInput[],
  options: { now: Date; synthesisId?: string | null },
): readonly ReviewDueClaimView[] {
  const latest = new Map<string, { payload: ClaimReviewedEventView; order: number }>();
  for (const event of events) {
    if (event.action_type !== "claim.reviewed") continue;
    if (options.synthesisId && event.synthesis_id !== options.synthesisId) {
      continue;
    }
    const payload = event.payload;
    if (!isClaimReviewedPayload(payload)) continue;
    const order = eventOrderingTime(event);
    const prev = latest.get(payload.claim_id);
    if (!prev || order >= prev.order) {
      latest.set(payload.claim_id, { payload, order });
    }
  }

  const nowMs = options.now.getTime();
  const due: ReviewDueClaimView[] = [];
  for (const { payload } of latest.values()) {
    const dueAt = parseTimeMs(payload.next_due_at);
    if (dueAt === null || dueAt > nowMs) continue;
    due.push({
      claimId: payload.claim_id,
      dueLabel: payload.due_label ?? "Due for review",
    });
  }
  return due.sort((a, b) => a.claimId.localeCompare(b.claimId));
}

export async function emitClaimReviewed(args: {
  investigationId: string;
  synthesisId: string;
  claimId: string;
  reviewedAt: Date;
  nextDueAt: Date;
  rating?: string | null;
  ease?: number | null;
  intervalDays?: number | null;
  dueLabel?: string | null;
}): Promise<void> {
  const payload: ClaimReviewedPayload = {
    action_type: "claim.reviewed",
    claim_id: args.claimId,
    reviewed_at: args.reviewedAt.toISOString(),
    next_due_at: args.nextDueAt.toISOString(),
    rating: args.rating ?? null,
    ease: args.ease ?? null,
    interval_days: args.intervalDays ?? null,
    due_label: args.dueLabel ?? null,
  };
  try {
    await postTypedEvent({
      investigation_id: args.investigationId,
      synthesis_id: args.synthesisId,
      payload,
    });
  } catch {
    /* best-effort — a missed review-state emit keeps the cue dark, honestly */
  }
}
