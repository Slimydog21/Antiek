import { RefreshCw } from "lucide-react";
import { useRef, useState } from "react";

import {
  discoverDerivedAssets,
  getDerivedAssetHistory,
  restoreDerivedAsset,
} from "../../api/research";
import type {
  DerivedAssetDiscoveryResponse,
  DerivedAssetHistoryResponse,
  DerivedMergeApplyResponse,
} from "../../api/research";
import { API_BASE } from "../../lib/api";

const operationKey = () => `op_${crypto.randomUUID().replaceAll("-", "").slice(0, 32)}`;

export const derivedAssetPreviewUrl = (relative: string, apiBase = API_BASE): string => {
  const base = new URL(apiBase || "/", window.location.origin);
  const prefix = base.pathname === "/" ? "" : base.pathname.replace(/\/$/, "");
  const candidate = new URL(`${prefix}/${relative.replace(/^\/+/, "")}`, base.origin);
  const pattern = new RegExp(
    `^${prefix}/research/derived-assets/assets/ast_[0-9a-f]{32}/(?:current|revisions/rev_[0-9a-f]{32})/frame-preview$`,
  );
  if (candidate.origin !== base.origin || candidate.search || candidate.hash
      || !pattern.test(candidate.pathname)) throw new Error("unsafe derived asset preview URL");
  return candidate.toString();
};

interface Props {
  disabled: boolean;
  onPendingChange: (pending: boolean) => void;
}

