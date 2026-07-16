import { useEffect, useMemo, useRef, useState } from "react";

import {
  attestMultimediaVisualCandidate,
  authorizeMultimediaVisual,
  materializeMultimediaVisualCandidates,
  pollMultimediaVisualGeneration,
  previewMultimediaVisualCandidate,
  registerMultimediaReviewedVisuals,
  submitMultimediaVisualGeneration,
} from "../../api/multimedia";
import type {
  MultimediaAssetRecord,
  MultimediaReviewedVisualSet,
  MultimediaVisualAuthorization,
  MultimediaVisualCandidate,
  MultimediaVisualGeneration,
} from "../../api/multimedia";
import { LemonButton, LemonTag } from "../../components/lemon";
import { emitWernerExperience } from "../../werner/reactionBus";
import { projectMultimediaPlan } from "./planProjection";

type Pending = "authorize" | "submit" | "poll" | "materialize" | "attest" | null;

type ChapterReview = {
  authority?: MultimediaVisualAuthorization;
  generation?: MultimediaVisualGeneration;
  candidates: MultimediaVisualCandidate[];
  previewUrls: Record<string, string>;
  attestedCandidateIds: string[];
  selectedCandidateId?: string;
  pending: Pending;
  error?: string;
};

const EMPTY: ChapterReview = {
  candidates: [],
  previewUrls: {},
  attestedCandidateIds: [],
  pending: null,
};

function requestId(assetId: string, revisionId: string, chapterId: string): string {
  return `visual-${assetId}-${revisionId}-${chapterId}`
    .replace(/[^A-Za-z0-9._:-]/g, "-")
    .slice(0, 128);
}

function message(error: unknown): string {
  const code = error instanceof Error ? error.message : "";
  if (code.includes("runtime_unavailable")) return "Visual production is not configured on this server.";
  if (code.includes("unavailable")) return "This visual is no longer available for the current revision.";
  if (code.includes("conflict")) return "The visual state changed. Reopen the asset before continuing.";
  return "The visual command did not complete. Retry the current step.";
}

