import { useCallback, useEffect, useState, type DragEvent } from "react";

import {
  exportResearchArtifact,
  getResearchArtifactBlocks,
  type ResearchArtifactBlock,
} from "../../lib/api";
import { artifactKindToBlockKind } from "../../lib/artifactBlocks";
import {
  DRAG_MIME,
  type PaletteDragPayload,
} from "../CreationStudio/BlockPalette";
import LemonButton from "../../components/lemon/LemonButton";
import { emitWernerExperience } from "../../werner/reactionBus";

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

export default function ArtifactOutlineShelf({
  investigationId,
}: ArtifactOutlineShelfProps) {
  const [blocks, setBlocks] = useState<ResearchArtifactBlock[]>([]);
  const [exportPath, setExportPath] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

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
      // Living-TV: HTML artifact export is a happy craft beat.
      emitWernerExperience("piece_started");
      await reload();
    } catch (e) {
      emitWernerExperience("fail");
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  if (!blocks.length && !exportPath && !err) {
    return (
      <div className="border-t border-rule px-4 py-3 text-sm text-ink-mute" data-testid="artifact-shelf-empty">
        <p className="mb-2">No outline blocks yet — export after insights land in the graph.</p>
        <LemonButton size="sm" disabled={busy} onClick={() => void onExport()}>
          Export research HTML
        </LemonButton>
      </div>
    );
  }

  return (
    <div className="border-t border-rule px-4 py-3" data-testid="artifact-outline-shelf">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <span className="text-xs font-semibold uppercase tracking-wide text-ink-mute">
          Write Lego · drag into outline
        </span>
        <LemonButton size="sm" disabled={busy} onClick={() => void onExport()}>
          Export HTML
        </LemonButton>
        {exportPath ? (
          <span className="truncate font-mono text-[10px] text-ink-mute" title={exportPath}>
            {exportPath}
          </span>
        ) : null}
      </div>
      {err ? <p className="text-sm text-emperor">{err}</p> : null}
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
    </div>
  );
}