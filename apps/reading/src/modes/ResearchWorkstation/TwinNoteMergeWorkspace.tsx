import { ArrowDown, ArrowUp, RefreshCw, X } from "lucide-react";
import { useMemo, useRef, useState } from "react";

import {
  applyDerivedMergeReview,
  createDerivedMergeDraft,
  createDerivedMergeReview,
  createTwinNoteMergeProjection,
  getTwinNoteMergeContext,
} from "../../api/research";
import type {
  DerivedMergeApplyResponse,
  DerivedMergeDraftResponse,
  DerivedMergeReviewResponse,
  TwinNoteMergeContextResponse,
  TwinNoteMergeProjectionResponse,
} from "../../api/research";
import { API_BASE } from "../../lib/api";

type NoteIdentity = { revision_id: string; note_ordinal: number };

const commandKey = () => crypto.randomUUID();
const operationKey = () => `op_${crypto.randomUUID().replaceAll("-", "").slice(0, 32)}`;
const noteKey = (note: NoteIdentity) => `${note.revision_id}:${note.note_ordinal}`;

export const mergePreviewUrl = (relative: string, apiBase = API_BASE): string => {
  const base = new URL(apiBase || "/", window.location.origin);
  const prefix = base.pathname === "/" ? "" : base.pathname.replace(/\/$/, "");
  const candidate = new URL(`${prefix}/${relative.replace(/^\/+/, "")}`, base.origin);
  const allowed = [
    new RegExp(`^${prefix}/research/twin-notes/merge-context/source-projections/hproj-[0-9a-f]{64}/preview$`),
    new RegExp(`^${prefix}/research/twin-notes/merge-context/(?:revision/tnr-|composition/tnc-)[0-9a-f]{32}/preview$`),
    new RegExp(`^${prefix}/research/derived-assets/merge/frame-previews/(?:drf_|rvw_)[0-9a-f]{32}$`),
  ];
  if (candidate.origin !== base.origin || candidate.search || candidate.hash
      || !allowed.some((pattern) => pattern.test(candidate.pathname))) {
    throw new Error("unsafe merge preview URL");
  }
  return candidate.toString();
};

interface Props {
  disabled: boolean;
  onPendingChange: (pending: boolean) => void;
}

