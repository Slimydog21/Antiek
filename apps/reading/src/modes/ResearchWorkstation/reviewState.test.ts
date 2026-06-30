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

describe("emitClaimReviewed", () => {
  it("posts a claim.reviewed typed event with scheduler metadata and no body", async () => {
    await emitClaimReviewed({
      investigationId: "read-syn-1",
      synthesisId: "syn-1",
      claimId: "2",
      reviewedAt: new Date("2026-06-30T10:00:00Z"),
      nextDueAt: new Date("2026-07-01T10:00:00Z"),
      rating: "good",
      ease: 2.5,
      intervalDays: 1,
      dueLabel: "Due tomorrow",
    });

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
    expect(env.payload.next_due_at).toBe("2026-07-01T10:00:00.000Z");
    for (const forbidden of ["content", "excerpt", "text", "body", "full_text", "snippet"]) {
      expect(env.payload[forbidden]).toBeUndefined();
    }
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
    ).resolves.toBeUndefined();
  });
});
