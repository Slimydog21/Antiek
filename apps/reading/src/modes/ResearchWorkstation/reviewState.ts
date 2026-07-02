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

export const CLAIM_REVIEW_RATINGS = ["again", "good", "easy"] as const;
export type ClaimReviewRating = (typeof CLAIM_REVIEW_RATINGS)[number];

export interface ClaimReviewSchedule {
  nextDueAt: Date;
  rating: ClaimReviewRating;
  ease: number;
  intervalDays: number;
  dueLabel: string;
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

function nonEmptyString(value: unknown): string | null {
  return typeof value === "string" && value.trim().length > 0
    ? value.trim()
    : null;
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
      dueLabel: nonEmptyString(payload.due_label) ?? "Due for review",
    });
  }
  return due.sort((a, b) => a.claimId.localeCompare(b.claimId));
}

function addMilliseconds(date: Date, ms: number): Date {
  return new Date(date.getTime() + ms);
}

export function scheduleClaimReview(
  reviewedAt: Date,
  rating: ClaimReviewRating,
): ClaimReviewSchedule {
  if (rating === "again") {
    const intervalDays = 30 / (24 * 60);
    return {
      nextDueAt: addMilliseconds(reviewedAt, 30 * 60 * 1000),
      rating,
      ease: 1.3,
      intervalDays,
      dueLabel: "Due again soon",
    };
  }
  if (rating === "easy") {
    return {
      nextDueAt: addMilliseconds(reviewedAt, 7 * 24 * 60 * 60 * 1000),
      rating,
      ease: 3,
      intervalDays: 7,
      dueLabel: "Due in a week",
    };
  }
  return {
    nextDueAt: addMilliseconds(reviewedAt, 24 * 60 * 60 * 1000),
    rating,
    ease: 2.5,
    intervalDays: 1,
    dueLabel: "Due tomorrow",
  };
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
}): Promise<boolean> {
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
    return true;
  } catch {
    /* best-effort — a missed review-state emit keeps the cue dark, honestly */
    return false;
  }
}
