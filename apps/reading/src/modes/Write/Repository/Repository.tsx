import { useEffect, useState } from "react";

import type { PaletteDragPayload } from "../../CreationStudio/BlockPalette";
import { DRAG_MIME } from "../../CreationStudio/BlockPalette";
import { emitWernerExperience } from "../../../werner/reactionBus";
import {
  listFolders,
  searchRepository,
  type FolderSummary,
  type RepositoryHit,
} from "../writeApi";

/**
 * Block repository (specs/write/ SPR-03 M1–M3).
 *
 * The supply side of Write — the shelves the writer pulls lego blocks
 * from. Folders are cross-investigation **views over graph nodes** (not
 * copies; the backend enforces multi-membership = one node), and each
 * result is a native HTML5 drag source emitting the existing palette
 * envelope (``PaletteDragPayload`` / ``DRAG_MIME``). The outline's drop
 * handler (``useOutlineDrop``) turns the drop into an OutlineBlock that
 * references the SAME node — provenance preserved (tested in
 * dragToOutline.test.ts).
 *
 * Reuses the shared `/write` REST surface; the drag contract is shared
 * with CreationStudio's BlockPalette so the outline accepts drops from
 * either source without a second drag system.
 */
export interface RepositoryProps {
  /** Optional folder filter; null = the whole repository. */
  initialFolderId?: string | null;
  className?: string;
}

export function Repository({ initialFolderId = null, className }: RepositoryProps) {
  const [query, setQuery] = useState("");
  const [folders, setFolders] = useState<FolderSummary[]>([]);
  const [activeFolder, setActiveFolder] = useState<string | null>(initialFolderId);
  const [hits, setHits] = useState<RepositoryHit[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listFolders().then(setFolders).catch(() => setFolders([]));
  }, []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    searchRepository({ q: query, folderId: activeFolder ?? undefined, limit: 50 })
      .then((h) => {
        if (!cancelled) setHits(h);
      })
      .catch((e) => {
        if (!cancelled) setError(String(e));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [query, activeFolder]);

  return (
    <div className={"flex h-full text-sm " + (className ?? "")} data-mode="write-repository">
      {/* Folders — cross-investigation views over nodes. */}
      <aside className="w-48 shrink-0 border-r border-rule dark:border-charcoal-1 pr-2 overflow-y-auto">
        <button
          type="button"
          onClick={() => setActiveFolder(null)}
          className={
            "block w-full text-left px-2 py-1 rounded " +
            (activeFolder === null ? "bg-ocean/15 text-ocean" : "text-ink-soft hover:bg-ice-2")
          }
        >
          All blocks
        </button>
        {folders.map((f) => (
          <button
            key={f.folder_id}
            type="button"
            onClick={() => setActiveFolder(f.folder_id)}
            className={
              "flex w-full items-center justify-between px-2 py-1 rounded " +
              (activeFolder === f.folder_id ? "bg-ocean/15 text-ocean" : "text-ink-soft hover:bg-ice-2")
            }
          >
            <span className="truncate">{f.name}</span>
            <span className="ml-2 text-[10px] text-ink-mute">{f.member_count}</span>
          </button>
        ))}
      </aside>

      {/* Search + draggable results. */}
      <div className="flex-1 flex flex-col pl-3 min-w-0">
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search insights, questions, claims…"
          className="w-full px-3 py-1.5 mb-2 border border-rule dark:border-charcoal-1 rounded focus:outline-none focus:ring-2 focus:ring-sun"
        />
        {error && <p className="text-xs text-emperor">{error}</p>}
        {loading && <p className="text-xs text-ink-mute">Searching…</p>}
        <ul className="flex-1 overflow-y-auto space-y-1">
          {hits.map((hit) => (
            <li
              key={hit.node_id}
              draggable
              onDragStart={(e) => {
                const payload: PaletteDragPayload = {
                  from: "palette",
                  block_kind: "insight",
                  block_id: hit.node_id, // the node — drop preserves it
                  label: hit.label,
                };
                e.dataTransfer.setData(DRAG_MIME, JSON.stringify(payload));
                e.dataTransfer.effectAllowed = "copy";
              }}
              className="px-2 py-1.5 border border-rule dark:border-charcoal-1 rounded cursor-grab hover:border-ocean bg-ice-0 dark:bg-charcoal-2"
              title="Drag into the outline"
            >
              <p className="font-serif text-ink dark:text-bright truncate">{hit.label}</p>
              {hit.document_title && (
                <p className="text-[10px] text-ink-mute truncate">
                  {hit.document_title}
                  {hit.source_tier != null ? ` · tier ${hit.source_tier}` : ""}
                </p>
              )}
            </li>
          ))}
          {!loading && hits.length === 0 && (
            <li className="text-xs text-ink-mute italic px-2 py-4">
              No blocks{activeFolder ? " in this folder" : ""}. Research notes appear here as
              insight/question/claim nodes to drag into your outline.
            </li>
          )}
        </ul>
      </div>
    </div>
  );
}

export default Repository;
