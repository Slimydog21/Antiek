import { useCallback, useEffect, useMemo, useState, type DragEvent } from "react";

import {
  API_BASE,
  composeResearchArtifacts,
  exportResearchArtifact,
  getResearchArtifactBlocks,
  type ResearchArtifactBlock,
} from "../../lib/api";
import { useInvestigationList } from "../../hooks/useInvestigationList";
import { artifactKindToBlockKind } from "../../lib/artifactBlocks";
import {
  DRAG_MIME,
  type PaletteDragPayload,
} from "../CreationStudio/BlockPalette";
import LemonButton from "../../components/lemon/LemonButton";

/**
 * ANT-AHT SPR-AHT-06 — draggable insight/question blocks sourced from
 * GET /research/{id}/artifact/blocks. Drops use the same palette envelope
 * as Repository / BlockPalette so Write outline preserves graph_node provenance.
 */
export interface ArtifactOutlineShelfProps {
  investigationId: string;
}

function startDrag(e: DragEvent, block: ResearchArtifactBlock) {
  const payload: PaletteDragPayload = {
    from: "palette",
    block_kind: artifactKindToBlockKind(block.kind),
    block_id: block.node_id,
    label: block.label.slice(0, 120),
  };
  e.dataTransfer.setData(DRAG_MIME, JSON.stringify(payload));
  e.dataTransfer.effectAllowed = "copy";
}

