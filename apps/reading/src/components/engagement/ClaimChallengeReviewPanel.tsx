import { useRef, useState } from "react";

import {
  acceptClaimChallengeReview,
  previewClaimChallengeReview,
  reverseClaimChallengeReview,
  type ClaimReviewResponse,
} from "../../lib/api";

type Props = {
  investigationId: string;
  sessionId: string;
  artifactContentHash: string;
};

const mutationKey = (prefix: string) =>
  `${prefix}-${typeof crypto !== "undefined" && typeof crypto.randomUUID === "function" ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`}`;

export function ClaimChallengeReviewPanel({
  investigationId,
  sessionId,
  artifactContentHash,
}: Props) {
  const [review, setReview] = useState<ClaimReviewResponse | null>(null);
  const [rationale, setRationale] = useState(
    "Reverse this acceptance while preserving its immutable review history.",
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const acceptKey = useRef<string | null>(null);
  const reverseKey = useRef<string | null>(null);

  const run = async (work: () => Promise<ClaimReviewResponse>) => {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      const next = await work();
      setReview((current) => ({
        ...next,
        preview: next.preview ?? current?.preview ?? null,
      }));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section
      className="space-y-2"
      data-testid="claim-challenge-review-panel"
      data-status={review?.status ?? "unreviewed"}
      data-view-format="html"
    >
      <h2 className="text-sm font-medium text-ink dark:text-parchment">
        Claim challenge owner review
      </h2>
      <p className="text-[11px] font-mono text-shadow-1 dark:text-moonlight">
        Acceptance appends a private review revision. It never replaces the terminal claim,
        changes provenance, or promotes knowledge.
      </p>
      {!review?.preview ? (
        <button
          type="button"
          disabled={busy}
          onClick={() =>
            void run(() =>
              previewClaimChallengeReview(
                investigationId,
                sessionId,
                artifactContentHash,
              ),
            )
          }
        >
          {busy ? "Resolving…" : "Review completed candidate"}
        </button>
      ) : (
        <div className="space-y-2 rounded border border-ink/20 p-2">
          <p className="text-[10px] font-mono">
            candidate {review.preview.candidate_sha256.slice(0, 12)}…
          </p>
          <pre className="whitespace-pre-wrap text-xs" data-testid="claim-review-candidate">
            {review.preview.candidate_text}
          </pre>
          {review.status === "candidate" ? (
            <button
              type="button"
              disabled={busy}
              onClick={() => {
                acceptKey.current ??= mutationKey("claim-review-accept");
                void run(() =>
                  acceptClaimChallengeReview(investigationId, sessionId, {
                    content_hash: artifactContentHash,
                    preview_sha256: review.preview!.preview_sha256,
                    mutation_key: acceptKey.current!,
                  }),
                );
              }}
            >
              {busy ? "Accepting…" : "Accept as separate review revision"}
            </button>
          ) : null}
        </div>
      )}
      {review?.status === "accepted" && review.acceptance ? (
        <div className="space-y-2">
          <p className="text-xs" role="status">
            Accepted as a separate review revision. Terminal truth remains unchanged.
          </p>
          <label className="block text-xs">
            Reversal rationale
            <textarea
              value={rationale}
              onChange={(event) => {
                setRationale(event.target.value);
                reverseKey.current = null;
              }}
              disabled={busy}
              rows={2}
              className="block w-full"
            />
          </label>
          <button
            type="button"
            disabled={busy || !rationale.trim()}
            onClick={() => {
              reverseKey.current ??= mutationKey("claim-review-reverse");
              void run(() =>
                reverseClaimChallengeReview(investigationId, sessionId, {
                  content_hash: artifactContentHash,
                  acceptance_receipt_sha256: review.acceptance!.receipt_sha256,
                  rationale,
                  mutation_key: reverseKey.current!,
                }),
              );
            }}
          >
            {busy ? "Reversing…" : "Append compensating reversal"}
          </button>
        </div>
      ) : null}
      {review?.status === "reversed" ? (
        <p className="text-xs" role="status">
          Acceptance reversed by an append-only compensation; both receipts remain intact.
        </p>
      ) : null}
      {error ? <p role="alert">{error}</p> : null}
    </section>
  );
}
