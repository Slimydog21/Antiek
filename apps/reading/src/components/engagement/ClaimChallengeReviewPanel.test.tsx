import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ClaimChallengeReviewPanel } from "./ClaimChallengeReviewPanel";

const api = vi.hoisted(() => ({
  preview: vi.fn(),
  accept: vi.fn(),
  reverse: vi.fn(),
}));

vi.mock("../../lib/api", () => ({
  previewClaimChallengeReview: api.preview,
  acceptClaimChallengeReview: api.accept,
  reverseClaimChallengeReview: api.reverse,
}));

const preview = {
  status: "candidate" as const,
  preview: {
    preview_sha256: "a".repeat(64),
    candidate_sha256: "b".repeat(64),
    candidate_text: "Counter-analysis remains separate.",
    html: "<article>Counter-analysis remains separate.</article>",
    view_format: "html" as const,
  },
  acceptance: null,
  reversal: null,
  view_format: "html" as const,
};

describe("ClaimChallengeReviewPanel", () => {
  beforeEach(() => {
    api.preview.mockReset().mockResolvedValue(preview);
    api.accept.mockReset().mockResolvedValue({
      ...preview,
      status: "accepted",
      preview: null,
      acceptance: {
        schema_version: 1,
        kind: "claim_challenge_acceptance",
        receipt_sha256: "c".repeat(64),
        candidate_sha256: "b".repeat(64),
        candidate_text: preview.preview.candidate_text,
        preview_sha256: "a".repeat(64),
      },
    });
    api.reverse.mockReset().mockResolvedValue({
      ...preview,
      status: "reversed",
      preview: null,
      acceptance: {
        schema_version: 1,
        kind: "claim_challenge_acceptance",
        receipt_sha256: "c".repeat(64),
        candidate_sha256: "b".repeat(64),
        candidate_text: preview.preview.candidate_text,
        preview_sha256: "a".repeat(64),
      },
      reversal: {
        schema_version: 1,
        kind: "claim_challenge_reversal",
        receipt_sha256: "d".repeat(64),
        acceptance_receipt_sha256: "c".repeat(64),
        rationale: "Reverse while preserving history.",
      },
    });
  });

  it("requires preview, then explicit acceptance, then append-only reversal", async () => {
    render(
      <ClaimChallengeReviewPanel
        investigationId="inv-review"
        sessionId="session-review"
        artifactContentHash={"e".repeat(64)}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Review completed candidate" }));
    expect(
      (await screen.findByTestId("claim-review-candidate")).textContent,
    ).toContain("Counter-analysis remains separate.");
    expect(api.preview).toHaveBeenCalledWith(
      "inv-review",
      "session-review",
      "e".repeat(64),
    );

    fireEvent.click(
      screen.getByRole("button", { name: "Accept as separate review revision" }),
    );
    await waitFor(() => expect(api.accept).toHaveBeenCalledTimes(1));
    expect(
      await screen.findByText(
        "Accepted as a separate review revision. Terminal truth remains unchanged.",
      ),
    ).toBeTruthy();
    expect(screen.getByTestId("claim-review-candidate")).toBeTruthy();

    fireEvent.change(screen.getByRole("textbox", { name: "Reversal rationale" }), {
      target: { value: "Reverse while preserving history." },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Append compensating reversal" }),
    );
    expect(
      await screen.findByText(
        "Acceptance reversed by an append-only compensation; both receipts remain intact.",
      ),
    ).toBeTruthy();
    expect(api.reverse).toHaveBeenCalledWith(
      "inv-review",
      "session-review",
      expect.objectContaining({
        content_hash: "e".repeat(64),
        acceptance_receipt_sha256: "c".repeat(64),
        rationale: "Reverse while preserving history.",
      }),
    );
  });
});
