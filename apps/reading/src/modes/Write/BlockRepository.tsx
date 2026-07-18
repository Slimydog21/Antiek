import { useEffect, useState } from "react";

import type { PaletteDragPayload } from "../CreationStudio/BlockPalette";
import { DRAG_MIME } from "../CreationStudio/BlockPalette";
import { emitWernerExperience } from "../../werner/reactionBus";
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
  className?: string;
}

export default function BlockRepository({
  onAdd,
  initialFolderId = null,
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
        {loading && <span className="text-[11px] text-ink-mute dark:text-moonlight">searching…</span>}
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
            onClick={() => { emitWernerExperience("highlight"); setActiveFolder(null); }}
          />
          {folders.map((f) => (
            <FolderChip
              key={f.folder_id}
              label={`${f.name} · ${f.member_count}`}
              active={activeFolder === f.folder_id}
              onClick={() => { emitWernerExperience("highlight"); setActiveFolder(f.folder_id); }}
            />
          ))}
        </div>
      )}

      {error && <p className="px-1 text-xs text-emperor">{error}</p>}

      <ul className="min-h-0 flex-1 space-y-1 overflow-y-auto">
        {hits.map((hit) => (
          <li key={hit.node_id}>
            <button
              type="button"
              draggable
              onClick={() => { emitWernerExperience("highlight"); onAdd(hit); }}
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
              className="w-full cursor-grab rounded border border-rule bg-ice-0 px-2 py-1.5 text-left hover:border-ocean active:cursor-grabbing dark:border-charcoal-1 dark:bg-charcoal-2"
            >
              <p className="truncate font-serif text-ink dark:text-bright">{hit.label}</p>
              {(hit.document_title || hit.source_tier != null) && (
                <p className="truncate text-[10px] text-ink-mute dark:text-moonlight">
                  {hit.document_title ?? "your note"}
                  {hit.source_tier != null ? ` · tier ${hit.source_tier}` : ""}
                </p>
              )}
            </button>
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
        "rounded-full border px-2 py-0.5 text-[11px] " +
        (active
          ? "border-ocean bg-ocean/15 text-ocean"
          : "border-rule text-ink-soft hover:border-ocean dark:border-charcoal-1")
      }
    >
      {label}
    </button>
  );
}