export default function TwinNoteMergeWorkspace({ disabled, onPendingChange }: Props) {
  const [context, setContext] = useState<TwinNoteMergeContextResponse | null>(null);
  const [opened, setOpened] = useState(false);
  const [sourceProjectionId, setSourceProjectionId] = useState("");
  const [twinSourceKey, setTwinSourceKey] = useState("");
  const [selection, setSelection] = useState<NoteIdentity[]>([]);
  const [bridgeKey, setBridgeKey] = useState(commandKey);
  const [operationId, setOperationId] = useState(operationKey);
  const [bridge, setBridge] = useState<TwinNoteMergeProjectionResponse | null>(null);
  const [draft, setDraft] = useState<DerivedMergeDraftResponse | null>(null);
  const [review, setReview] = useState<DerivedMergeReviewResponse | null>(null);
  const [applied, setApplied] = useState<DerivedMergeApplyResponse | null>(null);
  const [title, setTitle] = useState("");
  const [assetKind, setAssetKind] = useState<"document" | "analysis" | "synthesis" | "composite">("analysis");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const generation = useRef(0);

  const sourceProjection = context?.source_projections.find(
    (item) => item.projection_id === sourceProjectionId,
  );
  const twinSource = context?.twin_sources.find(
    (item) => `${item.kind}:${item.id}` === twinSourceKey,
  );
  const notes = useMemo(() => twinSource?.revisions.flatMap((revision) =>
    revision.notes.map((note) => ({ ...note, revision_id: revision.revision_id }))) ?? [], [twinSource]);

  const setBusy = (value: boolean) => {
    setPending(value);
    onPendingChange(value);
  };

  const invalidate = () => {
    generation.current += 1;
    setBusy(false);
    setSelection([]);
    setBridge(null);
    setDraft(null);
    setReview(null);
    setApplied(null);
    setBridgeKey(commandKey());
    setOperationId(operationKey());
    setError(null);
  };

  const load = async () => {
    const exactGeneration = ++generation.current;
    setBusy(true);
    setError(null);
    try {
      const result = await getTwinNoteMergeContext();
      if (exactGeneration !== generation.current) return;
      setContext(result);
      setSourceProjectionId("");
      setTwinSourceKey("");
      setSelection([]);
      setBridge(null);
      setDraft(null);
      setReview(null);
      setApplied(null);
      setBridgeKey(commandKey());
      setOperationId(operationKey());
    } catch {
      if (exactGeneration === generation.current) setError("Could not load merge context. Try again.");
    } finally {
      if (exactGeneration === generation.current) setBusy(false);
    }
  };

  const chooseSource = (value: string) => {
    invalidate();
    setSourceProjectionId(value);
  };

  const chooseTwin = (value: string) => {
    invalidate();
    setTwinSourceKey(value);
  };

  const toggleNote = (identity: NoteIdentity) => {
    const key = noteKey(identity);
    const selected = selection.some((item) => noteKey(item) === key);
    generation.current += 1;
    setBusy(false);
    setSelection((current) => selected
      ? current.filter((item) => noteKey(item) !== key)
      : [...current, identity]);
    setBridge(null); setDraft(null); setReview(null); setApplied(null);
    setBridgeKey(commandKey()); setOperationId(operationKey()); setError(null);
  };

  const moveNote = (index: number, offset: -1 | 1) => {
    const destination = index + offset;
    if (destination < 0 || destination >= selection.length) return;
    generation.current += 1;
    setBusy(false);
    setSelection((current) => {
      const next = [...current];
      [next[index], next[destination]] = [next[destination], next[index]];
      return next;
    });
    setBridge(null); setDraft(null); setReview(null); setApplied(null);
    setBridgeKey(commandKey()); setOperationId(operationKey()); setError(null);
  };

  const createBridge = async () => {
    if (!sourceProjection || !twinSource || selection.length === 0) return;
    const exactGeneration = generation.current;
    const exactSource = sourceProjection.projection_id;
    const exactTwin = { kind: twinSource.kind, id: twinSource.id };
    const exactNotes = [...selection];
    setBusy(true); setError(null);
    try {
      const result = await createTwinNoteMergeProjection({
        source_projection_id: exactSource,
        source: exactTwin,
        selected_notes: exactNotes,
        idempotency_key: bridgeKey,
      });
      if (exactGeneration !== generation.current) return;
      const expectedPair = [exactSource, result.projection_id];
      if (result.source_projection_id !== exactSource
          || result.twin_source.kind !== exactTwin.kind || result.twin_source.id !== exactTwin.id
          || result.member_count !== exactNotes.length
          || result.merge_draft_input.projection_ids.length !== 2
          || result.merge_draft_input.projection_ids.some((id, index) => id !== expectedPair[index])) {
        setError("Could not verify the merge projection response. Refresh and try again.");
        return;
      }
      setBridge(result);
    } catch {
      if (exactGeneration === generation.current) {
        setError("Could not create the merge projection. The exact command is retained; retry.");
      }
    } finally {
      if (exactGeneration === generation.current) setBusy(false);
    }
  };

  const createDraft = async () => {
    if (!bridge || !title.trim()) return;
    const exactGeneration = generation.current;
    const exactPair = bridge.merge_draft_input.projection_ids;
    setDraft(null); setReview(null); setApplied(null);
    setOperationId(operationKey());
    setBusy(true); setError(null);
    try {
      const result = await createDerivedMergeDraft({
        projection_ids: exactPair,
        intent: "create",
        title: title.trim(),
        asset_kind: assetKind,
      });
      if (exactGeneration !== generation.current) return;
      if (result.projection_ids.length !== 2
          || result.projection_ids.some((id, index) => id !== exactPair[index])) {
        setError("Could not verify the canonical draft response. Refresh and try again.");
        return;
      }
      setDraft(result);
    } catch {
      if (exactGeneration === generation.current) setError("Could not create the canonical merge draft. Retry.");
    } finally {
      if (exactGeneration === generation.current) setBusy(false);
    }
  };

  const createReview = async () => {
    if (!draft) return;
    const exactGeneration = generation.current;
    const exactDraft = draft;
    setBusy(true); setError(null);
    try {
      const result = await createDerivedMergeReview(exactDraft.draft_id);
      if (exactGeneration !== generation.current) return;
      if (result.draft_id !== exactDraft.draft_id
          || result.canonical_sha256 !== exactDraft.canonical_sha256
          || result.manifest_sha256 !== exactDraft.manifest_sha256) {
        setError("Could not verify the merge review response. Refresh and try again.");
        return;
      }
      setReview(result);
    } catch {
      if (exactGeneration === generation.current) setError("Could not create the immutable review. Retry.");
    } finally {
      if (exactGeneration === generation.current) setBusy(false);
    }
  };

  const applyReview = async () => {
    if (!review) return;
    const exactGeneration = generation.current;
    const exactReview = review.review_id;
    const exactOperation = operationId;
    setBusy(true); setError(null);
    try {
      const result = await applyDerivedMergeReview(exactReview, exactOperation);
      if (exactGeneration !== generation.current) return;
      if (result.operation_id !== exactOperation) {
        setError("Could not verify the apply receipt. Refresh and inspect the derived asset.");
        return;
      }
      setApplied(result);
    } catch {
      if (exactGeneration === generation.current) setError("Could not apply the reviewed merge. The operation is retained; retry.");
    } finally {
      if (exactGeneration === generation.current) setBusy(false);
    }
  };

  const changeDraftInput = (change: () => void) => {
    generation.current += 1;
    setBusy(false);
    change();
    setDraft(null); setReview(null); setApplied(null);
    setOperationId(operationKey()); setError(null);
  };

  const frozen = disabled || pending;
  if (!opened) {
    return <section className="mt-4 border-t border-ink-mute/30 pt-3">
      <button type="button" disabled={disabled} onClick={() => { setOpened(true); void load(); }}>Merge into derived asset</button>
    </section>;
  }
  return <section className="mt-4 border-t border-ink-mute/30 pt-3" aria-labelledby="merge-workspace-heading">
    <div className="flex items-center justify-between">
      <h3 id="merge-workspace-heading" className="font-mono text-[11px] font-semibold uppercase">Merge into derived asset</h3>
      <button type="button" aria-label="Refresh merge context" title="Refresh merge context" disabled={frozen} onClick={() => void load()}><RefreshCw size={14} /></button>
    </div>
    <fieldset disabled={frozen} className="mt-2 space-y-2">
      <label className="block font-mono text-[10px]">Source projection<select aria-label="Merge source projection" className="block w-full border bg-transparent p-1" value={sourceProjectionId} onChange={(event) => chooseSource(event.target.value)}><option value="">Choose source HTML</option>{context?.source_projections.map((item) => <option key={item.projection_id} value={item.projection_id}>{item.label}</option>)}</select></label>
      <label className="block font-mono text-[10px]">Twin source<select aria-label="Merge twin source" className="block w-full border bg-transparent p-1" value={twinSourceKey} onChange={(event) => chooseTwin(event.target.value)}><option value="">Choose exact twin note</option>{context?.twin_sources.map((item) => <option key={`${item.kind}:${item.id}`} value={`${item.kind}:${item.id}`}>{item.label} · {item.kind}</option>)}</select></label>
      {sourceProjection && twinSource && <div className="grid gap-2 sm:grid-cols-2" aria-label="Merge source comparison">
        <iframe title="Source HTML comparison" sandbox="" src={mergePreviewUrl(sourceProjection.preview_url)} className="h-64 w-full border" />
        <iframe title="Twin-note HTML comparison" sandbox="" src={mergePreviewUrl(twinSource.html_url)} className="h-64 w-full border" />
      </div>}
      {twinSource && <div aria-label="Exact twin-note checklist" className="space-y-1">{notes.map((note) => {
        const identity = { revision_id: note.revision_id, note_ordinal: note.note_ordinal };
        const checked = selection.some((item) => noteKey(item) === noteKey(identity));
        return <label key={noteKey(identity)} className="block border border-ink-mute/20 p-1 text-[10px]"><input type="checkbox" checked={checked} onChange={() => toggleNote(identity)} /> <span>{note.text}</span><span className="block font-mono text-[9px] text-ink-mute">{note.revision_id} · note {note.note_ordinal + 1} · {note.source_count} sources</span></label>;
      })}</div>}
      {selection.length > 0 && <ol aria-label="Ordered merge note selection" className="space-y-1">{selection.map((note, index) => <li key={noteKey(note)} className="flex items-center gap-1 text-[10px]"><span className="min-w-0 flex-1 break-all">{index + 1}. {note.revision_id} · {note.note_ordinal + 1}</span><button type="button" title="Move up" aria-label={`Move merge note ${index + 1} up`} disabled={index === 0} onClick={() => moveNote(index, -1)}><ArrowUp size={13} /></button><button type="button" title="Move down" aria-label={`Move merge note ${index + 1} down`} disabled={index === selection.length - 1} onClick={() => moveNote(index, 1)}><ArrowDown size={13} /></button><button type="button" title="Remove" aria-label={`Remove merge note ${index + 1}`} onClick={() => toggleNote(note)}><X size={13} /></button></li>)}</ol>}
      <button type="button" disabled={!sourceProjection || !twinSource || selection.length === 0} onClick={() => void createBridge()}>{pending && !bridge ? "Creating projection…" : bridge ? "Retry projection" : "Create merge projection"}</button>
      {bridge && <div aria-label="Canonical merge draft stage" className="border-t pt-2"><label className="block">Title<input aria-label="Derived asset title" value={title} onChange={(event) => changeDraftInput(() => setTitle(event.target.value))} /></label><label className="block">Kind<select aria-label="Derived asset kind" value={assetKind} onChange={(event) => changeDraftInput(() => setAssetKind(event.target.value as typeof assetKind))}><option value="analysis">Analysis</option><option value="synthesis">Synthesis</option><option value="document">Document</option><option value="composite">Composite</option></select></label><button type="button" disabled={!title.trim()} onClick={() => void createDraft()}>{draft ? "Recreate draft" : "Create canonical draft"}</button></div>}
      {draft && <div aria-label="Draft preview stage" className="border-t pt-2"><iframe title="Canonical merge draft preview" sandbox="" src={mergePreviewUrl(`/research/derived-assets/merge/frame-previews/${draft.draft_id}`)} className="h-64 w-full border" /><button type="button" onClick={() => void createReview()}>Create immutable review</button></div>}
      {review && <div aria-label="Reviewed merge stage" className="border-t pt-2"><iframe title="Reviewed merge preview" sandbox="" src={mergePreviewUrl(`/research/derived-assets/merge/frame-previews/${review.review_id}`)} className="h-64 w-full border" /><button type="button" onClick={() => void applyReview()}>Apply reviewed merge</button></div>}
      {applied && <div role="status" className="font-mono text-[10px]">Applied as derived asset {applied.derived_asset_id}, revision {applied.revision_id}.</div>}
    </fieldset>
    {pending && <div role="status" className="font-mono text-[10px]">Merge command in progress…</div>}
    {error && <div role="alert" className="font-mono text-[10px] text-emperor">{error}</div>}
  </section>;
}
