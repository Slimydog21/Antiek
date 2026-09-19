import { useEffect, useRef, useState } from "react";

import {
  API_BASE,
  acceptReasoningAncestryInterrogation,
  acceptRecursiveRoundContext,
  acceptEffectiveOwnerContext,
  acceptClaimRevisionCompensation,
  acceptClaimRevision,
  createClaimReconsideration,
  getEffectiveClaimIterations,
  getReasoningAncestry,
  getResearchArtifactClaim,
  previewClaimReconsideration,
  previewClaimRevision,
  previewClaimRevisionCompensation,
  previewEffectiveOwnerContext,
  previewRecursiveRoundContext,
  previewReasoningAncestryInterrogation,
  reserveResearchArtifactClaimChallenge,
  type EffectiveClaimIterationsResponse,
  type ReasoningAncestryResponse,
  type ReasoningAncestryInterrogationResponse,
  type RecursiveRoundContextPreview,
  type ResearchArtifactClaimSupport,
} from "../lib/api";
import { useAuth } from "../lib/auth";
import { sha256Hex } from "../lib/hash";
import { openHostedDocumentPanel } from "../workspace/actions";
import { openDeepResearchFromHighlight } from "../workspace/deepResearchWindow";
import { openWindow } from "./windows/openWindow";

interface Props extends Record<string, unknown> {
  investigationId?: string;
  claimIndex?: number;
  contentHash?: string;
  claimId?: string;
}

const qualificationCopy = {
  complete: "source coverage complete",
  partial: "source coverage partial",
  unknown: "source coverage unknown",
  legacy_unqualified: "legacy evidence — not source-qualified",
} as const;

const ownerContextMutationKey = async (head: string, question: string) =>
  `effective-owner-context:${await sha256Hex(new TextEncoder().encode(`${head}\u0000${question.trim()}`))}`;

