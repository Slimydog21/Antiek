import { useCallback, useEffect, useRef, useState, type DragEvent } from "react";

import {
  exportResearchArtifact,
  getResearchArtifactBlocks,
  getResearchArtifactClaims,
  type ResearchArtifactBlock,
  type ResearchArtifactClaimsResponse,
} from "../../lib/api";
import { artifactKindToBlockKind } from "../../lib/artifactBlocks";
import {
  DRAG_MIME,
  type PaletteDragPayload,
} from "../CreationStudio/BlockPalette";
import LemonButton from "../../components/lemon/LemonButton";
import { openWindow } from "../../components/windows/openWindow";
import { useAuth } from "../../lib/auth";
import { openClaimInspector } from "../../workspace/actions";

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
  const [claimSupports, setClaimSupports] = useState<ResearchArtifactClaimsResponse | null>(null);
  const [exportUrl, setExportUrl] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const { sessionGeneration } = useAuth();
  const requestGeneration = useRef(0);
  const currentIdentity = `${sessionGeneration}:${investigationId}`;
  const identityRef = useRef(currentIdentity);
  identityRef.current = currentIdentity;

  const reload = useCallback(async () => {
    const generation = ++requestGeneration.current;
    const [blocksResult, claimsResult] = await Promise.allSettled([
      getResearchArtifactBlocks(investigationId),
      getResearchArtifactClaims(investigationId),
    ]);
    if (generation !== requestGeneration.current) return;
    if (blocksResult.status === "fulfilled") setBlocks(blocksResult.value.blocks);
    else setBlocks([]);
    if (claimsResult.status === "fulfilled") setClaimSupports(claimsResult.value);
    else setClaimSupports(null);
    const failures = [blocksResult, claimsResult]
      .filter((result): result is PromiseRejectedResult => result.status === "rejected")
      .map((result) => result.reason instanceof Error ? result.reason.message : String(result.reason));
    setErr(failures.length === 2 ? failures.join(" · ") : null);
  }, [investigationId, sessionGeneration]);

  useEffect(() => {
    ++requestGeneration.current;
    setBlocks([]);
    setClaimSupports(null);
    setExportUrl(null);
    setErr(null);
    setBusy(false);
    void reload();
    return () => { ++requestGeneration.current; };
  }, [reload]);

  const onExport = async () => {
    const startedFor = currentIdentity;
    setBusy(true);
    setErr(null);
    try {
      const res = await exportResearchArtifact(investigationId);
      if (identityRef.current !== startedFor) return;
      setExportUrl(res.view_url);
      openWindow("research_artifact", { investigationId }, {
        id: `win:research-artifact:${sessionGeneration}:${investigationId}`,
      });
      await reload();
    } catch (e) {
      if (identityRef.current !== startedFor) return;
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      if (identityRef.current === startedFor) setBusy(false);
    }
  };

  if (!blocks.length && !claimSupports?.claims.length && !exportUrl && !err) {
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
        {exportUrl ? (
          <a
            className="truncate text-[10px] text-ocean underline"
            href={exportUrl}
            target="_blank"
            rel="noreferrer"
          >
            Open private HTML
          </a>
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
      {claimSupports?.claims.length ? (
        <div className="mt-3 border-t border-rule pt-2">
          <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-ink-mute">Claim support · inspect provenance</p>
          <ul className="flex max-h-40 flex-col gap-1.5 overflow-y-auto">
            {claimSupports.claims.map((claim) => (
              <li key={claim.claim_index}>
                <button
                  type="button"
                  className="w-full rounded border border-rule bg-ice-1 px-2 py-1.5 text-left text-sm hover:bg-sun/10"
                  onClick={() => openClaimInspector({
                    claimId: `artifact-${claim.claim_index}`,
                    investigationId,
                    claimIndex: claim.claim_index,
                    contentHash: claimSupports.content_hash,
                    sessionGeneration,
                  })}
                >
                  <span className="line-clamp-2 text-ink">{claim.claim}</span>
                  <span className="text-[10px] text-ink-mute">{claim.supporting_chunk_ids.length} direct · {claim.inherited_support.length} inherited</span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}
