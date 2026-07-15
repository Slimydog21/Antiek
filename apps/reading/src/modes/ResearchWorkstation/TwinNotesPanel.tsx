import { useEffect, useState } from "react";

import {
  composeTwinNotes,
  getTwinNoteHistory,
  listTwinNotes,
  twinNoteRevisionUrl,
} from "../../api/research";
import type { TwinNoteAsset, TwinNoteRevision } from "../../api/research";
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
        <button onClick={() => void load()} disabled={pending || loading} aria-label="Refresh twin notes"
          className="text-ink-mute dark:text-moonlight hover:text-ink disabled:opacity-40">⟳</button>
      </div>
      {loading && <div className="font-mono italic text-ink-mute">Loading twin notes…</div>}
      {loadError && <div role="status" className="text-emperor font-mono text-[10px]">Could not load twin notes. <button disabled={pending} onClick={() => void load()} className="underline disabled:opacity-40">Try again</button></div>}
      {!loading && !loadError && assets.length === 0 && <p className="font-serif italic text-ink-mute">No twin notes yet.</p>}
      <ul className="space-y-2">
        {assets.map((asset) => (
          <li key={asset.asset_id} className="border border-ink-mute/30 rounded p-2">
            <div className="font-serif font-semibold break-words">{asset.asset_label}</div>
            <div className="font-mono text-[9px] text-ink-mute">{asset.current_revision.note_count} notes · {asset.current_revision.source_count} sources · {asset.revision_count} revisions</div>
            <div className="flex gap-2 mt-1">
              <label><input type="checkbox" aria-label={`Select current ${asset.asset_label}`}
                checked={selection.includes(asset.current_revision.revision_id)}
                disabled={pending || (!selection.includes(asset.current_revision.revision_id) && selection.length >= 20)}
                onChange={() => toggle(asset.current_revision.revision_id)} /> Select</label>
              <button disabled={pending} onClick={() => openExact(asset.current_revision.revision_id)} className="underline disabled:opacity-40">Open current</button>
              <button disabled={pending || historyPending === asset.asset_id} onClick={() => void showHistory(asset.asset_id)}
                aria-expanded={Boolean(expandedHistory[asset.asset_id])} className="underline disabled:opacity-40">History</button>
            </div>
            {expandedHistory[asset.asset_id] && history[asset.asset_id] && <ul aria-label={`${asset.asset_label} history`} className="mt-2 space-y-1">
              {history[asset.asset_id].map((revision, index) => <li key={revision.revision_id} className="flex items-center gap-2">
                <span className="font-mono text-[9px]">Revision {history[asset.asset_id].length - index}</span>
                <label><input type="checkbox" aria-label={`Select revision ${revision.revision_id}`}
                  checked={selection.includes(revision.revision_id)} disabled={pending || (!selection.includes(revision.revision_id) && selection.length >= 20)}
                  onChange={() => toggle(revision.revision_id)} /> Select</label>
                <button disabled={pending} onClick={() => openExact(revision.revision_id)} className="underline disabled:opacity-40">Open exact</button>
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
            <button aria-label={`Move ${revisionId} up`} disabled={pending || index === 0} onClick={() => move(index, -1)}>↑</button>
            <button aria-label={`Move ${revisionId} down`} disabled={pending || index === selection.length - 1} onClick={() => move(index, 1)}>↓</button>
            <button aria-label={`Remove ${revisionId}`} disabled={pending} onClick={() => toggle(revisionId)}>×</button>
          </li>)}
        </ol>
        <button onClick={() => void compose()} disabled={pending || selection.length < 2}
          className="mt-2 bg-sun text-ink px-2 py-1 rounded disabled:opacity-40">{pending ? "Composing…" : "Compose twin notes"}</button>
      </div>}
      {actionError && <div role="alert" className="text-emperor font-mono text-[10px] mt-2">{actionError}</div>}
    </section>
  );
}