export default function DerivedAssetLibraryPanel({ disabled, onPendingChange }: Props) {
  const [opened, setOpened] = useState(false);
  const [discovery, setDiscovery] = useState<DerivedAssetDiscoveryResponse | null>(null);
  const [assetId, setAssetId] = useState("");
  const [history, setHistory] = useState<DerivedAssetHistoryResponse | null>(null);
  const [selectedRevisionId, setSelectedRevisionId] = useState("");
  const [operationId, setOperationId] = useState(operationKey);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [applied, setApplied] = useState<DerivedMergeApplyResponse | null>(null);
  const generation = useRef(0);

  const setBusy = (value: boolean) => { setPending(value); onPendingChange(value); };
  const selected = history?.revisions.find((item) => item.revision_id === selectedRevisionId);

  const loadDiscovery = async () => {
    const exactGeneration = ++generation.current;
    setAssetId(""); setHistory(null); setSelectedRevisionId("");
    setOperationId(operationKey()); setApplied(null);
    setBusy(true); setError(null);
    try {
      const result = await discoverDerivedAssets();
      if (exactGeneration !== generation.current) return;
      setDiscovery(result);
    } catch {
      if (exactGeneration === generation.current) setError("Could not load derived assets. Try again.");
    } finally {
      if (exactGeneration === generation.current) setBusy(false);
    }
  };

  const chooseAsset = async (value: string) => {
    const exactGeneration = ++generation.current;
    setBusy(false); setAssetId(value); setHistory(null); setSelectedRevisionId("");
    setOperationId(operationKey()); setApplied(null); setError(null);
    if (!value) return;
    setBusy(true);
    try {
      const result = await getDerivedAssetHistory(value);
      if (exactGeneration !== generation.current) return;
      const summary = discovery?.assets.find((item) => item.derived_asset_id === value);
      if (!summary || result.derived_asset_id !== value
          || result.current.revision_id !== summary.current.revision_id
          || result.current.content_sha256 !== summary.current.content_sha256
          || result.current.generation !== summary.current.generation
          || result.revision_count !== result.revisions.length) {
        setError("Could not verify this derived asset history. Refresh and try again.");
        return;
      }
      setHistory(result);
    } catch {
      if (exactGeneration === generation.current) setError("Could not load this derived asset history.");
    } finally {
      if (exactGeneration === generation.current) setBusy(false);
    }
  };

  const chooseRevision = (value: string) => {
    generation.current += 1; setBusy(false); setSelectedRevisionId(value);
    setOperationId(operationKey()); setApplied(null); setError(null);
  };

  const restore = async () => {
    if (!history || !selected || selected.is_current) return;
    const exactGeneration = generation.current;
    const exactAsset = history.derived_asset_id;
    const exactHead = history.current;
    const exactSelected = selected;
    const exactOperation = operationId;
    setBusy(true); setError(null);
    try {
      const result = await restoreDerivedAsset(exactAsset, {
        operation_id: exactOperation,
        selected_revision_id: exactSelected.revision_id,
        expected_revision_id: exactHead.revision_id,
        expected_content_sha256: exactHead.content_sha256,
        expected_generation: exactHead.generation,
      });
      if (exactGeneration !== generation.current) return;
      if (result.operation_id !== exactOperation || result.derived_asset_id !== exactAsset
          || result.content_sha256 !== exactSelected.content_sha256
          || result.generation !== exactHead.generation + 1) {
        setError("Could not verify the restore receipt. Refresh before continuing.");
        return;
      }
      const refreshed = await getDerivedAssetHistory(exactAsset);
      if (exactGeneration !== generation.current) return;
      if (refreshed.derived_asset_id !== exactAsset
          || refreshed.current.revision_id !== result.revision_id
          || refreshed.current.content_sha256 !== result.content_sha256
          || refreshed.current.generation !== result.generation
          || refreshed.revision_count !== refreshed.revisions.length) {
        setError("Restore applied, but the refreshed head could not be verified.");
        return;
      }
      setHistory(refreshed);
      setDiscovery((current) => current && ({ ...current, assets: current.assets.map((asset) =>
        asset.derived_asset_id === exactAsset ? {
          derived_asset_id: refreshed.derived_asset_id,
          title: refreshed.title,
          asset_kind: refreshed.asset_kind,
          current: refreshed.current,
          revision_count: refreshed.revision_count,
        } : asset) }));
      setSelectedRevisionId(""); setOperationId(operationKey()); setApplied(result);
    } catch {
      if (exactGeneration === generation.current) {
        setError("Could not restore this revision. The exact operation is retained; retry.");
      }
    } finally {
      if (exactGeneration === generation.current) setBusy(false);
    }
  };

  const frozen = disabled || pending;
  if (!opened) return <section className="mt-4 border-t border-ink-mute/30 pt-3">
    <button type="button" disabled={disabled} onClick={() => { setOpened(true); void loadDiscovery(); }}>Browse derived assets</button>
  </section>;
  return <section className="mt-4 border-t border-ink-mute/30 pt-3" aria-labelledby="derived-library-heading">
    <div className="flex items-center justify-between"><h3 id="derived-library-heading" className="font-mono text-[11px] font-semibold uppercase">Derived assets</h3><button type="button" title="Refresh derived assets" aria-label="Refresh derived assets" disabled={frozen} onClick={() => void loadDiscovery()}><RefreshCw size={14} /></button></div>
    <fieldset disabled={frozen} className="mt-2 space-y-2">
      <label className="block font-mono text-[10px]">Asset<select aria-label="Derived asset" value={assetId} onChange={(event) => void chooseAsset(event.target.value)}><option value="">Choose derived asset</option>{discovery?.assets.map((asset) => <option key={asset.derived_asset_id} value={asset.derived_asset_id}>{asset.title} · {asset.asset_kind} · {asset.revision_count} revisions</option>)}</select></label>
      {history && <><label className="block font-mono text-[10px]">Historical revision<select aria-label="Historical derived asset revision" value={selectedRevisionId} onChange={(event) => chooseRevision(event.target.value)}><option value="">Choose exact revision</option>{history.revisions.filter((revision) => !revision.is_current).map((revision) => <option key={revision.revision_id} value={revision.revision_id}>{revision.operation_kind} · {revision.revision_id}</option>)}</select></label>
      <div className="grid gap-2 sm:grid-cols-2" aria-label="Derived asset revision comparison"><iframe title="Current derived asset HTML" sandbox="" src={derivedAssetPreviewUrl(history.current.preview_url)} className="h-64 w-full border" />{selected && <iframe title="Historical derived asset HTML" sandbox="" src={derivedAssetPreviewUrl(selected.preview_url)} className="h-64 w-full border" />}</div>
      {selected && <button type="button" onClick={() => void restore()}>Restore as new revision</button>}</>}
    </fieldset>
    {pending && <div role="status" className="font-mono text-[10px]">Derived asset command in progress…</div>}
    {applied && <div role="status" className="font-mono text-[10px]">Restored as revision {applied.revision_id}, generation {applied.generation}.</div>}
    {error && <div role="alert" className="font-mono text-[10px] text-emperor">{error}</div>}
  </section>;
}
