import { useEffect, useRef, useState } from "react";

import {
  applyTwinNoteRevision,
  composeTwinNotes,
  createTwinNoteWriteDraft,
  discoverTwinNoteRevisionCandidates,
  getTwinNoteHistory,
  listTwinNotes,
  previewTwinNoteRevision,
  twinNoteRevisionUrl,
} from "../../api/research";
import type {
  TwinNoteAsset,
  TwinNotePreviewResponse,
  TwinNoteRevision,
  TwinNoteRevisionCandidate,
  TwinNoteRevisionCandidateAsset,
} from "../../api/research";
import { API_BASE } from "../../lib/api";
import TwinNoteMergeWorkspace from "./TwinNoteMergeWorkspace";

export const absoluteApiUrl = (relative: string, apiBase = API_BASE): string => {
  const origin = window.location.origin;
  const base = new URL(apiBase || "/", origin);
  const prefix = base.pathname === "/" ? "" : base.pathname.replace(/\/$/, "");
  const candidate = new URL(`${prefix}/${relative.replace(/^\/+/, "")}`, base.origin);
  const twinPath = `${prefix}/research/twin-notes/`;
  if (candidate.origin !== base.origin || !candidate.pathname.startsWith(twinPath)) {
    throw new Error("unsafe twin-note URL");
  }
  const suffix = candidate.pathname.slice(twinPath.length);
  if (!/^(?:revisions\/tnr-|compositions\/tnc-)[0-9a-f]{32}$/.test(suffix) || candidate.search || candidate.hash) {
    throw new Error("unsafe twin-note URL");
  }
  return candidate.toString();
};

const exclusionLabels: Record<NonNullable<TwinNoteRevisionCandidate["exclusion_reason"]>, string> = {
  evidence_incomplete: "Evidence is incomplete",
  evidence_digest_mismatch: "Evidence verification failed",
  evidence_noncanonical: "Evidence format is invalid",
  evidence_binding_mismatch: "Evidence binding does not match",
  evidence_output_invalid: "Note output is invalid",
};

const newCommandKey = () => crypto.randomUUID();

