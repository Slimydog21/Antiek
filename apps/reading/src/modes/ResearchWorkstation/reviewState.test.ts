import { afterEach, describe, expect, it, vi } from "vitest";

const postTypedEventMock = vi.hoisted(() =>
  vi.fn((_e: unknown) => Promise.resolve({ event_id: "ev-review-1", action_type: "claim.reviewed" })),
);

vi.mock("../../lib/api", async (orig) => {
  const actual = await orig<typeof import("../../lib/api")>();
  return { ...actual, postTypedEvent: (e: unknown) => postTypedEventMock(e) };
});

import type { Event } from "../../generated/types";
import {
  emitClaimReviewed,
  isClaimReviewedPayload,
  resolveDueClaimsFromEvents,
  scheduleClaimReview,
} from "./reviewState";

afterEach(() => postTypedEventMock.mockClear());

function ev(
  payload: Record<string, unknown>,
  emitted_at: string,
  synthesis_id: string | null = "syn-1",
): Pick<Event, "action_type" | "payload" | "emitted_at" | "synthesis_id"> {
  return {
    action_type: String(payload.action_type ?? "") as Event["action_type"],
    payload: payload as unknown as Event["payload"],
    emitted_at,
    synthesis_id,
  };
}

describe("reviewState resolver", () => {
  it("marks claims due from the latest claim.reviewed next_due_at verdict", () => {
    const due = resolveDueClaimsFromEvents(
      [
        ev(
          {
            action_type: "claim.reviewed",
            claim_id: "1",
            reviewed_at: "2026-06-29T10:00:00Z",
            next_due_at: "2026-06-30T09:00:00Z",
            due_label: "Due today",
          },
          "2026-06-29T10:00:01Z",
        ),
        ev(
          {
            action_type: "claim.reviewed",
            claim_id: "2",
            reviewed_at: "2026-06-30T10:00:00Z",
            next_due_at: "2026-07-02T10:00:00Z",
            due_label: "Due later",
          },
          "2026-06-30T10:00:01Z",
        ),
      ],
      { now: new Date("2026-06-30T10:00:00Z") },
    );

    expect(due).toEqual([{ claimId: "1", dueLabel: "Due today" }]);
  });

  it("latest event wins, so a later review can move a claim out of due state", () => {
    const due = resolveDueClaimsFromEvents(
      [
        ev(
          {
            action_type: "claim.reviewed",
            claim_id: "1",
            reviewed_at: "2026-06-29T10:00:00Z",
            next_due_at: "2026-06-30T09:00:00Z",
          },
          "2026-06-29T10:00:01Z",
        ),
        ev(
          {
            action_type: "claim.reviewed",
            claim_id: "1",
            reviewed_at: "2026-06-30T09:30:00Z",
            next_due_at: "2026-07-07T09:30:00Z",
          },
          "2026-06-30T09:30:01Z",
        ),
      ],
      { now: new Date("2026-06-30T10:00:00Z") },
    );

    expect(due).toEqual([]);
  });

  it("scopes review state to the rendered synthesis when a synthesis id is provided", () => {
    const due = resolveDueClaimsFromEvents(
      [
        ev(
          {
            action_type: "claim.reviewed",
            claim_id: "1",
            reviewed_at: "2026-06-30T09:00:00Z",
            next_due_at: "2026-06-30T09:00:00Z",
            due_label: "Wrong synthesis",
          },
          "2026-06-30T09:00:01Z",
          "syn-other",
        ),
        ev(
          {
            action_type: "claim.reviewed",
            claim_id: "1",
            reviewed_at: "2026-06-30T09:30:00Z",
            next_due_at: "2026-06-30T09:30:00Z",
            due_label: "Due here",
          },
          "2026-06-30T09:30:01Z",
          "syn-1",
        ),
      ],
      { now: new Date("2026-06-30T10:00:00Z"), synthesisId: "syn-1" },
    );

    expect(due).toEqual([{ claimId: "1", dueLabel: "Due here" }]);
  });

  it("empty/malformed history fabricates no due claims", () => {
    expect(resolveDueClaimsFromEvents([], { now: new Date("2026-06-30T10:00:00Z") })).toEqual([]);
    expect(
      resolveDueClaimsFromEvents(
        [
          ev({ action_type: "claim.reviewed", claim_id: "", reviewed_at: "x", next_due_at: "x" }, "x"),
          ev({ action_type: "source.read", chunk_id: "c1" }, "2026-06-30T10:00:00Z"),
        ],
        { now: new Date("2026-06-30T10:00:00Z") },
      ),
    ).toEqual([]);
  });

  it("sanitizes malformed due labels before exposing review cues", () => {
    const due = resolveDueClaimsFromEvents(
      [
        ev(
          {
            action_type: "claim.reviewed",
            claim_id: "1",
            reviewed_at: "2026-06-30T09:00:00Z",
            next_due_at: "2026-06-30T09:00:00Z",
            due_label: { text: "not renderable" },
          },
          "2026-06-30T09:00:01Z",
        ),
        ev(
          {
            action_type: "claim.reviewed",
            claim_id: "2",
            reviewed_at: "2026-06-30T09:30:00Z",
            next_due_at: "2026-06-30T09:30:00Z",
            due_label: "  Custom due label  ",
          },
          "2026-06-30T09:30:01Z",
        ),
      ],
      { now: new Date("2026-06-30T10:00:00Z") },
    );

    expect(due).toEqual([
      { claimId: "1", dueLabel: "Due for review" },
      { claimId: "2", dueLabel: "Custom due label" },
    ]);
  });

  it("orders due claims by positional claim id, not lexicographic string order", () => {
    const due = resolveDueClaimsFromEvents(
      ["10", "2", "1"].map((claimId, index) =>
        ev(
          {
            action_type: "claim.reviewed",
            claim_id: claimId,
            reviewed_at: "2026-06-30T09:00:00Z",
            next_due_at: "2026-06-30T09:00:00Z",
            due_label: `Due ${claimId}`,
          },
          `2026-06-30T09:00:0${index}Z`,
        ),
      ),
      { now: new Date("2026-06-30T10:00:00Z") },
    );

    expect(due.map((d) => d.claimId)).toEqual(["1", "2", "10"]);
  });

  it("identifies the minimal claim.reviewed payload shape", () => {
    expect(
      isClaimReviewedPayload({
        action_type: "claim.reviewed",
        claim_id: "1",
        reviewed_at: "2026-06-30T10:00:00Z",
        next_due_at: "2026-07-01T10:00:00Z",
      }),
    ).toBe(true);
    expect(isClaimReviewedPayload({ action_type: "claim.reviewed", claim_id: "" })).toBe(false);
  });
});

