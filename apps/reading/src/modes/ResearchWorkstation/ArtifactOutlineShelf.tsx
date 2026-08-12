import { useCallback, useEffect, useState, type DragEvent } from "react";

import {
  exportResearchArtifact,
  getResearchArtifactBlocks,
  type ResearchArtifactBlock,
} from "../../lib/api";
import { getArtifactStatus, type ArtifactStatus } from "../../api/styles";
import { artifactPalettePayload } from "../../lib/artifactDragPayload";
import { DRAG_MIME } from "../CreationStudio/BlockPalette";
import LemonButton from "../../components/lemon/LemonButton";
import StyleWheel from "./StyleWheel";

/**
 * ANT-AHT SPR-AHT-06 — draggable insight/question blocks sourced from
 * GET /research/{id}/artifact/blocks. Drops use the same palette envelope
 * as Repository / BlockPalette so Write outline preserves graph_node provenance.
 */
export interface ArtifactOutlineShelfProps {
  investigationId: string;
}

function startDrag(e: DragEvent, block: ResearchArtifactBlock) {
  const payload = artifactPalettePayload(block);
  e.dataTransfer.setData(DRAG_MIME, JSON.stringify(payload));
  e.dataTransfer.effectAllowed = "copy";
}

export default function ArtifactOutlineShelf({
  investigationId,
}: ArtifactOutlineShelfProps) {
  const [blocks, setBlocks] = useState<ResearchArtifactBlock[]>([]);
  const [exportPath, setExportPath] = useState<string | null>(null);
  const [artifactStatus, setArtifactStatus] = useState<ArtifactStatus | null>(null);
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

  useEffect(() => {
    const controller = new AbortController();
    getArtifactStatus(investigationId, controller.signal)
      .then((status) => {
        if (!controller.signal.aborted) setArtifactStatus(status);
      })
      .catch(() => {
        if (!controller.signal.aborted) setArtifactStatus(null);
      });
    return () => controller.abort();
  }, [investigationId]);

  const onExport = async () => {
    setBusy(true);
    setErr(null);
    try {
      const res = await exportResearchArtifact(investigationId);
      setExportPath(res.path);
      const status = await getArtifactStatus(investigationId);
      if (!status || status.artifact_id !== res.artifact_id) {
        throw new Error("Export completed without a matching durable artifact identity.");
      }
      setArtifactStatus(status);
      await reload();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  if (!blocks.length && !exportPath && !err) {
    return (
      <div className="border-t border-rule" data-testid="artifact-shelf-empty">
        <div className="px-4 py-3 text-sm text-ink-mute">
          <p className="mb-2">No outline blocks yet — export after insights land in the graph.</p>
          <LemonButton size="sm" disabled={busy} onClick={() => void onExport()}>
            Export research HTML
          </LemonButton>
        </div>
        {artifactStatus ? (
          <StyleWheel
            key={artifactStatus.artifact_id}
            artifactId={artifactStatus.artifact_id}
            initialStyle={artifactStatus.selected_style}
          />
        ) : null}
      </div>
    );
  }

  return (
    <div className="border-t border-rule" data-testid="artifact-outline-shelf">
      <div className="px-4 py-3">
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
      {artifactStatus ? (
        <StyleWheel
          key={`${artifactStatus.artifact_id}:${exportPath ?? "persisted"}`}
          artifactId={artifactStatus.artifact_id}
          initialStyle={artifactStatus.selected_style}
        />
      ) : null}
    </div>
  );
}