export function VisualReviewPanel({
  record,
  reviewedSet,
  onRegistered,
}: {
  record: MultimediaAssetRecord;
  reviewedSet: MultimediaReviewedVisualSet | null;
  onRegistered: (value: MultimediaReviewedVisualSet) => void;
}) {
  const epoch = useRef(0);
  const ownedPreviewUrls = useRef(new Set<string>());
  const lifetimeIdentity = `${record.asset.asset_id}\0${record.asset.revision_id}`;
  const previousIdentity = useRef(lifetimeIdentity);
  if (previousIdentity.current !== lifetimeIdentity) {
    previousIdentity.current = lifetimeIdentity;
    epoch.current += 1;
  }
  const [activeChapterId, setActiveChapterId] = useState("");
  const [ceilingUsd, setCeilingUsd] = useState("0.50");
  const [spendAcknowledged, setSpendAcknowledged] = useState(false);
  const [provenanceAcknowledged, setProvenanceAcknowledged] = useState(false);
  const [reviews, setReviews] = useState<Record<string, ChapterReview>>({});
  const [registering, setRegistering] = useState(false);
  const [registerError, setRegisterError] = useState<string | null>(null);

  const projection = useMemo(() => projectMultimediaPlan(record.plan), [record.plan]);
  const chapters = projection.ok ? projection.value.chapters : [];

  useEffect(() => {
    setActiveChapterId(chapters[0]?.id ?? "");
    setReviews({});
    setSpendAcknowledged(false);
    setProvenanceAcknowledged(false);
    setRegisterError(null);
    return () => {
      ownedPreviewUrls.current.forEach((url) => URL.revokeObjectURL(url));
      ownedPreviewUrls.current.clear();
    };
  }, [record.asset.asset_id, record.asset.revision_id]);

  useEffect(() => {
    setSpendAcknowledged(false);
    setProvenanceAcknowledged(false);
  }, [activeChapterId]);

  const activeReview = reviews[activeChapterId] ?? EMPTY;
  const complete = chapters.length > 0 && chapters.every(
    (chapter) => reviews[chapter.id]?.selectedCandidateId,
  );

  function update(chapterId: string, patch: Partial<ChapterReview>) {
    setReviews((current) => ({
      ...current,
      [chapterId]: { ...(current[chapterId] ?? EMPTY), ...patch },
    }));
  }

  async function command(
    chapterId: string,
    pending: Exclude<Pending, null>,
    work: (isCurrent: () => boolean) => Promise<void>,
  ) {
    const started = epoch.current;
    update(chapterId, { pending, error: undefined });
    try {
      await work(() => started === epoch.current);
    } catch (error) {
      if (started === epoch.current) update(chapterId, { error: message(error) });
    } finally {
      if (started === epoch.current) update(chapterId, { pending: null });
    }
  }

  async function authorize() {
    const microdollars = Math.round(Number(ceilingUsd) * 1_000_000);
    if (!Number.isSafeInteger(microdollars) || microdollars <= 0) return;
    // Living-TV: visual spend authorization is a noted honesty beat.
    emitWernerExperience("note_saved");
    await command(activeChapterId, "authorize", async (isCurrent) => {
      const authority = await authorizeMultimediaVisual(record.asset.asset_id, {
        request_id: requestId(record.asset.asset_id, record.asset.revision_id, activeChapterId),
        expected_revision_id: record.asset.revision_id,
        chapter_id: activeChapterId,
        approved_ceiling_microdollars: microdollars,
        operator_acknowledged_spend: true,
      });
      if (!isCurrent()) return;
      Object.values(activeReview.previewUrls).forEach((url) => {
        URL.revokeObjectURL(url);
        ownedPreviewUrls.current.delete(url);
      });
      update(activeChapterId, {
        authority,
        generation: undefined,
        candidates: [],
        previewUrls: {},
        attestedCandidateIds: [],
        selectedCandidateId: undefined,
      });
    });
  }

  async function submit() {
    const authority = activeReview.authority;
    if (!authority) return;
    // Living-TV: visual generation submit is a happy craft beat.
    emitWernerExperience("piece_started");
    await command(activeChapterId, "submit", async (isCurrent) => {
      const generation = await submitMultimediaVisualGeneration(
        record.asset.asset_id,
        authority.authorization.request_id,
        record.asset.revision_id,
        authority.authorization.authorization_id,
      );
      if (!isCurrent()) return;
      update(activeChapterId, { generation });
    });
  }

  async function poll() {
    const authority = activeReview.authority;
    const generation = activeReview.generation;
    if (!authority || !generation) return;
    await command(activeChapterId, "poll", async (isCurrent) => {
      const next = await pollMultimediaVisualGeneration(
        record.asset.asset_id,
        generation.execution_id,
        record.asset.revision_id,
        authority.authorization.authorization_id,
      );
      if (!isCurrent()) return;
      update(activeChapterId, { generation: next });
    });
  }

  async function materialize() {
    const authority = activeReview.authority;
    const generation = activeReview.generation;
    if (!authority || !generation) return;
    await command(activeChapterId, "materialize", async (isCurrent) => {
      const result = await materializeMultimediaVisualCandidates(
        record.asset.asset_id,
        generation.execution_id,
        authority.authorization.request_id,
        record.asset.revision_id,
      );
      if (!isCurrent()) return;
      const previews: Array<readonly [string, string]> = [];
      try {
        for (const candidate of result.candidates) {
          const blob = await previewMultimediaVisualCandidate(
            record.asset.asset_id,
            record.asset.revision_id,
            candidate.candidate_id,
          );
          if (!isCurrent()) return;
          const url = URL.createObjectURL(blob);
          ownedPreviewUrls.current.add(url);
          previews.push([candidate.candidate_id, url] as const);
        }
      } catch (error) {
        previews.forEach(([, url]) => {
          URL.revokeObjectURL(url);
          ownedPreviewUrls.current.delete(url);
        });
        throw error;
      }
      if (!isCurrent()) return;
      update(activeChapterId, { candidates: result.candidates, previewUrls: Object.fromEntries(previews) });
    });
  }

  async function attestAndSelect(candidate: MultimediaVisualCandidate) {
    if (!provenanceAcknowledged) return;
    await command(activeChapterId, "attest", async (isCurrent) => {
      const attestation = await attestMultimediaVisualCandidate(
        record.asset.asset_id,
        record.asset.revision_id,
        candidate.candidate_id,
      );
      if (!isCurrent()) return;
      if (attestation.artifact_receipt_id !== candidate.artifact_receipt_id) {
        throw new Error("multimedia_visual_attestation_identity_conflict");
      }
      update(activeChapterId, {
        attestedCandidateIds: Array.from(
          new Set([...activeReview.attestedCandidateIds, candidate.candidate_id]),
        ),
        selectedCandidateId: candidate.candidate_id,
      });
    });
  }

  async function register() {
    if (!complete) return;
    const started = epoch.current;
    setRegistering(true);
    setRegisterError(null);
    // Living-TV: reviewed visual set registration is a happy craft beat.
    emitWernerExperience("piece_started");
    try {
      const value = await registerMultimediaReviewedVisuals(
        record.asset.asset_id,
        record.asset.revision_id,
        requestId(record.asset.asset_id, record.asset.revision_id, "reviewed-set"),
        chapters.map((chapter) => ({
          chapter_id: chapter.id,
          candidate_id: reviews[chapter.id].selectedCandidateId!,
        })),
      );
      if (started === epoch.current) onRegistered(value);
    } catch (error) {
      if (started === epoch.current) {
        emitWernerExperience("fail");
        setRegisterError(message(error));
      }
    } finally {
      if (started === epoch.current) setRegistering(false);
    }
  }

  if (reviewedSet) {
    return (
      <section className="border-t border-rule pt-4 dark:border-charcoal-1" data-testid="visual-review-complete">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h3 className="font-serif text-base text-ink dark:text-bright">Visual sequence locked</h3>
            <p className="mt-1 text-[12px] text-shadow-1 dark:text-moonlight">
              <span>{reviewedSet.scene_ids.length} scenes bound</span>
              <span> and ready for documentary production.</span>
            </p>
            <p className="mt-1 font-mono text-[10px] text-shadow-2 dark:text-moonlight">{reviewedSet.set_id}</p>
          </div>
          <LemonTag colour="aurora">Reviewed</LemonTag>
        </div>
      </section>
    );
  }

  if (record.asset.status !== "ready") {
    return (
      <section className="border-t border-rule pt-4 dark:border-charcoal-1" data-testid="visual-review-awaiting-approval">
        <p className="font-mono text-[11px] uppercase text-shadow-2 dark:text-moonlight">Visual review</p>
        <p className="mt-1 text-[12px] text-ink dark:text-bright">Approve the plan before authorizing generated images.</p>
      </section>
    );
  }

  if (record.asset.route_policy === "cheapest") {
    return (
      <section className="border-t border-rule pt-4 dark:border-charcoal-1" data-testid="visual-review-cheapest">
        <p className="font-mono text-[11px] uppercase text-shadow-2 dark:text-moonlight">Visual review</p>
        <p className="mt-1 text-[12px] text-ink dark:text-bright">The cheapest route uses local visual fallbacks and does not authorize paid image generation.</p>
      </section>
    );
  }

  if (!projection.ok) {
    return <p role="alert" className="border-t border-rule pt-4 text-[12px] text-emperor dark:border-charcoal-1">{projection.error}</p>;
  }

  return (
    <section className="border-t border-rule pt-4 dark:border-charcoal-1" data-testid="visual-review-panel">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="font-mono text-[11px] uppercase text-shadow-2 dark:text-moonlight">Visual review</p>
          <h3 className="mt-1 font-serif text-lg text-ink dark:text-bright">Build the evidence sequence</h3>
        </div>
        <span className="font-mono text-[11px] text-shadow-1 dark:text-moonlight">
          {chapters.filter((chapter) => reviews[chapter.id]?.selectedCandidateId).length}/{chapters.length} selected
        </span>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-[13rem_minmax(0,1fr)]">
        <nav aria-label="Documentary chapters" className="border-r-0 border-rule lg:border-r lg:pr-4 dark:border-charcoal-1">
          <ol className="grid gap-1 sm:grid-cols-2 lg:grid-cols-1">
            {chapters.map((chapter, index) => {
              const selected = reviews[chapter.id]?.selectedCandidateId;
              return (
                <li key={chapter.id}>
                  <button
                    type="button"
                    aria-label={`Review visual chapter ${index + 1}`}
                    title={chapter.title}
                    onClick={() => setActiveChapterId(chapter.id)}
                    className={`min-h-14 w-full border-l-4 px-3 py-2 text-left ${
                      activeChapterId === chapter.id
                        ? "border-sun bg-sun/10"
                        : "border-transparent hover:bg-ice-2 dark:hover:bg-charcoal-1"
                    }`}
                  >
                    <span className="block font-mono text-[10px] text-shadow-2 dark:text-moonlight">
                      {String(index + 1).padStart(2, "0")} {selected ? "SELECTED" : "OPEN"}
                    </span>
                    <span className="mt-1 block text-[12px] font-semibold text-ink dark:text-bright">Chapter {String(index + 1).padStart(2, "0")}</span>
                  </button>
                </li>
              );
            })}
          </ol>
        </nav>

        <div className="min-w-0">
          <div className="flex flex-wrap items-end gap-3">
            <label className="text-[11px] text-shadow-1 dark:text-moonlight">
              Maximum spend (USD)
              <input
                aria-label="Maximum visual spend in USD"
                type="number"
                min="0.01"
                step="0.01"
                value={ceilingUsd}
                onChange={(event) => setCeilingUsd(event.target.value)}
                className="mt-1 block h-9 w-32 rounded-md border border-rule bg-ice-0 px-2 text-ink dark:border-charcoal-1 dark:bg-charcoal-2 dark:text-bright"
              />
            </label>
            <label className="flex min-h-9 items-center gap-2 text-[11px] text-shadow-1 dark:text-moonlight">
              <input type="checkbox" checked={spendAcknowledged} onChange={(event) => setSpendAcknowledged(event.target.checked)} />
              Approve this ceiling
            </label>
            {!activeReview.authority && (
              <LemonButton size="sm" variant="secondary" disabled={!spendAcknowledged || activeReview.pending !== null} onClick={authorize}>
                {activeReview.pending === "authorize" ? "Authorizing..." : "Authorize images"}
              </LemonButton>
            )}
            {activeReview.authority && !activeReview.generation && (
              <LemonButton size="sm" variant="primary" disabled={activeReview.pending !== null} onClick={submit}>
                {activeReview.pending === "submit" ? "Submitting..." : "Generate candidates"}
              </LemonButton>
            )}
            {activeReview.generation && activeReview.generation.status !== "succeeded" && (
              <LemonButton size="sm" variant="secondary" disabled={activeReview.pending !== null} onClick={poll}>
                {activeReview.pending === "poll" ? "Checking..." : "Check generation"}
              </LemonButton>
            )}
            {activeReview.generation?.status === "succeeded" && !activeReview.candidates.length && (
              <LemonButton size="sm" variant="secondary" disabled={activeReview.pending !== null} onClick={materialize}>
                {activeReview.pending === "materialize" ? "Preparing..." : "Open contact sheet"}
              </LemonButton>
            )}
          </div>

          {activeReview.error && <p role="alert" className="mt-3 text-[12px] text-emperor">{activeReview.error}</p>}

          {activeReview.candidates.length > 0 && (
            <>
              <div className="mt-4 grid gap-3 sm:grid-cols-2" data-testid="visual-candidate-grid">
                {activeReview.candidates.map((candidate, index) => {
                  const selected = activeReview.selectedCandidateId === candidate.candidate_id;
                  const attested = activeReview.attestedCandidateIds.includes(candidate.candidate_id);
                  return (
                    <article key={candidate.candidate_id} className={`overflow-hidden rounded-md border ${selected ? "border-sun shadow-z1" : "border-rule dark:border-charcoal-1"}`}>
                      <div className="aspect-video bg-ink">
                        {activeReview.previewUrls[candidate.candidate_id] && (
                          <img className="h-full w-full object-contain" src={activeReview.previewUrls[candidate.candidate_id]} alt={`Generated candidate ${index + 1} for ${chapters.find((chapter) => chapter.id === activeChapterId)?.title}`} />
                        )}
                      </div>
                      <div className="flex min-h-14 items-center justify-between gap-2 bg-ice-0 px-3 py-2 dark:bg-charcoal-2">
                        <div>
                          <p className="font-mono text-[10px] text-shadow-2 dark:text-moonlight">CANDIDATE {index + 1}</p>
                          <p className="text-[11px] text-ink dark:text-bright">{Math.ceil(candidate.byte_count / 1024)} KB · generated</p>
                        </div>
                        <LemonButton size="sm" variant={selected ? "primary" : "tertiary"} disabled={!provenanceAcknowledged || activeReview.pending !== null} onClick={() => void attestAndSelect(candidate)}>
                          {selected ? "Selected" : attested ? "Select" : "Attest & select"}
                        </LemonButton>
                      </div>
                    </article>
                  );
                })}
              </div>
              <label className="mt-3 flex items-start gap-2 text-[11px] leading-relaxed text-shadow-1 dark:text-moonlight">
                <input className="mt-0.5" type="checkbox" checked={provenanceAcknowledged} onChange={(event) => setProvenanceAcknowledged(event.target.checked)} />
                I confirm these are generated visuals, not archival evidence.
              </label>
            </>
          )}
        </div>
      </div>

      <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-rule pt-3 dark:border-charcoal-1">
        <p className="text-[11px] text-shadow-1 dark:text-moonlight">Every spoken chapter needs one attested selection.</p>
        <LemonButton variant="primary" disabled={!complete || registering} onClick={() => void register()}>
          {registering ? "Locking sequence..." : "Lock visual sequence"}
        </LemonButton>
      </div>
      {registerError && <p role="alert" className="mt-2 text-[12px] text-emperor">{registerError}</p>}
    </section>
  );
}
