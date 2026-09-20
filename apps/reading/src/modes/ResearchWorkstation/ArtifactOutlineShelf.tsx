import { useCallback, useEffect, useMemo, useState, type DragEvent } from "react";

import {
  API_BASE,
  composeResearchArtifacts,
  exportResearchArtifact,
  getResearchArtifactBlocks,
  type ResearchArtifactBlock,
} from "../../lib/api";
import { getArtifactStatus, type ArtifactStatus } from "../../api/styles";
import { useInvestigationList } from "../../hooks/useInvestigationList";
import {
  DRAG_MIME,
  type PaletteDragPayload,
} from "../CreationStudio/BlockPalette";
import LemonButton from "../../components/lemon/LemonButton";
import StyleWheel from "./StyleWheel";
import { useChaseDraftHandoffs } from "./chaseHandoffs";
import { artifactPalettePayload } from "../../lib/artifactDragPayload";

/**
 * ANT-AHT SPR-AHT-06 — draggable insight/question blocks sourced from
 * GET /research/{id}/artifact/blocks. Drops use the same palette envelope
 * as Repository / BlockPalette so Write outline preserves graph_node provenance.
 */
export interface ArtifactOutlineShelfProps {
  investigationId: string;
}

function startDrag(e: DragEvent, block: ResearchArtifactBlock) {
  const payload: PaletteDragPayload = artifactPalettePayload(block);
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
  const [blocksLoaded, setBlocksLoaded] = useState(false);
  const [exportPath, setExportPath] = useState<string | null>(null);
  const [notesPath, setNotesPath] = useState<string | null>(null);
  const [mergeIds, setMergeIds] = useState("");
  const [selectedChildIds, setSelectedChildIds] = useState<string[]>([]);
  const [selectedHandoffIds, setSelectedHandoffIds] = useState<string[]>([]);
  const [draftMergePath, setDraftMergePath] = useState<string | null>(null);
  const [draftMergeIds, setDraftMergeIds] = useState<string[]>([]);
  const [artifactStatus, setArtifactStatus] = useState<ArtifactStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [mergeBusy, setMergeBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const { investigations } = useInvestigationList({ limit: 200, pollIntervalMs: 0 });
  const chaseHandoffs = useChaseDraftHandoffs(investigationId);
  const childOptions = useMemo(
    () =>
      investigations
        .filter((item) => item.parent_investigation_id === investigationId)
        .sort((a, b) => (b.started_at ?? "").localeCompare(a.started_at ?? "")),
    [investigations, investigationId],
  );
  const handoffOptions = useMemo(() => {
    const serverChildIds = new Set(childOptions.map((child) => child.investigation_id));
    return chaseHandoffs.filter(
      (handoff) => !serverChildIds.has(handoff.child_investigation_id),
    );
  }, [chaseHandoffs, childOptions]);

  const reload = useCallback(async () => {
    try {
      const res = await getResearchArtifactBlocks(investigationId);
      setBlocks(res.blocks);
      setBlocksLoaded(true);
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
      setNotesPath(res.twin_notes_path);
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

  const onDraftMerge = async () => {
    const ids = [
      investigationId,
      ...selectedChildIds,
      ...selectedHandoffIds,
      ...parseSiblingIds(mergeIds),
    ];
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

  const toggleHandoff = (childId: string) => {
    setSelectedHandoffIds((current) =>
      current.includes(childId)
        ? current.filter((id) => id !== childId)
        : [...current, childId],
    );
  };

  if (!blocks.length && !exportPath && !err) {
    return (
      <div className="border-t border-rule" data-testid="artifact-shelf-empty">
        <div className="px-4 py-3 text-sm text-ink-mute">
          <p className="mb-2">No outline blocks yet — export after insights land in the graph.</p>
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <LemonButton size="sm" disabled={busy} onClick={() => void onExport()}>
              Export research HTML
            </LemonButton>
            <a
              href={`${API_BASE}/research/${encodeURIComponent(investigationId)}/artifact.html`}
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs underline decoration-dotted underline-offset-2 text-ink-mute hover:text-ink"
              data-testid="research-artifact-view-html"
            >
              View HTML
            </a>
            {exportPath ? (
              <span className="truncate font-mono text-[10px] text-ink-mute" title={exportPath}>
                {exportPath}
              </span>
            ) : null}
            {notesPath ? (
              <span className="truncate font-mono text-[10px] text-ink-mute" title={notesPath}>
                notes: {notesPath}
              </span>
            ) : null}
          </div>
          {blocksLoaded && childOptions.length > 0 ? (
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
          {blocksLoaded && handoffOptions.length > 0 ? (
            <div className="mb-2 flex flex-col gap-1.5">
              <span className="text-[10px] font-mono uppercase tracking-wide text-ink-mute">
                Saved chase handoffs
              </span>
              {handoffOptions.map((handoff) => (
                <label
                  key={handoff.child_investigation_id}
                  className="inline-flex max-w-full items-center gap-1.5 rounded-hog border border-rule bg-ice-0 px-2 py-1 font-mono text-[11px] text-ink dark:bg-charcoal-2 dark:text-bright"
                  title={handoff.source_passage}
                >
                  <input
                    type="checkbox"
                    checked={selectedHandoffIds.includes(handoff.child_investigation_id)}
                    onChange={() => toggleHandoff(handoff.child_investigation_id)}
                    className="h-3 w-3 accent-sun"
                  />
                  <span className="truncate">{handoff.source_passage}</span>
                </label>
              ))}
            </div>
          ) : null}
          {blocksLoaded ? (
            <div className="mb-2 flex flex-wrap items-center gap-2">
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
          ) : null}
          {blocksLoaded && err ? (
            <p className="text-sm text-emperor">{err}</p>
          ) : null}
        </div>
        {artifactStatus ? (
          <StyleWheel
            key={artifactStatus.artifact_id}
            artifactId={artifactStatus.artifact_id}
            investigationId={artifactStatus.investigation_id}
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
          <a
            href={`${API_BASE}/research/${encodeURIComponent(investigationId)}/artifact.html`}
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs underline decoration-dotted underline-offset-2 text-ink-mute hover:text-ink"
            data-testid="research-artifact-view-html"
          >
            View HTML
          </a>
          {exportPath ? (
            <span className="truncate font-mono text-[10px] text-ink-mute" title={exportPath}>
              {exportPath}
            </span>
          ) : null}
          {notesPath ? (
            <span className="truncate font-mono text-[10px] text-ink-mute" title={notesPath}>
              notes: {notesPath}
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
        {handoffOptions.length > 0 ? (
          <div className="mb-2 flex flex-col gap-1.5">
            <span className="text-[10px] font-mono uppercase tracking-wide text-ink-mute">
              Saved chase handoffs
            </span>
            {handoffOptions.map((handoff) => (
              <label
                key={handoff.child_investigation_id}
                className="inline-flex max-w-full items-center gap-1.5 rounded-hog border border-rule bg-ice-0 px-2 py-1 font-mono text-[11px] text-ink dark:bg-charcoal-2 dark:text-bright"
                title={handoff.source_passage}
              >
                <input
                  type="checkbox"
                  checked={selectedHandoffIds.includes(handoff.child_investigation_id)}
                  onChange={() => toggleHandoff(handoff.child_investigation_id)}
                  className="h-3 w-3 accent-sun"
                />
                <span className="truncate">{handoff.source_passage}</span>
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
        <ul className="flex flex-col gap-1.5 max-h-40 overflow-y-auto">
          {blocks.map((b) => (
            <li
              key={b.node_id}
              draggable
              onDragStart={(e) => startDrag(e, b)}
              className="cursor-grab rounded border border-rule bg-ice-1 px-2 py-1.5 text-sm active:cursor-grabbing"
              title="Drag to Write outline"
            >
              <span className="text-[10px] uppercase text-sun-deep">{b.kind}</span>
              <p className="line-clamp-2 text-ink">{b.label}</p>
            </li>
          ))}
        </ul>
      </div>
      {artifactStatus ? (
        <StyleWheel
          key={`${artifactStatus.artifact_id}:${exportPath ?? "persisted"}`}
          artifactId={artifactStatus.artifact_id}
          investigationId={artifactStatus.investigation_id}
          initialStyle={artifactStatus.selected_style}
        />
      ) : null}
    </div>
  );
}
