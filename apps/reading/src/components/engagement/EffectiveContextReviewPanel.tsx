import { useEffect, useRef, useState } from "react";

import {
  acceptEffectiveContextCompensation,
  acceptEffectiveContextReview,
  getEffectiveContextReview,
  previewEffectiveContextCompensation,
  previewEffectiveContextReview,
  type EffectiveContextCompensationResponse,
  type EffectiveContextReviewReadResponse,
  type EffectiveContextReviewResponse,
} from "../../lib/api";

type Props = {
  investigationId: string;
  sessionId: string;
  artifactContentHash: string;
};

export function EffectiveContextReviewPanel({
  investigationId,
  sessionId,
  artifactContentHash,
}: Props) {
  const [disposition, setDisposition] = useState<"retain_current" | "propose_compensation">("retain_current");
  const [rationale, setRationale] = useState("");
  const [proposedClaim, setProposedClaim] = useState("");
  const [review, setReview] = useState<EffectiveContextReviewResponse | null>(null);
  const [persisted, setPersisted] = useState<EffectiveContextReviewReadResponse | null>(null);
  const [compensation, setCompensation] = useState<EffectiveContextCompensationResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const generation = useRef(0);
  const mutationKey = useRef<string | null>(null);
  const compensationMutationKey = useRef<string | null>(null);

  useEffect(() => {
    generation.current += 1;
    setReview(null);
    setPersisted(null);
    setCompensation(null);
    setError(null);
    setBusy(false);
    setDisposition("retain_current");
    setRationale("");
    setProposedClaim("");
    mutationKey.current = null;
    compensationMutationKey.current = null;
    const requestGeneration = generation.current;
    void getEffectiveContextReview(investigationId, sessionId)
      .then((value) => {
        if (generation.current === requestGeneration) setPersisted(value);
      })
      .catch(() => undefined);
  }, [investigationId, sessionId, artifactContentHash]);

  const command = () => ({
    content_hash: artifactContentHash,
    disposition,
    rationale,
    proposed_claim: disposition === "propose_compensation" ? proposedClaim : null,
  });

  return (
    <section className="space-y-2" data-testid="effective-context-review-panel">
      <h2 className="text-sm font-medium text-ink dark:text-parchment">Owner-context research review</h2>
      <p className="text-[11px] font-mono text-shadow-1 dark:text-moonlight">
        Review keeps archived evidence, owner-authored wording, and candidate analysis separate. It cannot append canonical wording.
      </p>
      {persisted ? (
        <div className="space-y-1 rounded border border-ink/20 p-2 text-xs">
          <p><strong>Archived evidence baseline:</strong> {persisted.archived_claim}</p>
          <p><strong>Archived evaluation:</strong> {persisted.archived_evaluation.relation ?? "unavailable"} · score {persisted.archived_evaluation.score} · {persisted.archived_evaluation.scorer_id}</p>
          <p><strong>Direct evidence receipts:</strong> {persisted.archived_direct_evidence_receipt_sha256s.join(", ") || "none"}</p>
          <p><strong>Inherited support:</strong> {persisted.archived_inherited_support.map((item) => `${item.unit_id} (${item.qualification_state})`).join(", ") || "none"}</p>
          <p><strong>Owner-authored current wording:</strong> {persisted.effective_claim}</p>
          <pre className="whitespace-pre-wrap"><strong>Research candidate:</strong> {persisted.candidate_text}</pre>
          <p role="status">{persisted.consumption ? "Immutable review accepted; its canonical compensation is recorded separately." : "Immutable review accepted separately. Canonical wording remains unchanged."}</p>
          {persisted.proposal ? <>
            <p><strong>Reviewed proposal:</strong> {persisted.proposal.proposed_claim}</p>
            <p><strong>Rationale:</strong> {persisted.proposal.rationale}</p>
            <p className="font-mono break-all">Proposal receipt: {persisted.proposal.receipt_sha256}</p>
            {!compensation && !persisted.consumption ? (
              <button
                type="button"
                disabled={busy}
                onClick={() => {
                  const requestGeneration = ++generation.current;
                  compensationMutationKey.current ??= `effective-context-compensation:${crypto.randomUUID()}`;
                  setBusy(true);
                  setError(null);
                  void previewEffectiveContextCompensation(investigationId, sessionId, {
                    content_hash: artifactContentHash,
                    proposal_receipt_sha256: persisted.proposal!.receipt_sha256,
                    mutation_key: compensationMutationKey.current,
                  }).then((value) => {
                    if (generation.current === requestGeneration) setCompensation(value);
                  }).catch(() => {
                    if (generation.current === requestGeneration) setError("The canonical compensation preview is stale or unavailable.");
                  }).finally(() => {
                    if (generation.current === requestGeneration) setBusy(false);
                  });
                }}
              >
                Preview canonical compensation
              </button>
            ) : null}
            {compensation?.preview ? (
              <div className="space-y-1 rounded border border-ink/20 p-2">
                <p><strong>Current owner wording:</strong> {compensation.preview.prior_effective_claim}</p>
                <p><strong>Prospective owner wording:</strong> {compensation.preview.replacement_claim}</p>
                <p className="font-mono break-all">Prospective artifact: {compensation.preview.prospective_artifact_content_hash}</p>
                <p>Append-only owner change. Archived evidence remains unchanged.</p>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => {
                    const requestGeneration = ++generation.current;
                    setBusy(true);
                    setError(null);
                    void acceptEffectiveContextCompensation(investigationId, sessionId, {
                      content_hash: artifactContentHash,
                      proposal_receipt_sha256: persisted.proposal!.receipt_sha256,
                      mutation_key: compensationMutationKey.current!,
                      preview_sha256: compensation.preview!.preview_sha256,
                      transition_sha256: compensation.preview!.transition_sha256,
                    }).then(async (value) => {
                      const refreshed = await getEffectiveContextReview(investigationId, sessionId);
                      if (generation.current === requestGeneration) {
                        setCompensation(value);
                        setPersisted(refreshed);
                      }
                    }).catch(() => {
                      if (generation.current === requestGeneration) setError("The canonical compensation was not appended. Reload current artifact state.");
                    }).finally(() => {
                      if (generation.current === requestGeneration) setBusy(false);
                    });
                  }}
                >
                  Accept canonical compensation
                </button>
              </div>
            ) : null}
            {compensation?.acceptance && !persisted.consumption ? (
              <p role="status" className="font-mono break-all">Canonical compensation accepted: {compensation.acceptance.transition_sha256}</p>
            ) : null}
            {persisted.consumption ? (
              <p role="status" className="font-mono break-all">Canonical compensation accepted: {persisted.consumption.transition_sha256}</p>
            ) : null}
          </> : null}
        </div>
      ) : null}
      {!persisted ? <>
      <label className="block text-xs">
        Disposition
        <select
          value={disposition}
          disabled={busy || review?.status === "accepted"}
          onChange={(event) => {
            generation.current += 1;
            setDisposition(event.target.value as typeof disposition);
            setReview(null);
            mutationKey.current = null;
          }}
        >
          <option value="retain_current">Retain current owner wording</option>
          <option value="propose_compensation">Propose later compensation</option>
        </select>
      </label>
      {disposition === "propose_compensation" ? (
        <label className="block text-xs">
          Proposed owner wording
          <textarea
            value={proposedClaim}
            disabled={busy || review?.status === "accepted"}
            onChange={(event) => {
              generation.current += 1;
              setProposedClaim(event.target.value);
              setReview(null);
              mutationKey.current = null;
            }}
          />
        </label>
      ) : null}
      <label className="block text-xs">
        Review rationale
        <textarea
          value={rationale}
          disabled={busy || review?.status === "accepted"}
          onChange={(event) => {
            generation.current += 1;
            setRationale(event.target.value);
            setReview(null);
            mutationKey.current = null;
          }}
        />
      </label>
      {!review ? (
        <button
          type="button"
          disabled={busy || !rationale.trim() || (disposition === "propose_compensation" && !proposedClaim.trim())}
          onClick={() => {
            const requestGeneration = ++generation.current;
            setBusy(true);
            setError(null);
            void previewEffectiveContextReview(investigationId, sessionId, command())
              .then((value) => {
                if (generation.current === requestGeneration) setReview(value);
              })
              .catch(() => {
                if (generation.current === requestGeneration) setError("The three-channel review preview is stale or unavailable.");
              })
              .finally(() => {
                if (generation.current === requestGeneration) setBusy(false);
              });
          }}
        >
          Preview three-channel review
        </button>
      ) : null}
      {review?.preview ? (
        <div className="space-y-2 rounded border border-ink/20 p-2 text-xs">
          <p><strong>Archived evidence baseline:</strong> {review.preview.archived_claim}</p>
          <p>
            <strong>Archived evaluation:</strong> {review.preview.archived_evaluation.relation ?? "unavailable"}
            {" · score "}{review.preview.archived_evaluation.score}
            {" · "}{review.preview.archived_evaluation.scorer_id}
          </p>
          <p><strong>Direct evidence receipts:</strong> {review.preview.archived_direct_evidence_receipt_sha256s.join(", ") || "none"}</p>
          <p><strong>Inherited support:</strong> {review.preview.archived_inherited_support.map((item) => `${item.unit_id} (${item.qualification_state})`).join(", ") || "none"}</p>
          <p><strong>Owner-authored current wording:</strong> {review.preview.effective_claim}</p>
          <pre className="whitespace-pre-wrap"><strong>Research candidate:</strong> {review.preview.candidate_text}</pre>
          <p>Review only · no canonical append.</p>
          {review.status === "candidate" ? (
            <button
              type="button"
              disabled={busy}
              onClick={() => {
                const requestGeneration = ++generation.current;
                mutationKey.current ??= `effective-context-review:${crypto.randomUUID()}`;
                setBusy(true);
                setError(null);
                void acceptEffectiveContextReview(investigationId, sessionId, {
                  ...command(),
                  preview_sha256: review.preview.preview_sha256,
                  mutation_key: mutationKey.current,
                }).then((value) => {
                  if (generation.current === requestGeneration) setReview(value);
                }).catch(() => {
                  if (generation.current === requestGeneration) setError("The review was not accepted. Reload the current artifact and candidate.");
                }).finally(() => {
                  if (generation.current === requestGeneration) setBusy(false);
                });
              }}
            >
              Accept immutable review
            </button>
          ) : null}
        </div>
      ) : null}
      {review?.status === "accepted" ? (
        <p role="status" className="text-xs">Review accepted separately. Canonical owner wording remains unchanged.</p>
      ) : null}
      </> : null}
      {error ? <p role="alert">{error}</p> : null}
    </section>
  );
}