describe("scheduleClaimReview", () => {
  it("returns deterministic v1 intervals for review ratings", () => {
    const reviewedAt = new Date("2026-06-30T10:00:00Z");

    expect(scheduleClaimReview(reviewedAt, "again")).toMatchObject({
      rating: "again",
      nextDueAt: new Date("2026-06-30T10:30:00Z"),
      ease: 1.3,
      intervalDays: 30 / (24 * 60),
      dueLabel: "Due again soon",
    });
    expect(scheduleClaimReview(reviewedAt, "good")).toMatchObject({
      rating: "good",
      nextDueAt: new Date("2026-07-01T10:00:00Z"),
      ease: 2.5,
      intervalDays: 1,
      dueLabel: "Due tomorrow",
    });
    expect(scheduleClaimReview(reviewedAt, "easy")).toMatchObject({
      rating: "easy",
      nextDueAt: new Date("2026-07-07T10:00:00Z"),
      ease: 3,
      intervalDays: 7,
      dueLabel: "Due in a week",
    });
  });
});

describe("emitClaimReviewed", () => {
  it("posts a claim.reviewed typed event with scheduler metadata and no body", async () => {
    await expect(emitClaimReviewed({
      investigationId: " read-syn-1 ",
      synthesisId: " syn-1 ",
      claimId: " 2 ",
      reviewedAt: new Date("2026-06-30T10:00:00Z"),
      nextDueAt: new Date("2026-07-01T10:00:00Z"),
      rating: " good ",
      ease: 2.5,
      intervalDays: 1,
      dueLabel: " Due tomorrow ",
    })).resolves.toBe(true);

    expect(postTypedEventMock).toHaveBeenCalledTimes(1);
    const env = postTypedEventMock.mock.calls[0][0] as {
      investigation_id: string;
      synthesis_id?: string;
      payload: Record<string, unknown>;
    };
    expect(env.investigation_id).toBe("read-syn-1");
    expect(env.synthesis_id).toBe("syn-1");
    expect(env.payload.action_type).toBe("claim.reviewed");
    expect(env.payload.claim_id).toBe("2");
    expect(env.payload.rating).toBe("good");
    expect(env.payload.ease).toBe(2.5);
    expect(env.payload.interval_days).toBe(1);
    expect(env.payload.due_label).toBe("Due tomorrow");
    expect(env.payload.next_due_at).toBe("2026-07-01T10:00:00.000Z");
    for (const forbidden of ["content", "excerpt", "text", "body", "full_text", "snippet"]) {
      expect(env.payload[forbidden]).toBeUndefined();
    }
  });

  it("drops malformed review handles and dates before touching the typed-event funnel", async () => {
    const valid = {
      investigationId: "read-syn",
      synthesisId: "syn",
      claimId: "1",
      reviewedAt: new Date("2026-06-30T10:00:00Z"),
      nextDueAt: new Date("2026-07-01T10:00:00Z"),
    };

    await expect(emitClaimReviewed({ ...valid, investigationId: " " })).resolves.toBe(false);
    await expect(emitClaimReviewed({ ...valid, synthesisId: " " })).resolves.toBe(false);
    await expect(emitClaimReviewed({ ...valid, claimId: " " })).resolves.toBe(false);
    await expect(emitClaimReviewed({ ...valid, reviewedAt: new Date(Number.NaN) })).resolves.toBe(false);
    await expect(emitClaimReviewed({ ...valid, nextDueAt: new Date(Number.NaN) })).resolves.toBe(false);

    expect(postTypedEventMock).not.toHaveBeenCalled();
  });

  it("nulls malformed optional scheduler metadata before posting", async () => {
    await expect(emitClaimReviewed({
      investigationId: "read-syn",
      synthesisId: "syn",
      claimId: "1",
      reviewedAt: new Date("2026-06-30T10:00:00Z"),
      nextDueAt: new Date("2026-07-01T10:00:00Z"),
      rating: " ",
      ease: Number.POSITIVE_INFINITY,
      intervalDays: -1,
      dueLabel: " ",
    })).resolves.toBe(true);

    expect(postTypedEventMock).toHaveBeenCalledTimes(1);
    const env = postTypedEventMock.mock.calls[0][0] as { payload: Record<string, unknown> };
    expect(env.payload.rating).toBeNull();
    expect(env.payload.ease).toBeNull();
    expect(env.payload.interval_days).toBeNull();
    expect(env.payload.due_label).toBeNull();
  });

  it("is best-effort and never throws into the reader", async () => {
    postTypedEventMock.mockRejectedValueOnce(new Error("503"));
    await expect(
      emitClaimReviewed({
        investigationId: "read-syn",
        synthesisId: "syn",
        claimId: "1",
        reviewedAt: new Date("2026-06-30T10:00:00Z"),
        nextDueAt: new Date("2026-07-01T10:00:00Z"),
      }),
    ).resolves.toBe(false);
  });
});