export default function ClaimSupportInspector({
  investigationId,
  claimIndex,
  contentHash,
  claimId,
}: Props) {
  const { sessionGeneration } = useAuth();
  const [claim, setClaim] = useState<ResearchArtifactClaimSupport | null>(null);
  const [iterations, setIterations] = useState<EffectiveClaimIterationsResponse | null>(null);
  const [ancestry, setAncestry] = useState<ReasoningAncestryResponse | null>(null);
  const [interrogationTerminals, setInterrogationTerminals] = useState<number[]>([]);
  const [interrogationQuestion, setInterrogationQuestion] = useState("");
  const [interrogationPreview, setInterrogationPreview] = useState<ReasoningAncestryInterrogationResponse | null>(null);
  const [interrogationBusy, setInterrogationBusy] = useState(false);
  const [selectedRoundOrdinals, setSelectedRoundOrdinals] = useState<number[]>([]);
  const [recursiveQuestions, setRecursiveQuestions] = useState("");
  const [recursivePreview, setRecursivePreview] = useState<RecursiveRoundContextPreview | null>(null);
  const [recursiveBusy, setRecursiveBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [challengeGoal, setChallengeGoal] = useState("Test this claim against the strongest available counterevidence and identify what would change the conclusion.");
  const [challengeBusy, setChallengeBusy] = useState(false);
  const [ownerContextPreview, setOwnerContextPreview] = useState<{
    previewSha256: string;
    receiptSha256: string;
    archivedClaim: string;
    effectiveClaim: string;
    headTransitionSha256: string;
  } | null>(null);
  const [selectedReviews, setSelectedReviews] = useState<string[]>([]);
  const [proposedClaim, setProposedClaim] = useState("");
  const [reconsiderationRationale, setReconsiderationRationale] = useState("");
  const [reconsiderationPreview, setReconsiderationPreview] = useState<string | null>(null);
  const [reconsiderationBusy, setReconsiderationBusy] = useState(false);
  const [activeContentHash, setActiveContentHash] = useState(contentHash ?? "");
  const [revisionPreview, setRevisionPreview] = useState<{ previewSha256: string; transitionSha256: string } | null>(null);
  const [compensationOperation, setCompensationOperation] = useState<"restore_archived_terminal" | "supersede_owner_revision">("restore_archived_terminal");
  const [compensationReplacement, setCompensationReplacement] = useState("");
  const [compensationRationale, setCompensationRationale] = useState("");
  const [compensationPreview, setCompensationPreview] = useState<{
    previewSha256: string;
    transitionSha256: string;
    priorEffectiveClaim: string;
    replacementClaim: string;
    rationale: string;
  } | null>(null);
  const reconsiderationGeneration = useRef(0);
  const recursiveGeneration = useRef(0);
  const interrogationGeneration = useRef(0);

  useEffect(() => {
    reconsiderationGeneration.current += 1;
    recursiveGeneration.current += 1;
    interrogationGeneration.current += 1;
    let live = true;
    if (!investigationId || !Number.isInteger(claimIndex) || claimIndex! < 0 || !contentHash) {
      setClaim(null);
      setError(null);
      return () => { live = false; };
    }
    setClaim(null);
    setIterations(null);
    setAncestry(null);
    setInterrogationTerminals([]);
    setInterrogationQuestion("");
    setInterrogationPreview(null);
    setInterrogationBusy(false);
    setSelectedRoundOrdinals([]);
    setRecursiveQuestions("");
    setRecursivePreview(null);
    setRecursiveBusy(false);
    setError(null);
    setSelectedReviews([]);
    setOwnerContextPreview(null);
    setProposedClaim("");
    setReconsiderationRationale("");
    setReconsiderationPreview(null);
    setReconsiderationBusy(false);
    setActiveContentHash(contentHash);
    setRevisionPreview(null);
    setCompensationOperation("restore_archived_terminal");
    setCompensationReplacement("");
    setCompensationRationale("");
    setCompensationPreview(null);
    void (async () => {
      try {
        const value = await getResearchArtifactClaim(investigationId, claimIndex!, contentHash);
        if (live) setClaim(value);
      } catch {
        if (live) setError("This claim is unavailable or the research artifact changed. Reopen it from the current artifact shelf.");
      }
    })();
    return () => { live = false; };
  }, [investigationId, claimIndex, contentHash, sessionGeneration]);

  useEffect(() => {
    let live = true;
    if (!investigationId || !Number.isInteger(claimIndex) || !claim?.owner_revision) {
      setIterations(null);
      return () => { live = false; };
    }
    void Promise.all([
      getEffectiveClaimIterations(investigationId, claimIndex!),
      getReasoningAncestry(investigationId, claimIndex!),
    ])
      .then(([value, graph]) => {
        if (!live) return;
        if (
          value.artifact_content_hash !== activeContentHash
          || value.current_head_transition_sha256 !== claim.owner_revision?.head_transition_sha256
          || graph.artifact_content_hash !== activeContentHash
          || graph.current_head_transition_sha256 !== claim.owner_revision?.head_transition_sha256
          || graph.current_head_transition_sha256 !== value.current_head_transition_sha256
        ) {
          setIterations(null);
          setAncestry(null);
          setError("The recursive research ledger advanced beyond this displayed claim. Reopen the current artifact before continuing.");
          return;
        }
        setIterations(value);
        setAncestry(graph);
      })
      .catch(() => {
        if (live) { setIterations(null); setAncestry(null); }
      });
    return () => { live = false; };
  }, [investigationId, claimIndex, claim?.owner_revision?.head_transition_sha256, activeContentHash, sessionGeneration]);

  if (!investigationId || !Number.isInteger(claimIndex) || !contentHash) {
    return (
      <div className="p-4 text-sm text-ink-soft">
        <p className="font-semibold text-ink">Claim support unavailable</p>
        <p className="mt-2">This older claim{claimId ? ` (${claimId})` : ""} is not bound to a canonical artifact claim. Open an attested claim from the research artifact shelf.</p>
      </div>
    );
  }
  if (error) return <p role="alert" className="p-4 text-sm text-emperor">{error}</p>;
  if (!claim) return <p className="p-4 text-sm text-ink-mute">Loading authenticated claim support…</p>;

  return (
    <article className="flex h-full flex-col gap-4 overflow-y-auto p-4 text-sm">
      <div>
        <p className="text-[10px] font-semibold uppercase tracking-wide text-ocean">{claim.owner_revision ? "Archived terminal claim" : "Terminal claim"}</p>
        <h2 className="mt-1 text-base font-semibold leading-snug text-ink">{claim.claim}</h2>
        {claim.owner_revision ? (
          <aside className="mt-3 rounded border border-ink bg-white p-3">
            <p className="text-[10px] font-semibold uppercase tracking-wide text-ocean">Current owner revision</p>
            <p className="mt-1 font-semibold text-ink">{claim.owner_revision.effective_claim}</p>
            <p className="mt-1 text-xs text-ink-soft">
              {claim.owner_revision.compensations.at(-1)?.rationale ?? claim.owner_revision.rationale}
            </p>
            {claim.owner_revision.compensations.length ? (
              <ol className="mt-2 list-decimal pl-4 text-xs text-ink-soft">
                {claim.owner_revision.compensations.map((compensation) => (
                  <li key={compensation.transition_sha256}>
                    {compensation.operation === "restore_archived_terminal" ? "Restored archived wording" : "Superseded owner wording"}: {compensation.replacement_claim}
                    {" — "}{compensation.rationale}
                    {compensation.source_proposal_receipt_sha256 ? (
                      <span className="block break-all font-mono text-[10px]">
                        Consumed reviewed proposal: {compensation.source_proposal_receipt_sha256}
                      </span>
                    ) : null}
                    {" · "}<a
                      className="text-ocean underline"
                      target="_blank"
                      rel="noreferrer"
                      href={`${API_BASE}/research/${encodeURIComponent(investigationId)}/artifact/history/${compensation.prior_artifact_content_hash}`}
                    >prior HTML</a>
                  </li>
                ))}
              </ol>
            ) : null}
            <a
              className="mt-2 inline-block text-xs text-ocean underline"
              target="_blank"
              rel="noreferrer"
              href={`${API_BASE}/research/${encodeURIComponent(investigationId)}/artifact/history/${claim.owner_revision.prior_artifact_content_hash}`}
            >
              open immutable prior HTML
            </a>
            <p className="mt-1 text-[10px] text-ink-mute">Canonical owner-authored record; not archive-grounded, model-verified, provenance, or downstream authority.</p>
            <div className="mt-3 border-t border-rule pt-2">
              <label className="block text-xs font-semibold text-ink" htmlFor={`compensation-operation-${claim.claim_index}`}>Compensating operation</label>
              <select
                id={`compensation-operation-${claim.claim_index}`}
                className="mt-1 w-full rounded border border-rule bg-white p-1 text-xs"
                value={compensationOperation}
                onChange={(event) => {
                  reconsiderationGeneration.current += 1;
                  setCompensationOperation(event.target.value as typeof compensationOperation);
                  setCompensationPreview(null);
                }}
              >
                <option value="restore_archived_terminal">Restore archived terminal wording</option>
                <option value="supersede_owner_revision">Supersede with new owner wording</option>
              </select>
              {compensationOperation === "supersede_owner_revision" ? (
                <>
                  <label className="mt-2 block text-xs font-semibold text-ink" htmlFor={`compensation-replacement-${claim.claim_index}`}>Replacement owner wording</label>
                  <textarea
                    id={`compensation-replacement-${claim.claim_index}`}
                    className="mt-1 min-h-16 w-full rounded border border-rule bg-white p-2 text-xs"
                    maxLength={20_000}
                    value={compensationReplacement}
                    onChange={(event) => { reconsiderationGeneration.current += 1; setCompensationReplacement(event.target.value); setCompensationPreview(null); }}
                  />
                </>
              ) : null}
              <label className="mt-2 block text-xs font-semibold text-ink" htmlFor={`compensation-rationale-${claim.claim_index}`}>Compensation rationale</label>
              <textarea
                id={`compensation-rationale-${claim.claim_index}`}
                className="mt-1 min-h-16 w-full rounded border border-rule bg-white p-2 text-xs"
                maxLength={20_000}
                value={compensationRationale}
                onChange={(event) => { reconsiderationGeneration.current += 1; setCompensationRationale(event.target.value); setCompensationPreview(null); }}
              />
              <div className="mt-2 flex gap-2">
                <button
                  type="button"
                  disabled={reconsiderationBusy || !compensationRationale.trim() || (compensationOperation === "supersede_owner_revision" && !compensationReplacement.trim())}
                  className="rounded border border-rule bg-white px-2 py-1 text-xs font-semibold text-ocean disabled:opacity-50"
                  onClick={() => {
                    const requestGeneration = ++reconsiderationGeneration.current;
                    const mutationKey = `claim-compensation:${claim.owner_revision!.head_transition_sha256}:${compensationOperation}`;
                    setReconsiderationBusy(true);
                    setError(null);
                    void previewClaimRevisionCompensation(investigationId, claim.claim_index, {
                      content_hash: activeContentHash,
                      supersedes_transition_sha256: claim.owner_revision!.head_transition_sha256,
                      operation: compensationOperation,
                      replacement_claim: compensationOperation === "restore_archived_terminal" ? null : compensationReplacement,
                      rationale: compensationRationale,
                      mutation_key: mutationKey,
                    }).then((result) => {
                      if (reconsiderationGeneration.current === requestGeneration && result.preview) {
                        setCompensationPreview({
                          previewSha256: result.preview.preview_sha256,
                          transitionSha256: result.preview.transition_sha256,
                          priorEffectiveClaim: result.preview.prior_effective_claim,
                          replacementClaim: result.preview.replacement_claim,
                          rationale: result.preview.rationale,
                        });
                      }
                    }).catch(() => {
                      if (reconsiderationGeneration.current === requestGeneration) setError("The compensating revision preview is stale or unavailable.");
                    }).finally(() => {
                      if (reconsiderationGeneration.current === requestGeneration) setReconsiderationBusy(false);
                    });
                  }}
                >
                  preview compensating revision
                </button>
                {compensationPreview ? (
                  <aside className="w-full rounded border border-rule bg-parchment p-2 text-xs text-ink-soft">
                    <p><span className="font-semibold text-ink">Current:</span> {compensationPreview.priorEffectiveClaim}</p>
                    <p className="mt-1"><span className="font-semibold text-ink">Append:</span> {compensationPreview.replacementClaim}</p>
                    <p className="mt-1"><span className="font-semibold text-ink">Rationale:</span> {compensationPreview.rationale}</p>
                    <p className="mt-1 text-[10px] text-ink-mute">Exact server preview. Appending preserves every prior transition and immutable HTML version.</p>
                  </aside>
                ) : null}
                {compensationPreview ? (
                  <button
                    type="button"
                    disabled={reconsiderationBusy}
                    className="rounded border border-ink bg-ink px-2 py-1 text-xs font-semibold text-white disabled:opacity-50"
                    onClick={() => {
                      const requestGeneration = ++reconsiderationGeneration.current;
                      const mutationKey = `claim-compensation:${claim.owner_revision!.head_transition_sha256}:${compensationOperation}`;
                      setReconsiderationBusy(true);
                      setError(null);
                      void acceptClaimRevisionCompensation(investigationId, claim.claim_index, {
                        content_hash: activeContentHash,
                        supersedes_transition_sha256: claim.owner_revision!.head_transition_sha256,
                        operation: compensationOperation,
                        replacement_claim: compensationOperation === "restore_archived_terminal" ? null : compensationReplacement,
                        rationale: compensationRationale,
                        mutation_key: mutationKey,
                        preview_sha256: compensationPreview.previewSha256,
                        transition_sha256: compensationPreview.transitionSha256,
                      }).then((result) => {
                        if (!result.acceptance) throw new Error("missing compensation acceptance");
                        return getResearchArtifactClaim(investigationId, claim.claim_index, result.acceptance.artifact_content_hash)
                          .then((updated) => ({ updated, hash: result.acceptance!.artifact_content_hash }));
                      }).then(({ updated, hash }) => {
                        if (reconsiderationGeneration.current === requestGeneration) {
                          setClaim(updated);
                          setActiveContentHash(hash);
                          setCompensationPreview(null);
                          setCompensationRationale("");
                        }
                      }).catch(() => {
                        if (reconsiderationGeneration.current === requestGeneration) setError("The compensating owner revision was not accepted. Reload before retrying.");
                      }).finally(() => {
                        if (reconsiderationGeneration.current === requestGeneration) setReconsiderationBusy(false);
                      });
                    }}
                  >
                    append compensating revision
                  </button>
                ) : null}
              </div>
              <p className="mt-1 text-[10px] text-ink-mute">Restore appends archived wording as a new transition; it never deletes or rolls back prior decisions.</p>
            </div>
          </aside>
        ) : null}
        {iterations?.rounds.length ? (
          <section className="mt-3 rounded border border-ink/20 bg-white p-3" aria-label="Recursive owner research rounds">
            <div className="flex items-center justify-between gap-2">
              <div>
                <p className="text-[10px] font-semibold uppercase tracking-wide text-ocean">Recursive research ledger</p>
                <p className="text-xs text-ink-soft">{iterations.rounds.length} completed canonical round{iterations.rounds.length === 1 ? "" : "s"}</p>
              </div>
              {iterations.next_round_eligible ? (
                <button
                  type="button"
                  disabled={challengeBusy || reconsiderationBusy}
                  className="text-xs text-ocean underline"
                  onClick={() => {
                    reconsiderationGeneration.current += 1;
                    setOwnerContextPreview(null);
                    setChallengeGoal("Research the current owner wording again, focusing on what remains uncertain and what evidence could warrant another revision.");
                  }}
                >
                  Research current wording again
                </button>
              ) : null}
            </div>
            <div className="mt-2 rounded border border-ocean/20 bg-ice-1 p-2">
              <p className="text-xs font-semibold text-ink">Build the next round from selected reasoning</p>
              <p className="mt-1 text-[10px] text-ink-mute">Selection sends ordinal identities only. The server rebuilds exact candidate, review, proposal, and transition bytes.</p>
              <label className="mt-2 block text-xs font-semibold text-ink" htmlFor={`recursive-questions-${claim.claim_index}`}>Unresolved questions — one per line</label>
              <textarea
                id={`recursive-questions-${claim.claim_index}`}
                className="mt-1 min-h-20 w-full rounded border border-rule bg-white p-2 text-xs"
                maxLength={4000}
                disabled={recursiveBusy}
                value={recursiveQuestions}
                onChange={(event) => {
                  recursiveGeneration.current += 1;
                  setRecursiveQuestions(event.target.value);
                  setRecursivePreview(null);
                }}
              />
              <div className="mt-2 flex flex-wrap gap-2">
                <button
                  type="button"
                  disabled={recursiveBusy || !recursiveQuestions.split("\n").some((value) => value.trim())}
                  className="rounded border border-rule bg-white px-2 py-1 text-xs font-semibold text-ocean disabled:opacity-50"
                  onClick={() => {
                    const questions = recursiveQuestions.split("\n").map((value) => value.trim()).filter(Boolean);
                    const generation = ++recursiveGeneration.current;
                    setRecursiveBusy(true);
                    setRecursivePreview(null);
                    setError(null);
                    void sha256Hex(new TextEncoder().encode(JSON.stringify({ head: iterations.current_head_transition_sha256, selectedRoundOrdinals, questions })))
                      .then((intent) => previewRecursiveRoundContext(investigationId, claim.claim_index, {
                        content_hash: activeContentHash,
                        selected_round_ordinals: selectedRoundOrdinals,
                        follow_up_questions: questions,
                        mutation_key: `recursive-context:${intent}`,
                        view_mode: "floating",
                        research_tier: "deep",
                      }))
                      .then((result) => {
                        if (recursiveGeneration.current === generation && result.preview) setRecursivePreview(result.preview);
                      })
                      .catch(() => {
                        if (recursiveGeneration.current === generation) setError("The selected recursive context is stale or unavailable.");
                      })
                      .finally(() => {
                        if (recursiveGeneration.current === generation) setRecursiveBusy(false);
                      });
                  }}
                >
                  preview exact recursive context
                </button>
                {recursivePreview ? (
                  <button
                    type="button"
                    disabled={recursiveBusy}
                    className="rounded border border-ink bg-ink px-2 py-1 text-xs font-semibold text-white disabled:opacity-50"
                    onClick={() => {
                      const questions = recursiveQuestions.split("\n").map((value) => value.trim()).filter(Boolean);
                      const generation = ++recursiveGeneration.current;
                      setRecursiveBusy(true);
                      setError(null);
                      void sha256Hex(new TextEncoder().encode(JSON.stringify({ head: iterations.current_head_transition_sha256, selectedRoundOrdinals, questions })))
                        .then((intent) => acceptRecursiveRoundContext(investigationId, claim.claim_index, {
                          content_hash: activeContentHash,
                          selected_round_ordinals: selectedRoundOrdinals,
                          follow_up_questions: questions,
                          mutation_key: `recursive-context:${intent}`,
                          view_mode: "floating",
                          research_tier: "deep",
                          preview_sha256: recursivePreview.preview_sha256,
                          receipt_sha256: recursivePreview.receipt_sha256,
                        }))
                        .then((result) => {
                          if (recursiveGeneration.current !== generation || !result.reservation) return;
                          const reserved = result.reservation;
                          openDeepResearchFromHighlight({
                            asset_id: reserved.parent_asset_id,
                            selection_text: reserved.selection_text,
                            session_id: reserved.session_id,
                            spawn_id: reserved.spawn_id,
                            investigation_id: reserved.investigation_id,
                            status: reserved.status,
                            mode: reserved.view_mode,
                            model_id: reserved.model_id ?? undefined,
                            research_tier: reserved.research_tier,
                            goal: `Recursive owner claim research · ${questions.join(" · ")}`,
                            title: "Recursive owner claim research",
                            claim_challenge: reserved.claim_challenge,
                          });
                          setRecursivePreview(null);
                        })
                        .catch(() => {
                          if (recursiveGeneration.current === generation) setError("The recursive context was not reserved. Reopen the current artifact before retrying.");
                        })
                        .finally(() => {
                          if (recursiveGeneration.current === generation) setRecursiveBusy(false);
                        });
                    }}
                  >
                    confirm and reserve recursive research
                  </button>
                ) : null}
              </div>
              {recursivePreview ? (
                <p className="mt-2 text-[10px] text-ink-mute">Exact pack {recursivePreview.pack_sha256.slice(0, 12)}… · {recursivePreview.pack_bytes} bytes · {recursivePreview.selected_round_ordinals.length} selected rounds · no provider call, spend, evidence, graph, Write, benchmark, twin, or publication authority.</p>
              ) : null}
            </div>
            <ol className="mt-2 space-y-2">
              {iterations.rounds.map((round) => (
                <li key={round.transition_sha256} className="rounded border border-ink/15 p-2 text-xs">
                  <label className="mb-1 flex items-center gap-2 text-[10px] font-semibold text-ocean">
                    <input
                      type="checkbox"
                      aria-label={`include round ${round.ordinal} in recursive context`}
                      disabled={recursiveBusy}
                      checked={selectedRoundOrdinals.includes(round.ordinal)}
                      onChange={(event) => {
                        recursiveGeneration.current += 1;
                        setRecursivePreview(null);
                        setSelectedRoundOrdinals((current) => event.target.checked
                          ? [...current, round.ordinal].sort((a, b) => a - b)
                          : current.filter((ordinal) => ordinal !== round.ordinal));
                      }}
                    />
                    include in next context
                  </label>
                  <details>
                    <summary className="cursor-pointer font-semibold text-ink">Round {round.ordinal}: {round.prior_effective_claim} → {round.replacement_claim}</summary>
                    <div className="mt-2 space-y-1 text-ink-soft">
                      <p><strong>Purpose:</strong> {round.purpose}</p>
                      <p><strong>Question:</strong> {round.question}</p>
                      <p><strong>Model/tier:</strong> {round.model_id ?? "default"} · {round.research_tier}</p>
                      <p><strong>Archived evidence baseline:</strong> {round.archived_claim}</p>
                      <p><strong>Then-current owner wording:</strong> {round.prior_effective_claim}</p>
                      <pre className="whitespace-pre-wrap"><strong>Research candidate:</strong> {round.candidate_text}</pre>
                      <p><strong>Owner review:</strong> {round.review_rationale}</p>
                      <p><strong>Accepted proposal:</strong> {round.proposed_claim}</p>
                      <p className="break-all font-mono text-[10px]">Context {round.context_receipt_sha256}<br />Review {round.review_receipt_sha256}<br />Proposal {round.proposal_receipt_sha256}<br />Transition {round.transition_sha256}</p>
                      <p><a className="text-ocean underline" href={round.prior_html_url} target="_blank" rel="noreferrer">prior HTML</a>{" · "}<a className="text-ocean underline" href={round.result_html_url} target="_blank" rel="noreferrer">result HTML</a></p>
                      <p>Owner-authored iteration only — not archived evidence or downstream authority.</p>
                    </div>
                  </details>
                </li>
              ))}
            </ol>
            {ancestry?.nodes.length ? (
              <section aria-label="Reasoning ancestry" className="mt-3 border-t border-rule pt-3">
                <div className="flex items-center justify-between gap-2">
                  <div>
                    <p className="text-[10px] font-semibold uppercase tracking-wide text-ocean">Reasoning ancestry</p>
                    <p className="text-[10px] text-ink-mute">Receipt-derived parent paths; graph {ancestry.graph_sha256.slice(0, 12)}…</p>
                  </div>
                </div>
                <div className="mt-2 rounded border border-ocean/20 bg-ice-1 p-2">
                  <p className="text-xs font-semibold text-ink">Interrogate completed branches together</p>
                  <p className="mt-1 text-[10px] text-ink-mute">Select terminal branches only. The server derives their exact ancestor union and immutable collective membership.</p>
                  <label className="mt-2 block text-xs font-semibold text-ink" htmlFor={`ancestry-interrogation-question-${claim.claim_index}`}>Collective interrogation question</label>
                  <textarea
                    id={`ancestry-interrogation-question-${claim.claim_index}`}
                    className="mt-1 min-h-16 w-full rounded border border-rule bg-white p-2 text-xs"
                    maxLength={4000}
                    disabled={interrogationBusy}
                    value={interrogationQuestion}
                    onChange={(event) => {
                      interrogationGeneration.current += 1;
                      setInterrogationQuestion(event.target.value);
                      setInterrogationPreview(null);
                    }}
                  />
                  <div className="mt-2 flex flex-wrap gap-2">
                    <button
                      type="button"
                      disabled={interrogationBusy || !interrogationTerminals.length || !interrogationQuestion.trim()}
                      className="rounded border border-rule bg-white px-2 py-1 text-xs font-semibold text-ocean disabled:opacity-50"
                      onClick={() => {
                        const generation = ++interrogationGeneration.current;
                        const terminals = [...interrogationTerminals].sort((a, b) => a - b);
                        const question = interrogationQuestion.trim();
                        setInterrogationBusy(true);
                        setInterrogationPreview(null);
                        setError(null);
                        void sha256Hex(new TextEncoder().encode(JSON.stringify({ head: ancestry.current_head_transition_sha256, terminals, question })))
                          .then((intent) => previewReasoningAncestryInterrogation(investigationId, claim.claim_index, {
                            content_hash: activeContentHash,
                            selected_terminal_ordinals: terminals,
                            question,
                            mutation_key: `ancestry-interrogation:${intent}`,
                          }))
                          .then((result) => {
                            if (interrogationGeneration.current === generation) setInterrogationPreview(result);
                          })
                          .catch(() => {
                            if (interrogationGeneration.current === generation) setError("The selected reasoning branches are stale or unavailable.");
                          })
                          .finally(() => {
                            if (interrogationGeneration.current === generation) setInterrogationBusy(false);
                          });
                      }}
                    >preview collective interrogation</button>
                    {interrogationPreview ? (
                      <button
                        type="button"
                        disabled={interrogationBusy}
                        className="rounded border border-ink bg-ink px-2 py-1 text-xs font-semibold text-white disabled:opacity-50"
                        onClick={() => {
                          const generation = ++interrogationGeneration.current;
                          const terminals = [...interrogationTerminals].sort((a, b) => a - b);
                          const question = interrogationQuestion.trim();
                          setInterrogationBusy(true);
                          setError(null);
                          void sha256Hex(new TextEncoder().encode(JSON.stringify({ head: ancestry.current_head_transition_sha256, terminals, question })))
                            .then((intent) => acceptReasoningAncestryInterrogation(investigationId, claim.claim_index, {
                              content_hash: activeContentHash,
                              selected_terminal_ordinals: terminals,
                              question,
                              mutation_key: `ancestry-interrogation:${intent}`,
                              preview_sha256: interrogationPreview.preview_sha256,
                              receipt_sha256: interrogationPreview.receipt.receipt_sha256,
                            }))
                            .then((result) => {
                              if (interrogationGeneration.current !== generation || result.status !== "accepted") return;
                              openWindow("collective_unit", {
                                resume_ref: { manifest_id: result.manifest.manifest_id },
                                interrogation_ref: {
                                  investigation_id: investigationId,
                                  receipt_id: result.receipt.receipt_id,
                                },
                              }, {
                                id: `win:collective_unit:${result.manifest.manifest_id}`,
                                title: "Reasoning ancestry collective",
                                mode: "floating",
                              });
                              setInterrogationPreview(null);
                            })
                            .catch(() => {
                              if (interrogationGeneration.current === generation) setError("The collective interrogation was not accepted.");
                            })
                            .finally(() => {
                              if (interrogationGeneration.current === generation) setInterrogationBusy(false);
                            });
                        }}
                      >confirm and open collective</button>
                    ) : null}
                  </div>
                  {interrogationPreview ? (
                    <p className="mt-2 text-[10px] text-ink-mute">Exact closure {interrogationPreview.receipt.closure_ordinals.join(", ")} · manifest {interrogationPreview.manifest.manifest_id} · no provider call, spend, evidence, graph, Write, benchmark, or publication authority.</p>
                  ) : null}
                </div>
                <ol className="mt-2 space-y-2">
                  {ancestry.nodes.map((node) => (
                    <li key={node.ancestry_sha256} className="rounded border border-ink/15 p-2 text-xs">
                      {!node.child_ordinals.length ? (
                        <label className="mb-1 flex items-center gap-2 text-[10px] font-semibold text-ocean">
                          <input
                            type="checkbox"
                            aria-label={`select terminal branch ${node.ordinal} for collective interrogation`}
                            disabled={interrogationBusy}
                            checked={interrogationTerminals.includes(node.ordinal)}
                            onChange={(event) => {
                              interrogationGeneration.current += 1;
                              setInterrogationPreview(null);
                              setInterrogationTerminals((current) => event.target.checked
                                ? [...current, node.ordinal].sort((a, b) => a - b)
                                : current.filter((ordinal) => ordinal !== node.ordinal));
                            }}
                          />
                          select terminal branch
                        </label>
                      ) : null}
                      <details id={`reasoning-ancestry-round-${node.ordinal}`}>
                        <summary className="cursor-pointer font-semibold text-ink">
                          Round {node.ordinal} · depth {node.depth}{node.is_recombination ? " · recombination" : node.is_root ? " · root" : ""}
                        </summary>
                        <div className="mt-2 space-y-1 text-ink-soft">
                          <p><strong>Parents:</strong> {node.parent_ordinals.length ? node.parent_ordinals.map((ordinal) => (
                            <button key={ordinal} type="button" className="ml-1 text-ocean underline" onClick={() => {
                              const target = document.getElementById(`reasoning-ancestry-round-${ordinal}`) as HTMLDetailsElement | null;
                              if (target) { target.open = true; target.querySelector("summary")?.focus(); }
                            }}>round {ordinal}</button>
                          )) : "none"}</p>
                          <p><strong>Children:</strong> {node.child_ordinals.length ? node.child_ordinals.map((ordinal) => (
                            <button key={ordinal} type="button" className="ml-1 text-ocean underline" onClick={() => {
                              const target = document.getElementById(`reasoning-ancestry-round-${ordinal}`) as HTMLDetailsElement | null;
                              if (target) { target.open = true; target.querySelector("summary")?.focus(); }
                            }}>round {ordinal}</button>
                          )) : "none"}</p>
                          <p><strong>Inherited questions:</strong> {node.inherited_questions.length ? node.inherited_questions.join(" · ") : "none"}</p>
                          <p className="break-all font-mono text-[10px]">Ancestry {node.ancestry_sha256}<br />Pack {node.recursive_pack_receipt_sha256 ?? "ordinary root"}</p>
                          <p><a className="text-ocean underline" href={node.prior_html_url} target="_blank" rel="noreferrer">prior HTML</a>{" · "}<a className="text-ocean underline" href={node.result_html_url} target="_blank" rel="noreferrer">result HTML</a></p>
                          <button
                            type="button"
                            disabled={recursiveBusy}
                            className="rounded border border-rule bg-white px-2 py-1 font-semibold text-ocean"
                            onClick={() => {
                              recursiveGeneration.current += 1;
                              const included = new Set<number>();
                              const pending = [node.ordinal];
                              while (pending.length) {
                                const ordinal = pending.pop()!;
                                if (included.has(ordinal)) continue;
                                included.add(ordinal);
                                pending.push(...(ancestry.nodes.find((candidate) => candidate.ordinal === ordinal)?.parent_ordinals ?? []));
                              }
                              setSelectedRoundOrdinals([...included].sort((a, b) => a - b));
                              setRecursiveQuestions(node.inherited_questions.join("\n"));
                              setRecursivePreview(null);
                            }}
                          >use this ancestry path</button>
                          <p>No evidence, graph-admission, Write, benchmark, publication, provider-call, or spend authority.</p>
                        </div>
                      </details>
                    </li>
                  ))}
                </ol>
              </section>
            ) : null}
          </section>
        ) : null}
      </div>
      <section>
        <h3 className="text-xs font-semibold uppercase tracking-wide text-ink-soft">Direct evidence</h3>
        {claim.direct_evidence.length ? (
          <ul className="mt-2 flex flex-col gap-1">
            {claim.direct_evidence.map((evidence) => (
              <li key={evidence.receipt_sha256} className="rounded border border-rule bg-ice-1 px-2 py-2 text-xs">
                <p className="font-mono text-ink">{evidence.chunk_ids.join(", ")}</p>
                <button
                  type="button"
                  className="mt-1 rounded border border-rule bg-white px-2 py-1 font-sans text-ocean hover:bg-sun/10"
                  onClick={() => openHostedDocumentPanel({
                    documentId: evidence.document_id,
                    chunkIds: evidence.chunk_ids,
                    citationReceiptSha256: evidence.receipt_sha256,
                    title: "Claim evidence",
                  })}
                >
                  open source in canonical HTML
                </button>
              </li>
            ))}
          </ul>
        ) : <p className="mt-1 text-ink-mute">No reopenable direct evidence attested.</p>}
        {claim.supporting_path_indices.length ? <p className="mt-2 text-xs text-ink-mute">Reasoning paths: {claim.supporting_path_indices.join(", ")}</p> : null}
      </section>
      <section className="rounded border border-rule bg-sun/10 px-3 py-3">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-ink-soft">Advisory evaluation</h3>
        {claim.evaluation && !claim.owner_revision ? (
          <div className="mt-2 text-xs">
            <p className="font-semibold text-ink">{claim.evaluation.relation === "entailed" ? "Evidence entails this claim" : claim.evaluation.relation === "contradicted" ? "Evidence contradicts this claim" : claim.evaluation.relation === "not_established" ? "Entailment not established" : "Typed relation unavailable"}</p>
            <p className="mt-1 text-ink-mute">Score {claim.evaluation.score.toFixed(2)} · threshold {claim.evaluation.supported_threshold.toFixed(2)} · {claim.evaluation.backend} / {claim.evaluation.scorer_id}</p>
            <p className="mt-1 text-ink-mute">Advisory only — this signal does not change provenance or permission to read a source.</p>
          </div>
        ) : <p className="mt-1 text-xs text-ink-mute">No exact-event evaluation is available for this artifact claim.</p>}
        {claim.evaluation ? (
          <div className="mt-3 border-t border-rule pt-3">
            <label className="block text-xs font-semibold text-ink" htmlFor={`claim-challenge-${claim.claim_index}`}>Challenge goal</label>
            <textarea
              id={`claim-challenge-${claim.claim_index}`}
              className="mt-1 min-h-20 w-full rounded border border-rule bg-white p-2 text-xs"
              maxLength={4000}
              value={challengeGoal}
              onChange={(event) => {
                reconsiderationGeneration.current += 1;
                setChallengeGoal(event.target.value);
                setOwnerContextPreview(null);
              }}
            />
            {claim.owner_revision ? (
              <>
                <button
                  type="button"
                  disabled={challengeBusy || !challengeGoal.trim()}
                  className="mt-2 rounded border border-rule bg-white px-2 py-1 text-xs font-semibold text-ocean disabled:opacity-50"
                  onClick={() => {
                    const requestGeneration = ++reconsiderationGeneration.current;
                    setChallengeBusy(true);
                    setError(null);
                    void ownerContextMutationKey(claim.owner_revision!.head_transition_sha256, challengeGoal).then((mutationKey) =>
                      previewEffectiveOwnerContext(investigationId, claim.claim_index, {
                        content_hash: activeContentHash,
                        goal: challengeGoal,
                        mutation_key: mutationKey,
                        view_mode: "floating",
                        research_tier: "deep",
                      }),
                    ).then((result) => {
                      if (reconsiderationGeneration.current !== requestGeneration || !result.preview) return;
                      setOwnerContextPreview({
                        previewSha256: result.preview.preview_sha256,
                        receiptSha256: result.preview.receipt_sha256,
                        archivedClaim: result.preview.archived_claim,
                        effectiveClaim: result.preview.effective_claim,
                        headTransitionSha256: result.preview.head_transition_sha256,
                      });
                    }).catch(() => {
                      if (reconsiderationGeneration.current === requestGeneration) setError("The effective owner-claim context preview is stale or unavailable.");
                    }).finally(() => {
                      if (reconsiderationGeneration.current === requestGeneration) setChallengeBusy(false);
                    });
                  }}
                >
                  preview owner-claim research context
                </button>
                {ownerContextPreview ? (
                  <aside className="mt-2 rounded border border-rule bg-white p-2 text-xs text-ink-soft">
                    <p><span className="font-semibold text-ink">Archived evidence baseline:</span> {ownerContextPreview.archivedClaim}</p>
                    <p className="mt-1"><span className="font-semibold text-ink">Selected owner-authored current wording:</span> {ownerContextPreview.effectiveClaim}</p>
                    <p className="mt-1 text-[10px] text-ink-mute">Exact head {ownerContextPreview.headTransitionSha256.slice(0, 12)}… · not archive-grounded · no provider call or spend.</p>
                    <button
                      type="button"
                      disabled={challengeBusy}
                      className="mt-2 rounded border border-ink bg-ink px-2 py-1 font-semibold text-white disabled:opacity-50"
                      onClick={() => {
                        const requestGeneration = ++reconsiderationGeneration.current;
                        setChallengeBusy(true);
                        setError(null);
                        void ownerContextMutationKey(claim.owner_revision!.head_transition_sha256, challengeGoal).then((mutationKey) =>
                          acceptEffectiveOwnerContext(investigationId, claim.claim_index, {
                            content_hash: activeContentHash,
                            goal: challengeGoal,
                            mutation_key: mutationKey,
                            view_mode: "floating",
                            research_tier: "deep",
                            preview_sha256: ownerContextPreview.previewSha256,
                            receipt_sha256: ownerContextPreview.receiptSha256,
                          }),
                        ).then((result) => {
                          if (reconsiderationGeneration.current !== requestGeneration || !result.reservation) return;
                          const reserved = result.reservation;
                          openDeepResearchFromHighlight({
                            asset_id: reserved.parent_asset_id,
                            selection_text: reserved.selection_text,
                            session_id: reserved.session_id,
                            spawn_id: reserved.spawn_id,
                            investigation_id: reserved.investigation_id,
                            status: reserved.status,
                            mode: reserved.view_mode,
                            model_id: reserved.model_id ?? undefined,
                            research_tier: reserved.research_tier,
                            goal: `Effective owner claim research · ${challengeGoal.trim()}`,
                            title: "Owner claim research",
                            claim_challenge: reserved.claim_challenge,
                          });
                          setOwnerContextPreview(null);
                        }).catch(() => {
                          if (reconsiderationGeneration.current === requestGeneration) setError("The owner-claim context was not accepted. Reload the current artifact before retrying.");
                        }).finally(() => {
                          if (reconsiderationGeneration.current === requestGeneration) setChallengeBusy(false);
                        });
                      }}
                    >
                      accept context and reserve candidate research
                    </button>
                  </aside>
                ) : null}
              </>
            ) : (
            <button
              type="button"
              disabled={challengeBusy || !challengeGoal.trim()}
              className="mt-2 rounded border border-rule bg-white px-2 py-1 text-xs font-semibold text-ocean disabled:opacity-50"
              onClick={() => {
                setChallengeBusy(true);
                setError(null);
                void reserveResearchArtifactClaimChallenge(investigationId, claim.claim_index, {
                  content_hash: contentHash,
                  goal: challengeGoal,
                  view_mode: "floating",
                  research_tier: "deep",
                }).then((reserved) => {
                  openDeepResearchFromHighlight({
                    asset_id: reserved.parent_asset_id,
                    selection_text: reserved.selection_text,
                    session_id: reserved.session_id,
                    spawn_id: reserved.spawn_id,
                    investigation_id: reserved.investigation_id,
                    status: reserved.status,
                    mode: reserved.view_mode,
                    model_id: reserved.model_id ?? undefined,
                    research_tier: reserved.research_tier,
                    goal: `Claim challenge · ${challengeGoal.trim()}`,
                    title: "Claim challenge research",
                    claim_challenge: reserved.claim_challenge,
                  });
                }).catch(() => {
                  setError("The exact claim challenge could not be reserved. Reopen the current artifact and evidence before retrying.");
                }).finally(() => setChallengeBusy(false));
              }}
            >
              {challengeBusy ? "reserving challenge…" : "reserve separate challenge research"}
            </button>
            )}
            <p className="mt-1 text-xs text-ink-mute">Reservation makes no model call and cannot replace this terminal claim. Any result remains a separate candidate until an explicit future acceptance step.</p>
          </div>
        ) : null}
      </section>
      <section className="rounded border border-ocean/30 bg-ocean/5 px-3 py-3">
        <div className="flex items-center justify-between gap-2">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-ink-soft">
            Later owner reviews
          </h3>
          <a
            href={`${API_BASE}/research/${encodeURIComponent(investigationId)}/artifact/reviewed-view?content_hash=${encodeURIComponent(activeContentHash)}#claim-review-${claim.claim_index}`}
            target="_blank"
            rel="noreferrer"
            className="text-xs text-ocean underline"
          >
            open reviewed HTML overlay
          </a>
        </div>
        {(claim.reviews ?? []).length ? (
          <ul className="mt-2 flex flex-col gap-2">
            {(claim.reviews ?? []).map((review) => (
              <li
                key={review.acceptance_receipt_sha256}
                className="rounded border border-ocean/20 bg-white px-2 py-2"
                data-epistemic-status={review.status}
              >
                <p className="text-xs font-semibold text-ocean">
                  {review.status === "later_owner_reversed_counter_analysis"
                    ? "Reversed later counter-analysis — retained as history"
                    : "Owner-accepted later counter-analysis"}
                </p>
                <pre className="mt-1 whitespace-pre-wrap text-xs text-ink">
                  {review.candidate_text}
                </pre>
                <p className="mt-1 font-mono text-[10px] text-ink-mute">
                  acceptance {review.acceptance_receipt_sha256.slice(0, 12)}…
                  {review.reversal_receipt_sha256
                    ? ` · reversal ${review.reversal_receipt_sha256.slice(0, 12)}…`
                    : ""}
                </p>
                <p className="mt-1 text-[10px] text-ink-mute">
                  Later review only — not provenance, verification, source permission, or merge authority.
                </p>
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-1 text-xs text-ink-mute">
            No accepted later counter-analysis is bound to this exact claim and evidence set.
          </p>
        )}
      </section>
      <section className="rounded border border-ink/20 bg-ice-1 px-3 py-3">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-ink-soft">
          Claim reconsideration proposals
        </h3>
        {(claim.reconsiderations ?? []).map((proposal) => (
          <article key={proposal.receipt_sha256} className="mt-2 rounded border border-rule bg-white p-2">
            <p className="text-xs font-semibold text-ink">Owner-authored proposal — not terminal truth</p>
            <pre className="mt-1 whitespace-pre-wrap text-xs text-ink">{proposal.proposed_claim}</pre>
            <p className="mt-1 text-xs text-ink-soft">{proposal.rationale}</p>
            <p className="mt-1 font-mono text-[10px] text-ink-mute">proposal {proposal.receipt_sha256.slice(0, 12)}…</p>
            <p className="mt-1 text-[10px] text-ink-mute">No provenance, merge, graph, benchmark, publication, model-call, or spend authority.</p>
            <div className="mt-2 flex gap-2">
              <button
                type="button"
                disabled={reconsiderationBusy}
                className="rounded border border-rule bg-white px-2 py-1 text-xs font-semibold text-ocean disabled:opacity-50"
                onClick={() => {
                  const requestGeneration = ++reconsiderationGeneration.current;
                  const mutationKey = `claim-revision:${proposal.receipt_sha256}`;
                  setReconsiderationBusy(true);
                  setRevisionPreview(null);
                  setError(null);
                  void previewClaimRevision(investigationId, claim.claim_index, {
                    content_hash: activeContentHash,
                    proposal_receipt_sha256: proposal.receipt_sha256,
                    mutation_key: mutationKey,
                  }).then((result) => {
                    if (reconsiderationGeneration.current === requestGeneration && result.preview) {
                      setRevisionPreview({ previewSha256: result.preview.preview_sha256, transitionSha256: result.preview.transition_sha256 });
                    }
                  }).catch(() => {
                    if (reconsiderationGeneration.current === requestGeneration) setError("The canonical revision preview is stale or unavailable.");
                  }).finally(() => {
                    if (reconsiderationGeneration.current === requestGeneration) setReconsiderationBusy(false);
                  });
                }}
              >
                preview canonical revision
              </button>
              {revisionPreview ? (
                <button
                  type="button"
                  disabled={reconsiderationBusy}
                  className="rounded border border-ink bg-ink px-2 py-1 text-xs font-semibold text-white disabled:opacity-50"
                  onClick={() => {
                    const requestGeneration = ++reconsiderationGeneration.current;
                    const mutationKey = `claim-revision:${proposal.receipt_sha256}`;
                    setReconsiderationBusy(true);
                    setError(null);
                    void acceptClaimRevision(investigationId, claim.claim_index, {
                      content_hash: activeContentHash,
                      proposal_receipt_sha256: proposal.receipt_sha256,
                      mutation_key: mutationKey,
                      preview_sha256: revisionPreview.previewSha256,
                      transition_sha256: revisionPreview.transitionSha256,
                    }).then((result) => {
                      if (!result.acceptance) throw new Error("missing acceptance");
                      return getResearchArtifactClaim(investigationId, claim.claim_index, result.acceptance.artifact_content_hash)
                        .then((updated) => ({ updated, hash: result.acceptance!.artifact_content_hash }));
                    }).then(({ updated, hash }) => {
                      if (reconsiderationGeneration.current === requestGeneration) {
                        setClaim(updated);
                        setActiveContentHash(hash);
                        setRevisionPreview(null);
                      }
                    }).catch(() => {
                      if (reconsiderationGeneration.current === requestGeneration) setError("The canonical owner revision was not accepted. Reload the artifact before retrying.");
                    }).finally(() => {
                      if (reconsiderationGeneration.current === requestGeneration) setReconsiderationBusy(false);
                    });
                  }}
                >
                  accept as canonical owner revision
                </button>
              ) : null}
            </div>
            {revisionPreview ? <p className="mt-1 text-[10px] text-ink-mute">Exact prospective artifact verified. Acceptance preserves immutable prior HTML and does not rewrite archived claim evidence.</p> : null}
          </article>
        ))}
        {!(claim.reconsiderations ?? []).length ? (
          <div className="mt-2 border-t border-rule pt-2">
            <fieldset>
              <legend className="text-xs font-semibold text-ink">Select accepted later reviews</legend>
              {(claim.reviews ?? []).filter((review) => review.status === "later_owner_accepted_counter_analysis").map((review) => (
                <label key={review.acceptance_receipt_sha256} className="mt-1 flex items-start gap-2 text-xs text-ink">
                  <input
                    type="checkbox"
                    checked={selectedReviews.includes(review.acceptance_receipt_sha256)}
                    onChange={(event) => {
                      reconsiderationGeneration.current += 1;
                      setReconsiderationPreview(null);
                      setSelectedReviews((current) => event.target.checked
                        ? [...current, review.acceptance_receipt_sha256]
                        : current.filter((receipt) => receipt !== review.acceptance_receipt_sha256));
                    }}
                  />
                  <span>{review.candidate_text}</span>
                </label>
              ))}
            </fieldset>
            <label className="mt-2 block text-xs font-semibold text-ink" htmlFor={`proposed-claim-${claim.claim_index}`}>Proposed replacement wording</label>
            <textarea
              id={`proposed-claim-${claim.claim_index}`}
              className="mt-1 min-h-20 w-full rounded border border-rule bg-white p-2 text-xs"
              maxLength={20_000}
              value={proposedClaim}
              onChange={(event) => { reconsiderationGeneration.current += 1; setProposedClaim(event.target.value); setReconsiderationPreview(null); }}
            />
            <label className="mt-2 block text-xs font-semibold text-ink" htmlFor={`reconsideration-rationale-${claim.claim_index}`}>Owner rationale</label>
            <textarea
              id={`reconsideration-rationale-${claim.claim_index}`}
              className="mt-1 min-h-16 w-full rounded border border-rule bg-white p-2 text-xs"
              maxLength={20_000}
              value={reconsiderationRationale}
              onChange={(event) => { reconsiderationGeneration.current += 1; setReconsiderationRationale(event.target.value); setReconsiderationPreview(null); }}
            />
            <div className="mt-2 flex gap-2">
              <button
                type="button"
                disabled={reconsiderationBusy || !selectedReviews.length || !proposedClaim.trim() || !reconsiderationRationale.trim()}
                className="rounded border border-rule bg-white px-2 py-1 text-xs font-semibold text-ocean disabled:opacity-50"
                onClick={() => {
                  const requestGeneration = ++reconsiderationGeneration.current;
                  setReconsiderationBusy(true);
                  setError(null);
                  void previewClaimReconsideration(investigationId, claim.claim_index, {
                    content_hash: activeContentHash,
                    acceptance_receipt_sha256s: selectedReviews,
                    proposed_claim: proposedClaim,
                    rationale: reconsiderationRationale,
                  }).then((result) => {
                    if (reconsiderationGeneration.current === requestGeneration) {
                      setReconsiderationPreview(result.preview?.preview_sha256 ?? null);
                    }
                  }).catch(() => {
                    if (reconsiderationGeneration.current === requestGeneration) {
                      setError("The reconsideration preview is stale or unavailable. Reload the exact claim before retrying.");
                    }
                  }).finally(() => {
                    if (reconsiderationGeneration.current === requestGeneration) setReconsiderationBusy(false);
                  });
                }}
              >
                {reconsiderationBusy ? "checking…" : "preview exact proposal"}
              </button>
              {reconsiderationPreview ? (
                <button
                  type="button"
                  disabled={reconsiderationBusy}
                  className="rounded border border-ink bg-ink px-2 py-1 text-xs font-semibold text-white disabled:opacity-50"
                  onClick={() => {
                    const previewSha = reconsiderationPreview;
                    const requestGeneration = ++reconsiderationGeneration.current;
                    setReconsiderationBusy(true);
                    setError(null);
                    void createClaimReconsideration(investigationId, claim.claim_index, {
                      content_hash: activeContentHash,
                      acceptance_receipt_sha256s: selectedReviews,
                      proposed_claim: proposedClaim,
                      rationale: reconsiderationRationale,
                      preview_sha256: previewSha,
                      mutation_key: `claim-reconsideration:${previewSha}`,
                    }).then(() => getResearchArtifactClaim(investigationId, claim.claim_index, activeContentHash))
                      .then((updated) => {
                        if (reconsiderationGeneration.current === requestGeneration) {
                          setClaim(updated);
                          setReconsiderationPreview(null);
                        }
                      }).catch(() => {
                        if (reconsiderationGeneration.current === requestGeneration) {
                          setError("The reconsideration proposal was not created. Reload the exact claim before retrying.");
                        }
                      }).finally(() => {
                        if (reconsiderationGeneration.current === requestGeneration) setReconsiderationBusy(false);
                      });
                  }}
                >
                  create immutable proposal
                </button>
              ) : null}
            </div>
            {reconsiderationPreview ? (
              <aside className="mt-2 rounded border border-ocean/30 bg-white p-2" aria-label="exact reconsideration preview">
                <p className="text-xs font-semibold text-ocean">Exact server preview ready — proposal only</p>
                <pre className="mt-1 whitespace-pre-wrap text-xs text-ink">{proposedClaim}</pre>
                <p className="mt-1 text-xs text-ink-soft">{reconsiderationRationale}</p>
                <p className="mt-1 font-mono text-[10px] text-ink-mute">preview {reconsiderationPreview.slice(0, 12)}…</p>
              </aside>
            ) : null}
            <p className="mt-1 text-[10px] text-ink-mute">Preview writes nothing. Creation records a proposal only; it does not replace the terminal claim or call a model.</p>
          </div>
        ) : null}
      </section>
      <section>
        <h3 className="text-xs font-semibold uppercase tracking-wide text-ink-soft">Inherited knowledge dependencies</h3>
        {claim.inherited_support.length ? (
          <ul className="mt-2 flex flex-col gap-2">
            {claim.inherited_support.map((support) => (
              <li key={`${support.supporting_leaf_investigation_id}:${support.unit_id}`} className="rounded border border-rule px-2 py-2">
                <p className="font-mono text-xs text-ink">{support.unit_id}</p>
                <p className="mt-1 text-xs font-semibold text-sun-deep">{qualificationCopy[support.qualification_state]}</p>
                <p className="text-xs text-ink-mute">supporting leaf: {support.supporting_leaf_investigation_id}</p>
                {support.source_investigation_id ? <p className="text-xs text-ink-mute">source research: {support.source_investigation_id}</p> : null}
              </li>
            ))}
          </ul>
        ) : <p className="mt-1 text-ink-mute">No inherited knowledge dependency attested.</p>}
      </section>
      <p className="border-t border-rule pt-3 text-xs text-ink-mute">Support edges are provenance. Entailment and contradiction judgments are separate evaluations and are not shown unless bound to this exact claim and evidence set.</p>
    </article>
  );
}
