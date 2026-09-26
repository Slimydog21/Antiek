import { useEffect, useState } from "react";

import { openWindow, readerWindowId } from "../../components/windows/openWindow";
import type { PaletteDragPayload } from "../CreationStudio/BlockPalette";
import { DRAG_MIME } from "../CreationStudio/BlockPalette";
import {
  listFolders,
  searchRepository,
  type FolderSummary,
  type RepositoryHit,
} from "./writeApi";

/**
 * Block repository — the tap-to-add block picker (Product Depth SPR-07 M1).
 *
 * The supply side of the Write loop: the shelves the writer pulls lego blocks
 * (research insight / question / claim notes — the SPR-03 distill output) into
 * the outline from. It REPLACES CreationStudio's "Attach by id" form — the
 * paste-a-UUID dead-end (CreationStudio:336,362) the Write experience-spec
 * flagged as structural — with a search-first picker where a block is added by
 * a single TAP. Drag is kept (the same `PaletteDragPayload` / `DRAG_MIME`
 * envelope the shipped `useOutlineDrop` consumes), so the outline accepts a
 * drop OR a tap without a second drag system.
 *
 * NO-ID INVARIANT (SPR-07 M1): a block is shown by its TEXT and provenance
 * (the source title + tier), never its `node_id`. The id rides the drag
 * payload / the tap callback for the place-block API; it is never rendered.
 *
 * This is the routed sibling of `Write/Repository/Repository.tsx` (the
 * shipped-but-orphaned drag surface): it adds the tap affordance + the
 * onSelect callback the routed outline wires to, and lives at the Write-mode
 * level so the door's Home composes it directly.
 */
export interface BlockRepositoryProps {
  /** Tap-to-add: the host places the tapped block into the active section. */
  onAdd: (hit: RepositoryHit) => void;
  /** Optional folder filter; null = the whole repository. */
  initialFolderId?: string | null;
  /** The piece being written, when the shelf is open beside one (the write
   *  origin context, reading-global SPR-02). Absent ⇒ repository hits open
   *  the reader WITHOUT an origin — lawful, nothing changes. */
  deliverableId?: string | null;
  className?: string;
}

export default function BlockRepository({
  onAdd,
  initialFolderId = null,
  deliverableId = null,
  className,
}: BlockRepositoryProps) {
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
    const handle = setTimeout(() => {
      setLoading(true);
      setError(null);
      searchRepository({ q: query, folderId: activeFolder ?? undefined, limit: 50 })
        .then((h) => {
          if (!cancelled) setHits(h);
        })
        .catch(() => {
          if (!cancelled) {
            // The repository search is graph-only (no provider key) — an error
            // here is a real backend problem, shown plainly, never faked away.
            setError("Couldn't load your notes. Try again.");
            setHits([]);
          }
        })
        .finally(() => {
          if (!cancelled) setLoading(false);
        });
    }, 250);
    return () => {
      cancelled = true;
      clearTimeout(handle);
    };
  }, [query, activeFolder]);

  return (
    <div
      className={"flex h-full min-h-0 flex-col text-sm " + (className ?? "")}
      data-mode="write-block-repository"
    >
      <div className="flex items-baseline justify-between px-1 pb-2">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-ink dark:text-bright">
          Your blocks
        </h2>
        {loading && <span className="text-xs text-ink-mute dark:text-moonlight">searching…</span>}
      </div>

      <input
        type="search"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="Search insights, questions, claims…"
        className="mb-2 w-full rounded border border-rule px-3 py-1.5 focus:outline-none focus:ring-2 focus:ring-sun dark:border-charcoal-1"
      />

      {folders.length > 0 && (
        <div className="mb-2 flex flex-wrap gap-1">
          <FolderChip
            label="All"
            active={activeFolder === null}
            onClick={() => setActiveFolder(null)}
          />
          {folders.map((f) => (
            <FolderChip
              key={f.folder_id}
              label={`${f.name} · ${f.member_count}`}
              active={activeFolder === f.folder_id}
              onClick={() => setActiveFolder(f.folder_id)}
            />
          ))}
        </div>
      )}

      {error && <p className="px-1 text-xs text-emperor">{error}</p>}

      <ul className="min-h-0 flex-1 space-y-1 overflow-y-auto">
        {hits.map((hit) => (
          <li key={hit.node_id} className="flex items-stretch gap-1">
            <button
              type="button"
              draggable
              onClick={() => onAdd(hit)}
              onDragStart={(e) => {
                // Keep drag: the same envelope the shipped outline drop reads.
                const payload: PaletteDragPayload = {
                  from: "palette",
                  block_kind: "insight",
                  block_id: hit.node_id, // the node — the drop/tap preserves it
                  label: hit.label,
                };
                e.dataTransfer.setData(DRAG_MIME, JSON.stringify(payload));
                e.dataTransfer.effectAllowed = "copy";
              }}
              title="Tap to add to the outline (or drag)"
              className="min-w-0 flex-1 cursor-grab rounded border border-rule bg-ice-0 px-2 py-1.5 text-left hover:border-sun-deep active:cursor-grabbing dark:border-charcoal-1 dark:bg-charcoal-2"
            >
              <p className="truncate font-serif text-ink dark:text-bright">{hit.label}</p>
              {(hit.document_title || hit.source_tier != null) && (
                <p className="truncate text-xxs text-ink-mute dark:text-moonlight">
                  {hit.document_title ?? "your note"}
                  {hit.source_tier != null ? ` · tier ${hit.source_tier}` : ""}
                </p>
              )}
            </button>
            {/* Reading-global SPR-02: a hit with source identity opens (or
                focuses) the ONE reader window on its source document. The
                write origin rides when the shelf is beside a piece. */}
            {hit.document_id && (
              <button
                type="button"
                data-open-in-reader
                onClick={() =>
                  openWindow(
                    "reader",
                    {
                      documentId: hit.document_id!,
                      ...(deliverableId
                        ? { origin: { from: "write" as const, id: deliverableId } }
                        : {}),
                    },
                    { id: readerWindowId(hit.document_id!) },
                  )
                }
                title="Open the source in the reader"
                className="shrink-0 rounded border border-rule px-1.5 font-mono text-xxs text-shadow-1 hover:text-ink dark:border-charcoal-1 dark:text-moonlight dark:hover:text-bright"
              >
                read ↗
              </button>
            )}
          </li>
        ))}
        {!loading && hits.length === 0 && !error && (
          <li className="px-2 py-4 text-xs italic text-ink-mute dark:text-moonlight">
            No blocks{activeFolder ? " in this folder" : ""} yet. Your research
            notes — insights, open questions, claims — appear here to tap into
            the outline. Run a research to fill the shelf.
          </li>
        )}
      </ul>
    </div>
  );
}

function FolderChip({
  label,
  active,
  onClick,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={
        "rounded-full border px-2 py-0.5 text-xs " +
        (active
          ? "border-sun-deep bg-sun-deep/15 text-sun-deep"
          : "border-rule text-ink-soft hover:border-sun-deep dark:border-charcoal-1")
      }
    >
      {label}
    </button>
  );
}