function parseSiblingIds(raw: string): string[] {
  return raw
    .split(/[,\s]+/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function draftMergeHref(investigationIds: string[]): string {
  const params = new URLSearchParams();
  for (const id of investigationIds) params.append("investigation_ids", id);
  return `${API_BASE}/research/artifacts/compose/draft-merge.html?${params.toString()}`;
}

export default function ArtifactOutlineShelf({
  investigationId,
}: ArtifactOutlineShelfProps) {
  const [blocks, setBlocks] = useState<ResearchArtifactBlock[]>([]);
  const [exportPath, setExportPath] = useState<string | null>(null);
  const [twinNotesPath, setTwinNotesPath] = useState<string | null>(null);
  const [mergeIds, setMergeIds] = useState("");
  const [selectedChildIds, setSelectedChildIds] = useState<string[]>([]);
  const [draftMergePath, setDraftMergePath] = useState<string | null>(null);
  const [draftMergeIds, setDraftMergeIds] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [mergeBusy, setMergeBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const { investigations } = useInvestigationList({ limit: 200, pollIntervalMs: 0 });
  const childOptions = useMemo(
    () =>
      investigations
        .filter((item) => item.parent_investigation_id === investigationId)
        .sort((a, b) => (b.started_at ?? "").localeCompare(a.started_at ?? "")),
    [investigations, investigationId],
  );

  const reload = useCallback(async () => {
    try {
      const res = await getResearchArtifactBlocks(investigationId);
      setBlocks(res.blocks);
      setErr(null);
    } catch (e) {
      setBlocks([]);
      setErr(e instanceof Error ? e.message : String(e));
    }
  }, [investigationId]);

  useEffect(() => {
    void reload();
  }, [reload]);

  const onExport = async () => {
    setBusy(true);
    setErr(null);
    try {
      const res = await exportResearchArtifact(investigationId);
      setExportPath(res.path);
      setTwinNotesPath(res.twin_notes_path);
      await reload();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const onDraftMerge = async () => {
    const ids = [investigationId, ...selectedChildIds, ...parseSiblingIds(mergeIds)];
    const uniqueIds = Array.from(new Set(ids));
    if (uniqueIds.length < 2) {
      setErr("Add at least one other research id to draft a merge.");
      return;
    }
    setMergeBusy(true);
    setErr(null);
    try {
      const res = await composeResearchArtifacts(uniqueIds, true);
      setDraftMergePath(res.draft_merge_path ?? res.path);
      setDraftMergeIds(uniqueIds);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setMergeBusy(false);
    }
  };

  const toggleChild = (childId: string) => {
    setSelectedChildIds((current) =>
      current.includes(childId)
        ? current.filter((id) => id !== childId)
        : [...current, childId],
    );
  };

  const empty = !blocks.length && !exportPath && !err;

  return (
    <div
      className={`border-t border-rule px-4 py-3 ${empty ? "text-sm text-ink-mute" : ""}`}
      data-testid={empty ? "artifact-shelf-empty" : "artifact-outline-shelf"}
    >
      <div className="mb-2 flex flex-wrap items-center gap-2">
        {empty ? (
          <p>No outline blocks yet — export after insights land in the graph.</p>
        ) : (
          <span className="text-xs font-semibold uppercase tracking-wide text-ink-mute">
            Write Lego · drag into outline
          </span>
        )}
        <LemonButton size="sm" disabled={busy} onClick={() => void onExport()}>
          {empty ? "Export research HTML" : "Export HTML"}
        </LemonButton>
        {exportPath ? (
          <span className="truncate font-mono text-[10px] text-ink-mute" title={exportPath}>
            {exportPath}
          </span>
        ) : null}
        {twinNotesPath ? (
          <span className="truncate font-mono text-[10px] text-ink-mute" title={twinNotesPath}>
            notes: {twinNotesPath}
          </span>
        ) : null}
      </div>
      {childOptions.length > 0 ? (
        <div className="mb-2 flex flex-wrap gap-1.5">
          {childOptions.map((child) => (
            <label
              key={child.investigation_id}
              className="inline-flex max-w-full items-center gap-1.5 rounded-hog border border-rule bg-ice-0 px-2 py-1 font-mono text-[11px] text-ink dark:bg-charcoal-2 dark:text-bright"
              title={child.question ?? child.investigation_id}
            >
              <input
                type="checkbox"
                checked={selectedChildIds.includes(child.investigation_id)}
                onChange={() => toggleChild(child.investigation_id)}
                className="h-3 w-3 accent-sun"
              />
              <span className="truncate">{child.question ?? child.investigation_id}</span>
            </label>
          ))}
        </div>
      ) : null}
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <input
          value={mergeIds}
          onChange={(e) => setMergeIds(e.target.value)}
          placeholder="other research ids"
          aria-label="Other research ids"
          className="min-w-[180px] flex-1 rounded-hog border border-rule bg-ice-0 px-2 py-1.5 font-mono text-[11px] text-ink outline-none placeholder:text-ink-mute focus:border-sun dark:bg-charcoal-2 dark:text-bright"
        />
        <LemonButton size="sm" disabled={mergeBusy} onClick={() => void onDraftMerge()}>
          Draft merge
        </LemonButton>
        {draftMergePath ? (
          <>
            <span className="truncate font-mono text-[10px] text-ink-mute" title={draftMergePath}>
              {draftMergePath}
            </span>
            {draftMergeIds.length >= 2 ? (
              <a
                href={draftMergeHref(draftMergeIds)}
                target="_blank"
                rel="noreferrer"
                className="inline-flex h-7 items-center rounded-hog px-2 font-mono text-[12px] font-semibold text-ink hover:bg-ice-3 dark:text-bright dark:hover:bg-charcoal-1"
              >
                Open draft
              </a>
            ) : null}
          </>
        ) : null}
      </div>
      {err ? <p className="text-sm text-emperor">{err}</p> : null}
      {blocks.length > 0 ? (
        <ul className="flex flex-col gap-1.5 max-h-40 overflow-y-auto">
          {blocks.map((b) => (
            <li
              key={b.node_id}
              draggable
              onDragStart={(e) => startDrag(e, b)}
              className="cursor-grab rounded border border-rule bg-ice-1 px-2 py-1.5 text-sm active:cursor-grabbing"
              title="Drag to Write outline"
            >
              <span className="text-[10px] uppercase text-ocean">{b.kind}</span>
              <p className="line-clamp-2 text-ink">{b.label}</p>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
