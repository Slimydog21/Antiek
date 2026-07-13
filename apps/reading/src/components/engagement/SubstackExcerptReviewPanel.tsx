import { useEffect, useRef, useState } from "react";

import {
  confirmCollectiveSubstackExcerpt,
  reviewCollectiveSubstackExcerpt,
  type ConfirmedCollectiveUnit,
  type ConfirmedSubstackExcerptReview,
  type SubstackExcerptReviewDraft,
} from "../../api/engagement";

function newReviewKey(): string {
  if (globalThis.crypto?.randomUUID) {
    return `substack-review-${globalThis.crypto.randomUUID()}`;
  }
  if (globalThis.crypto?.getRandomValues) {
    const bytes = globalThis.crypto.getRandomValues(new Uint8Array(16));
    return `substack-review-${Array.from(bytes, (value) => value.toString(16).padStart(2, "0")).join("")}`;
  }
  throw new Error("Secure browser randomness is required for Substack review");
}

export function SubstackExcerptReviewPanel(props: {
  collective: ConfirmedCollectiveUnit;
  onConfirmed?: (review: ConfirmedSubstackExcerptReview) => void;
  onAuthorityRefresh?: () => Promise<void>;
}) {
  const references = (props.collective.material.unit.source_references ?? []).filter(
    (ref) => ref.kind === "substack",
  );
  const sourceAuthority = JSON.stringify(
    references.map((ref) => [ref.ref_id, ref.canonical_url, ref.external_id ?? null]),
  );
  const authority = `${props.collective.collective_unit_id}:${props.collective.preview_sha256}:${sourceAuthority}`;
  const [refId, setRefId] = useState(references[0]?.ref_id ?? "");
  const [selectionText, setSelectionText] = useState("");
  const [representationHash, setRepresentationHash] = useState("");
  const [representationBytes, setRepresentationBytes] = useState(0);
  const [sourceStart, setSourceStart] = useState(0);
  const [lawfulAccess, setLawfulAccess] = useState(false);
  const [providerProcessing, setProviderProcessing] = useState(false);
  const [draft, setDraft] = useState<SubstackExcerptReviewDraft | null>(null);
  const [confirmed, setConfirmed] = useState<ConfirmedSubstackExcerptReview | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const reviewKey = useRef(newReviewKey());
  const confirmKey = useRef(newReviewKey());
  const generation = useRef(0);

  useEffect(() => {
    generation.current += 1;
    setRefId(references[0]?.ref_id ?? "");
    setSelectionText("");
    setRepresentationHash("");
    setRepresentationBytes(0);
    setSourceStart(0);
    setLawfulAccess(false);
    setProviderProcessing(false);
    setDraft(null);
    setConfirmed(null);
    setBusy(false);
    setError(null);
    reviewKey.current = newReviewKey();
    confirmKey.current = newReviewKey();
  }, [authority]);

  if (references.length === 0) return null;

  const changeReviewedMaterial = () => {
    generation.current += 1;
    setDraft(null);
    setConfirmed(null);
    setBusy(false);
    setError(null);
    reviewKey.current = newReviewKey();
    confirmKey.current = newReviewKey();
  };

  const review = async () => {
    const requestGeneration = generation.current;
    setBusy(true);
    setError(null);
    try {
      const next = await reviewCollectiveSubstackExcerpt(
        props.collective.collective_unit_id,
        {
          expected_collective_preview_sha256: props.collective.preview_sha256,
          ref_id: refId,
          selection_text: selectionText,
          source_representation_sha256: representationHash,
          source_representation_bytes: representationBytes,
          source_byte_start: sourceStart,
          authorization_lifetime_minutes: 30,
          owner_affirms_lawful_access: true,
          owner_affirms_provider_processing: true,
          partial_excerpt_affirmed: true,
          redistribution_authorized: false,
          training_authorized: false,
          publication_authorized: false,
          idempotency_key: reviewKey.current,
        },
      );
      if (requestGeneration !== generation.current) return;
      setDraft(next);
    } catch (cause) {
      if (requestGeneration !== generation.current) return;
      setError(cause instanceof Error ? cause.message : "Substack excerpt review failed");
    } finally {
      if (requestGeneration === generation.current) setBusy(false);
    }
  };

  const confirm = async () => {
    if (!draft) return;
    const requestGeneration = generation.current;
    setBusy(true);
    setError(null);
    try {
      const next = await confirmCollectiveSubstackExcerpt(
        props.collective.collective_unit_id,
        {
          review_id: draft.review_id,
          expected_review_preview_sha256: draft.review_preview_sha256,
          idempotency_key: confirmKey.current,
        },
      );
      if (requestGeneration !== generation.current) {
        try {
          await props.onAuthorityRefresh?.();
        } catch {
          setError("Confirmation may be saved, but authoritative refresh failed");
        }
        return;
      }
      setConfirmed(next);
      setSelectionText("");
      props.onConfirmed?.(next);
      try {
        await props.onAuthorityRefresh?.();
      } catch {
        setError("Confirmation was saved, but authoritative refresh failed");
      }
    } catch (cause) {
      if (requestGeneration !== generation.current) return;
      setError(cause instanceof Error ? cause.message : "Substack excerpt confirmation failed");
    } finally {
      if (requestGeneration === generation.current) setBusy(false);
    }
  };

  const valid =
    refId.length > 0 &&
    selectionText.length > 0 &&
    /^[0-9a-f]{64}$/.test(representationHash) &&
    representationBytes > 0 &&
    sourceStart >= 0 &&
    lawfulAccess &&
    providerProcessing;

  return (
    <section className="space-y-3 rounded border border-amber-700/40 bg-amber-50/50 p-3" data-testid="substack-excerpt-review-panel">
      <div>
        <h3 className="font-mono text-xs font-semibold uppercase tracking-wide">Private Substack excerpt review</h3>
        <p className="text-xs">
          Subscription access and permission to send selected text to an external model are separate decisions. This stores one owner-private excerpt; Substack execution remains disabled until manifest-v2 and private-output gates ship.
        </p>
      </div>
      {(props.collective.substack_excerpt_reviews ?? []).length > 0 ? (
        <ul className="space-y-1 text-[11px]" data-testid="saved-substack-reviews">
          {(props.collective.substack_excerpt_reviews ?? []).map((item) => (
            <li key={item.overlay_id}>
              Saved private excerpt for {item.ref_id}: authority {item.authorization_state ?? "unavailable"}; execution unavailable
            </li>
          ))}
        </ul>
      ) : null}
      <label className="block text-xs">
        Reviewed post
        <select value={refId} onChange={(event) => { changeReviewedMaterial(); setRefId(event.currentTarget.value); }} className="mt-1 block w-full rounded border p-2" data-testid="substack-review-ref">
          {references.map((ref) => <option key={ref.ref_id} value={ref.ref_id}>{ref.canonical_url}</option>)}
        </select>
      </label>
      <label className="block text-xs">
        Exact selected text
        <textarea value={selectionText} onChange={(event) => { changeReviewedMaterial(); setSelectionText(event.currentTarget.value); }} rows={5} className="mt-1 block w-full rounded border p-2" data-testid="substack-review-text" />
      </label>
      <div className="grid gap-2 sm:grid-cols-3">
        <label className="text-xs">Representation SHA-256<input value={representationHash} onChange={(event) => { changeReviewedMaterial(); setRepresentationHash(event.currentTarget.value.trim().toLowerCase()); }} className="mt-1 block w-full rounded border p-2 font-mono" /></label>
        <label className="text-xs">Representation bytes<input type="number" min={1} value={representationBytes || ""} onChange={(event) => { changeReviewedMaterial(); setRepresentationBytes(Number(event.currentTarget.value)); }} className="mt-1 block w-full rounded border p-2" /></label>
        <label className="text-xs">Selection starts at byte<input type="number" min={0} value={sourceStart} onChange={(event) => { changeReviewedMaterial(); setSourceStart(Number(event.currentTarget.value)); }} className="mt-1 block w-full rounded border p-2" /></label>
      </div>
      <label className="flex gap-2 text-xs"><input type="checkbox" checked={lawfulAccess} onChange={(event) => { changeReviewedMaterial(); setLawfulAccess(event.currentTarget.checked); }} />I have lawful access to this post and selected excerpt.</label>
      <label className="flex gap-2 text-xs"><input type="checkbox" checked={providerProcessing} onChange={(event) => { changeReviewedMaterial(); setProviderProcessing(event.currentTarget.checked); }} />I request private processing of this exact excerpt under the displayed no-training/no-retention constraints.</label>
      <p className="text-[11px]">Your representation and range are an unverified attestation—not publisher permission, provenance, redistribution rights, training rights, or publication rights.</p>
      <div className="flex gap-2">
        <button type="button" disabled={busy || !valid || Boolean(draft)} onClick={() => void review()} className="rounded border px-3 py-1.5 text-xs disabled:opacity-40" data-testid="review-substack-excerpt">Review exact excerpt</button>
        <button type="button" disabled={busy || !draft || Boolean(confirmed)} onClick={() => void confirm()} className="rounded bg-ink px-3 py-1.5 text-xs text-white disabled:opacity-40" data-testid="confirm-substack-excerpt">Confirm owner-private review</button>
      </div>
      {error ? <p role="alert">{error}</p> : null}
      {draft ? <div className="rounded border bg-white p-2" data-testid="substack-review-preview"><pre className="whitespace-pre-wrap text-xs">{draft.selection_text}</pre><p className="text-[10px] font-mono">{draft.excerpt_bytes} UTF-8 bytes · expires {new Date(draft.expires_at_ms).toISOString()}</p></div> : null}
      {confirmed ? <p className="text-[10px] font-mono" data-testid="confirmed-substack-review">Saved {confirmed.receipt_id} · personal reading · execution unavailable</p> : null}
    </section>
  );
}
