import { useEffect, useState } from "react";

import {
  composeTwinNotes,
  previewTwinNoteRevision, applyTwinNoteRevision, createTwinNoteWriteDraft,
  getTwinNoteHistory,
  listTwinNotes,
  twinNoteRevisionUrl,
} from "../../api/research";
import type { TwinNoteAsset, TwinNoteRevision, TwinNotePreviewResponse } from "../../api/research";
import { API_BASE } from "../../lib/api";

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

/** Cycle 48 owner-scoped immutable note browser and ordered composer. */
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
  const [createAsset,setCreateAsset]=useState("");
  const [createWindows,setCreateWindows]=useState("");
  const [preview,setPreview]=useState<TwinNotePreviewResponse|null>(null);
  const [createKey,setCreateKey]=useState(() => crypto.randomUUID());
  const [createPending,setCreatePending]=useState(false);
  const [compositionId,setCompositionId]=useState<string|null>(null);
  const [importSource,setImportSource]=useState<{kind:"revision"|"composition";id:string}|null>(null);
  const [importTitle,setImportTitle]=useState("");
  const [importKind,setImportKind]=useState("research_memo");
  const [importKey,setImportKey]=useState(() => crypto.randomUUID());
  const [importPending,setImportPending]=useState(false);
  const frozen=pending||createPending||importPending;

  const invalidatePreview=()=>{setPreview(null);setCreateKey(crypto.randomUUID());setActionError(null);};
  const windowIds=()=>createWindows.split(/[\n,]/).map(x=>x.trim()).filter(Boolean);
  const doPreview=async()=>{setCreatePending(true);setActionError(null);try{setPreview(await previewTwinNoteRevision(createAsset,windowIds()));}
    catch{setActionError("Could not preview this revision. Check the exact windows and try again.");}finally{setCreatePending(false);}};
  const doApply=async()=>{if(!preview)return;setCreatePending(true);setActionError(null);try{const made=await applyTwinNoteRevision({asset_id:createAsset,window_ids:windowIds(),expected_predecessor:preview.expected_predecessor,preview_digest:preview.preview_digest,idempotency_key:createKey});await load();setPreview(null);setImportSource({kind:"revision",id:made.revision_id});}
    catch{setActionError("Revision could not be applied. If the predecessor is stale, refresh the preview; otherwise retry with the same command.");}finally{setCreatePending(false);}};
  const startImport=(source:{kind:"revision"|"composition";id:string})=>{setImportSource(source);setImportTitle("");setImportKey(crypto.randomUUID());setActionError(null);};
  const doImport=async()=>{if(!importSource)return;setImportPending(true);setActionError(null);try{const draft=await createTwinNoteWriteDraft({source:importSource,idempotency_key:importKey,title:importTitle,deliverable_kind:importKind});window.location.assign(`/write/${draft.deliverable_id}`);}
    catch{setActionError("Could not create the Write draft. The exact source and command are retained; try again.");}finally{setImportPending(false);}};

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

  useEffect(() => { void load(); }, []);

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
    if (pending) return;
    setActionError(null);
    setSelection((current) => current.includes(revisionId)
      ? current.filter((id) => id !== revisionId)
      : current.length < 20 ? [...current, revisionId] : current);
  };

  const move = (index: number, offset: -1 | 1) => {
    if (pending) return;
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

  return (
    <section className="mt-5 border-t border-ink-mute/30 pt-3" aria-labelledby="twin-notes-heading">
      <div className="flex items-center justify-between mb-2">
        <h2 id="twin-notes-heading" className="font-mono text-shadow-1 dark:text-moonlight font-semibold uppercase tracking-wider">Twin notes</h2>
        <button onClick={() => void load()} disabled={frozen || loading} aria-label="Refresh twin notes"
          className="text-ink-mute dark:text-moonlight hover:text-ink disabled:opacity-40">⟳</button>
      </div>
      {loading && <div className="font-mono italic text-ink-mute">Loading twin notes…</div>}
      {loadError && <div role="status" className="text-emperor font-mono text-[10px]">Could not load twin notes. <button disabled={frozen} onClick={() => void load()} className="underline disabled:opacity-40">Try again</button></div>}
      {!loading && !loadError && assets.length === 0 && <p className="font-serif italic text-ink-mute">No twin notes yet.</p>}
      <fieldset disabled={frozen} className="mb-3 border border-ink-mute/30 rounded p-2">
        <legend className="font-mono text-[10px]">Create revision</legend>
        <label className="block">Asset ID<input aria-label="Twin-note asset ID" value={createAsset} onChange={e=>{setCreateAsset(e.target.value);invalidatePreview();}} className="w-full border" /></label>
        <label className="block">Ordered window IDs<textarea aria-label="Ordered window IDs" value={createWindows} onChange={e=>{setCreateWindows(e.target.value);invalidatePreview();}} className="w-full border" /></label>
        <button onClick={()=>void doPreview()} disabled={frozen||!createAsset||windowIds().length===0}>{createPending&&!preview?"Previewing…":"Preview"}</button>
        {preview&&<div aria-label="Revision preview" className="mt-2 font-mono text-[9px]">
          <div>Predecessor: {preview.expected_predecessor??"root"}</div><div>{preview.note_count} notes · {preview.source_count} sources</div>
          <ol>{preview.members.map(m=><li key={m.window_id}>{m.member_ordinal+1}. {m.investigation_id} · {m.window_id}</li>)}</ol>
          <button onClick={()=>void doApply()} disabled={frozen}>{createPending?"Applying…":"Apply revision"}</button>
          <button onClick={()=>void doPreview()} disabled={frozen}>Refresh preview</button>
        </div>}
      </fieldset>
      <ul className="space-y-2">
        {assets.map((asset) => (
          <li key={asset.asset_id} className="border border-ink-mute/30 rounded p-2">
            <div className="font-serif font-semibold break-words">{asset.asset_label}</div>
            <div className="font-mono text-[9px] text-ink-mute">{asset.current_revision.note_count} notes · {asset.current_revision.source_count} sources · {asset.revision_count} revisions</div>
            <div className="flex gap-2 mt-1">
              <label><input type="checkbox" aria-label={`Select current ${asset.asset_label}`}
                checked={selection.includes(asset.current_revision.revision_id)}
                disabled={frozen || (!selection.includes(asset.current_revision.revision_id) && selection.length >= 20)}
                onChange={() => toggle(asset.current_revision.revision_id)} /> Select</label>
              <button disabled={frozen} onClick={() => openExact(asset.current_revision.revision_id)} className="underline disabled:opacity-40">Open current</button>
              <button disabled={frozen} onClick={()=>startImport({kind:"revision",id:asset.current_revision.revision_id})} className="underline disabled:opacity-40">Create Write draft</button>
              <button disabled={frozen || historyPending === asset.asset_id} onClick={() => void showHistory(asset.asset_id)}
                aria-expanded={Boolean(expandedHistory[asset.asset_id])} className="underline disabled:opacity-40">History</button>
            </div>
            {expandedHistory[asset.asset_id] && history[asset.asset_id] && <ul aria-label={`${asset.asset_label} history`} className="mt-2 space-y-1">
              {history[asset.asset_id].map((revision, index) => <li key={revision.revision_id} className="flex items-center gap-2">
                <span className="font-mono text-[9px]">Revision {history[asset.asset_id].length - index}</span>
                <label><input type="checkbox" aria-label={`Select revision ${revision.revision_id}`}
                  checked={selection.includes(revision.revision_id)} disabled={frozen || (!selection.includes(revision.revision_id) && selection.length >= 20)}
                  onChange={() => toggle(revision.revision_id)} /> Select</label>
                <button disabled={frozen} onClick={() => openExact(revision.revision_id)} className="underline disabled:opacity-40">Open exact</button>
                <button disabled={frozen} onClick={()=>startImport({kind:"revision",id:revision.revision_id})} className="underline disabled:opacity-40">Create Write draft</button>
              </li>)}
            </ul>}
          </li>
        ))}
      </ul>

      {selection.length > 0 && <div className="mt-3 border border-ink-mute/30 rounded p-2" aria-label="Ordered twin-note selection">
        <div aria-live="polite" className="font-mono text-[10px]">{selection.length}/20 selected</div>
        <ol className="mt-1 space-y-1">
          {selection.map((revisionId, index) => <li key={revisionId} className="flex items-center gap-1">
            <span className="font-mono text-[9px] break-all flex-1">{index + 1}. {revisionId}</span>
            <button aria-label={`Move ${revisionId} up`} disabled={frozen || index === 0} onClick={() => move(index, -1)}>↑</button>
            <button aria-label={`Move ${revisionId} down`} disabled={frozen || index === selection.length - 1} onClick={() => move(index, 1)}>↓</button>
            <button aria-label={`Remove ${revisionId}`} disabled={frozen} onClick={() => toggle(revisionId)}>×</button>
          </li>)}
        </ol>
        <button onClick={() => void compose()} disabled={frozen || selection.length < 2}
          className="mt-2 bg-sun text-ink px-2 py-1 rounded disabled:opacity-40">{pending ? "Composing…" : "Compose twin notes"}</button>
      </div>}
      {compositionId&&<button disabled={frozen} onClick={()=>startImport({kind:"composition",id:compositionId})}>Create composition Write draft</button>}
      {importSource&&<fieldset disabled={frozen} className="mt-3 border p-2"><legend>Create Write draft from exact {importSource.kind}</legend>
        <div className="font-mono text-[9px] break-all">{importSource.id}</div>
        <label>Title<input aria-label="Write draft title" value={importTitle} onChange={e=>setImportTitle(e.target.value)} /></label>
        <label>Kind<select aria-label="Write draft kind" value={importKind} onChange={e=>setImportKind(e.target.value)}><option value="research_memo">Research memo</option><option value="general_essay">General essay</option><option value="book_chapter">Book chapter</option></select></label>
        <button disabled={frozen||!importTitle.trim()} onClick={()=>void doImport()}>{importPending?"Creating…":"Create draft"}</button>
      </fieldset>}
      {actionError && <div role="alert" className="text-emperor font-mono text-[10px] mt-2">{actionError}</div>}
    </section>
  );
}