/** Owner-scoped immutable note browser, composer, and revision workflow. */
export default function TwinNotesPanel() {
  const [assets, setAssets] = useState<TwinNoteAsset[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [history, setHistory] = useState<Record<string, TwinNoteRevision[]>>({});
  const [expandedHistory, setExpandedHistory] = useState<Record<string, boolean>>({});
  const [historyPending, setHistoryPending] = useState<string | null>(null);
  const [selection, setSelection] = useState<string[]>([]);
  const [pending, setPending] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const [candidateAssets, setCandidateAssets] = useState<TwinNoteRevisionCandidateAsset[]>([]);
  const [selectedAssetId, setSelectedAssetId] = useState("");
  const [selectedWindows, setSelectedWindows] = useState<string[]>([]);
  const [selectionLimit, setSelectionLimit] = useState(20);
  const [discoveryPending, setDiscoveryPending] = useState(true);
  const [discoveryError, setDiscoveryError] = useState(false);
  const discoveryGeneration = useRef(0);
  const previewGeneration = useRef(0);

  const [preview, setPreview] = useState<TwinNotePreviewResponse | null>(null);
  const [createKey, setCreateKey] = useState(newCommandKey);
  const [createPending, setCreatePending] = useState(false);
  const [compositionId, setCompositionId] = useState<string | null>(null);
  const [importSource, setImportSource] = useState<{ kind: "revision" | "composition"; id: string } | null>(null);
  const [importTitle, setImportTitle] = useState("");
  const [importKind, setImportKind] = useState("research_memo");
  const [importKey, setImportKey] = useState(newCommandKey);
  const [importPending, setImportPending] = useState(false);
  const [mergePending, setMergePending] = useState(false);
  const legacyFrozen = loading
    || discoveryPending
    || historyPending !== null
    || pending
    || createPending
    || importPending;
  const frozen = legacyFrozen || mergePending;

  const invalidatePreview = () => {
    previewGeneration.current += 1;
    setCreatePending(false);
    setPreview(null);
    setCreateKey(newCommandKey());
    setActionError(null);
  };

  const load = async () => {
    setLoading(true);
    setLoadError(false);
    try {
      setAssets((await listTwinNotes()).assets);
    } catch {
      setLoadError(true);
    } finally {
      setLoading(false);
    }
  };

  const loadDiscovery = async ({ invalidate = true }: { invalidate?: boolean } = {}) => {
    const generation = ++discoveryGeneration.current;
    if (invalidate) invalidatePreview();
    setDiscoveryPending(true);
    setDiscoveryError(false);
    try {
      const result = await discoverTwinNoteRevisionCandidates();
      if (generation !== discoveryGeneration.current) return;
      setCandidateAssets(result.assets);
      setSelectionLimit(result.limits.selection_members);
    } catch {
      if (generation === discoveryGeneration.current) setDiscoveryError(true);
    } finally {
      if (generation === discoveryGeneration.current) setDiscoveryPending(false);
    }
  };

  useEffect(() => {
    void load();
    void loadDiscovery();
    return () => {
      discoveryGeneration.current += 1;
      previewGeneration.current += 1;
    };
  }, []);

  const chooseAsset = (assetId: string) => {
    setSelectedAssetId(assetId);
    setSelectedWindows([]);
    invalidatePreview();
  };

  const addWindow = (windowId: string) => {
    if (selectedWindows.includes(windowId) || selectedWindows.length >= selectionLimit) return;
    setSelectedWindows((current) => [...current, windowId]);
    invalidatePreview();
  };

  const removeWindow = (windowId: string) => {
    setSelectedWindows((current) => current.filter((id) => id !== windowId));
    invalidatePreview();
  };

  const moveWindow = (index: number, offset: -1 | 1) => {
    const destination = index + offset;
    if (destination < 0 || destination >= selectedWindows.length) return;
    setSelectedWindows((current) => {
      const next = [...current];
      [next[index], next[destination]] = [next[destination], next[index]];
      return next;
    });
    invalidatePreview();
  };

  const doPreview = async () => {
    const generation = ++previewGeneration.current;
    const exactAsset = selectedAssetId;
    const exactWindows = [...selectedWindows];
    setPreview(null);
    setCreateKey(newCommandKey());
    setCreatePending(true);
    setActionError(null);
    try {
      const result = await previewTwinNoteRevision(exactAsset, exactWindows);
      if (generation !== previewGeneration.current) return;
      const exactEcho = result.asset_id === exactAsset
        && result.members.length === exactWindows.length
        && result.members.every((member, index) =>
          member.member_ordinal === index && member.window_id === exactWindows[index],
        );
      if (!exactEcho) {
        setPreview(null);
        setActionError("Could not verify this preview. Your selection is retained; refresh and try again.");
        return;
      }
      setPreview(result);
    } catch {
      if (generation === previewGeneration.current) {
        setActionError("Could not preview this revision. Refresh the candidates and try again.");
      }
    } finally {
      if (generation === previewGeneration.current) setCreatePending(false);
    }
  };

  const doApply = async () => {
    if (!preview) return;
    const exactPreview = preview;
    const exactAsset = selectedAssetId;
    const exactWindows = [...selectedWindows];
    const exactKey = createKey;
    setCreatePending(true);
    setActionError(null);
    try {
      const made = await applyTwinNoteRevision({
        asset_id: exactAsset,
        window_ids: exactWindows,
        expected_predecessor: exactPreview.expected_predecessor,
        preview_digest: exactPreview.preview_digest,
        idempotency_key: exactKey,
      });
      const [historyRefresh] = await Promise.all([
        getTwinNoteHistory(exactAsset).then(
          (result) => result.revisions,
          () => null,
        ),
        load(),
        loadDiscovery({ invalidate: false }),
      ]);
      if (historyRefresh) {
        setHistory((current) => ({ ...current, [exactAsset]: historyRefresh }));
      }
      setImportSource({ kind: "revision", id: made.revision_id });
    } catch {
      setActionError("Revision could not be applied. Refresh a stale preview, or retry the retained command.");
    } finally {
      setCreatePending(false);
    }
  };

  const startImport = (source: { kind: "revision" | "composition"; id: string }) => {
    setImportSource(source);
    setImportTitle("");
    setImportKey(newCommandKey());
    setActionError(null);
  };

  const doImport = async () => {
    if (!importSource) return;
    setImportPending(true);
    setActionError(null);
    try {
      const draft = await createTwinNoteWriteDraft({
        source: importSource,
        idempotency_key: importKey,
        title: importTitle,
        deliverable_kind: importKind,
      });
      window.location.assign(`/write/${draft.deliverable_id}`);
    } catch {
      setActionError("Could not create the Write draft. The exact source and command are retained; try again.");
    } finally {
      setImportPending(false);
    }
  };

  const showHistory = async (assetId: string) => {
    if (history[assetId]) {
      setExpandedHistory((current) => ({ ...current, [assetId]: !current[assetId] }));
      return;
    }
    setHistoryPending(assetId);
    setActionError(null);
    try {
      const result = await getTwinNoteHistory(assetId);
      setHistory((current) => ({ ...current, [assetId]: result.revisions }));
      setExpandedHistory((current) => ({ ...current, [assetId]: true }));
    } catch {
      setActionError("Could not load twin-note history. Try again.");
    } finally {
      setHistoryPending(null);
    }
  };

  const openExact = (revisionId: string) => {
    const popup = window.open("", "_blank");
    if (!popup) {
      setActionError("Allow pop-ups to open an immutable twin note.");
      return;
    }
    popup.opener = null;
    try {
      popup.location.replace(absoluteApiUrl(twinNoteRevisionUrl(revisionId)));
    } catch {
      popup.close();
      setActionError("Could not open this twin note. Try again.");
    }
  };

  const toggle = (revisionId: string) => {
    setActionError(null);
    setSelection((current) => current.includes(revisionId)
      ? current.filter((id) => id !== revisionId)
      : current.length < 20 ? [...current, revisionId] : current);
  };

  const move = (index: number, offset: -1 | 1) => {
    setSelection((current) => {
      const destination = index + offset;
      if (destination < 0 || destination >= current.length) return current;
      const next = [...current];
      [next[index], next[destination]] = [next[destination], next[index]];
      return next;
    });
  };

  const compose = async () => {
    const popup = window.open("", "_blank");
    if (!popup) {
      setActionError("Allow pop-ups to open the immutable composition.");
      return;
    }
    popup.opener = null;
    const exactOrder = [...selection];
    setPending(true);
    setActionError(null);
    try {
      const result = await composeTwinNotes(exactOrder);
      setCompositionId(result.composition_id);
      popup.location.replace(absoluteApiUrl(result.url));
    } catch {
      popup.close();
      setActionError("Could not compose these twin notes. Your selection is retained; try again.");
    } finally {
      setPending(false);
    }
  };

  const selectedCandidateAsset = candidateAssets.find((asset) => asset.asset_id === selectedAssetId);

  return (
    <section className="mt-5 border-t border-ink-mute/30 pt-3" aria-labelledby="twin-notes-heading">
      <div className="mb-2 flex items-center justify-between">
        <h2 id="twin-notes-heading" className="font-mono font-semibold uppercase tracking-wider text-shadow-1 dark:text-moonlight">Twin notes</h2>
        <button onClick={() => void Promise.all([load(), loadDiscovery()])} disabled={frozen || loading} aria-label="Refresh twin notes" className="text-ink-mute hover:text-ink disabled:opacity-40 dark:text-moonlight">⟳</button>
      </div>

      <fieldset disabled={frozen} className="mb-3 rounded border border-ink-mute/30 p-2">
        <legend className="font-mono text-[10px]">Create revision</legend>
        <label className="block font-mono text-[10px]">
          Asset
          <select aria-label="Twin-note asset" value={selectedAssetId} onChange={(event) => chooseAsset(event.target.value)} className="block w-full border bg-transparent p-1">
            <option value="">Choose an owned asset</option>
            {selectedAssetId && !candidateAssets.some((asset) => asset.asset_id === selectedAssetId) && <option value={selectedAssetId}>Previously selected asset</option>}
            {candidateAssets.map((asset) => <option key={asset.asset_id} value={asset.asset_id}>{asset.asset_label}</option>)}
          </select>
        </label>
        {discoveryError && <div role="status" className="font-mono text-[10px] text-emperor">Could not load revision candidates. <button onClick={() => void loadDiscovery()} className="underline">Try again</button></div>}
        {selectedCandidateAsset && <div className="mt-2 grid gap-2 sm:grid-cols-2">
          <ul aria-label="Revision window candidates" className="space-y-1">
            {selectedCandidateAsset.windows.map((window) => {
              const added = selectedWindows.includes(window.window_id);
              const excluded = window.eligibility === "excluded";
              return <li key={`${window.investigation_id}:${window.window_id}`} className="rounded border border-ink-mute/20 p-1">
                <div className="break-all font-mono text-[9px]">{window.investigation_id} · {window.window_id}</div>
                <div className="font-mono text-[9px] text-ink-mute">Window {window.window_ordinal} · {window.note_count} notes · {window.source_count} sources</div>
                {excluded && window.exclusion_reason && <div className="font-mono text-[9px] text-emperor">{exclusionLabels[window.exclusion_reason]}</div>}
                <button aria-label={`Add window ${window.window_id}`} disabled={excluded || added || selectedWindows.length >= selectionLimit} onClick={() => addWindow(window.window_id)} className="underline disabled:opacity-40">{added ? "Added" : "Add"}</button>
              </li>;
            })}
          </ul>
          <div aria-label="Ordered revision window selection" className="rounded border border-sun/70 p-2">
            <div aria-live="polite" className="font-mono text-[10px]">{selectedWindows.length}/{selectionLimit} windows selected</div>
            {selectedWindows.length === 0 ? <p className="font-serif italic text-ink-mute">Add eligible windows in the order they should appear.</p> : <ol className="space-y-1">
              {selectedWindows.map((windowId, index) => <li key={windowId} className="flex items-center gap-1">
                <span className="min-w-0 flex-1 break-all font-mono text-[9px]">{index + 1}. {windowId}</span>
                <button aria-label={`Move window ${windowId} up`} disabled={index === 0} onClick={() => moveWindow(index, -1)}>↑</button>
                <button aria-label={`Move window ${windowId} down`} disabled={index === selectedWindows.length - 1} onClick={() => moveWindow(index, 1)}>↓</button>
                <button aria-label={`Remove window ${windowId}`} onClick={() => removeWindow(windowId)}>×</button>
              </li>)}
            </ol>}
          </div>
        </div>}
        <button onClick={() => void doPreview()} disabled={!selectedAssetId || selectedWindows.length === 0} className="mt-2 disabled:opacity-40">{createPending && !preview ? "Previewing…" : "Preview"}</button>
        {preview && <div aria-label="Revision preview" className="mt-2 font-mono text-[9px]">
          <div>Predecessor: {preview.expected_predecessor ?? "root"}</div>
          <div>{preview.note_count} notes · {preview.source_count} sources</div>
          <ol>{preview.members.map((member) => <li key={member.window_id}>{member.member_ordinal + 1}. {member.investigation_id} · {member.window_id}</li>)}</ol>
          <button onClick={() => void doApply()}>{createPending ? "Applying…" : "Apply revision"}</button>
          <button onClick={() => void doPreview()}>Refresh preview</button>
        </div>}
      </fieldset>

      {loading && <div className="font-mono italic text-ink-mute">Loading twin notes…</div>}
      {loadError && <div role="status" className="font-mono text-[10px] text-emperor">Could not load twin notes. <button disabled={frozen} onClick={() => void load()} className="underline disabled:opacity-40">Try again</button></div>}
      {!loading && !loadError && assets.length === 0 && <p className="font-serif italic text-ink-mute">No twin notes yet.</p>}
      <ul className="space-y-2">
        {assets.map((asset) => <li key={asset.asset_id} className="rounded border border-ink-mute/30 p-2">
          <div className="break-words font-serif font-semibold">{asset.asset_label}</div>
          <div className="font-mono text-[9px] text-ink-mute">{asset.current_revision.note_count} notes · {asset.current_revision.source_count} sources · {asset.revision_count} revisions</div>
          <div className="mt-1 flex gap-2">
            <label><input type="checkbox" aria-label={`Select current ${asset.asset_label}`} checked={selection.includes(asset.current_revision.revision_id)} disabled={frozen || (!selection.includes(asset.current_revision.revision_id) && selection.length >= 20)} onChange={() => toggle(asset.current_revision.revision_id)} /> Select</label>
            <button disabled={frozen} onClick={() => openExact(asset.current_revision.revision_id)} className="underline disabled:opacity-40">Open current</button>
            <button disabled={frozen} onClick={() => startImport({ kind: "revision", id: asset.current_revision.revision_id })} className="underline disabled:opacity-40">Create Write draft</button>
            <button disabled={frozen || historyPending === asset.asset_id} onClick={() => void showHistory(asset.asset_id)} aria-expanded={Boolean(expandedHistory[asset.asset_id])} className="underline disabled:opacity-40">History</button>
          </div>
          {expandedHistory[asset.asset_id] && history[asset.asset_id] && <ul aria-label={`${asset.asset_label} history`} className="mt-2 space-y-1">
            {history[asset.asset_id].map((revision, index) => <li key={revision.revision_id} className="flex items-center gap-2">
              <span className="font-mono text-[9px]">Revision {history[asset.asset_id].length - index}</span>
              <label><input type="checkbox" aria-label={`Select revision ${revision.revision_id}`} checked={selection.includes(revision.revision_id)} disabled={frozen || (!selection.includes(revision.revision_id) && selection.length >= 20)} onChange={() => toggle(revision.revision_id)} /> Select</label>
              <button disabled={frozen} onClick={() => openExact(revision.revision_id)} className="underline disabled:opacity-40">Open exact</button>
              <button disabled={frozen} onClick={() => startImport({ kind: "revision", id: revision.revision_id })} className="underline disabled:opacity-40">Create Write draft</button>
            </li>)}
          </ul>}
        </li>)}
      </ul>

      {selection.length > 0 && <div className="mt-3 rounded border border-ink-mute/30 p-2" aria-label="Ordered twin-note selection">
        <div aria-live="polite" className="font-mono text-[10px]">{selection.length}/20 selected</div>
        <ol className="mt-1 space-y-1">{selection.map((revisionId, index) => <li key={revisionId} className="flex items-center gap-1">
          <span className="min-w-0 flex-1 break-all font-mono text-[9px]">{index + 1}. {revisionId}</span>
          <button aria-label={`Move ${revisionId} up`} disabled={frozen || index === 0} onClick={() => move(index, -1)}>↑</button>
          <button aria-label={`Move ${revisionId} down`} disabled={frozen || index === selection.length - 1} onClick={() => move(index, 1)}>↓</button>
          <button aria-label={`Remove ${revisionId}`} disabled={frozen} onClick={() => toggle(revisionId)}>×</button>
        </li>)}</ol>
        <button onClick={() => void compose()} disabled={frozen || selection.length < 2} className="mt-2 rounded bg-sun px-2 py-1 text-ink disabled:opacity-40">{pending ? "Composing…" : "Compose twin notes"}</button>
      </div>}
      {compositionId && <button disabled={frozen} onClick={() => startImport({ kind: "composition", id: compositionId })}>Create composition Write draft</button>}
      {importSource && <fieldset disabled={frozen} className="mt-3 border p-2"><legend>Create Write draft from exact {importSource.kind}</legend>
        <div className="break-all font-mono text-[9px]">{importSource.id}</div>
        <label>Title<input aria-label="Write draft title" value={importTitle} onChange={(event) => setImportTitle(event.target.value)} /></label>
        <label>Kind<select aria-label="Write draft kind" value={importKind} onChange={(event) => setImportKind(event.target.value)}><option value="research_memo">Research memo</option><option value="general_essay">General essay</option><option value="book_chapter">Book chapter</option></select></label>
        <button disabled={frozen || !importTitle.trim()} onClick={() => void doImport()}>{importPending ? "Creating…" : "Create draft"}</button>
      </fieldset>}
      <TwinNoteMergeWorkspace disabled={legacyFrozen} onPendingChange={setMergePending} />
      {actionError && <div role="alert" className="mt-2 font-mono text-[10px] text-emperor">{actionError}</div>}
    </section>
  );
}
