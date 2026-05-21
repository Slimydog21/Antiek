// SPR-06 / M3 — Library sidebar (folders + tags filter rail).
//
// Layout: a column on the left of the LibraryGrid with three buckets:
//   - "All"             — show every imported doc
//   - "Recent"          — opened or imported within the last 30 days
//   - <user folders>    — flat list, click to filter
// Tags get their own section under folders. Each click sets a single
// active filter (folder XOR tag XOR All XOR Recent). Multi-filter
// AND is out-of-scope this sprint.
//
// Per rigor #2 (fairness, steelman "drop folders/tags entirely"):
// the sidebar is rendered only when the user has folders OR tags
// OR more than ~8 documents — under that threshold a flat grid is
// less visually noisy. The threshold is intentionally low so most
// real users see the sidebar within their first session.

import { useCallback, useEffect, useState } from "react";

import { LemonButton } from "../../components/lemon";
import {
  type Folder,
  createFolder,
  deleteFolder,
  listFolders,
} from "../../../api/library/folders";
import { type Tag, listTags } from "../../../api/library/tags";

export type LibraryFilter =
  | { kind: "all" }
  | { kind: "recent" }
  | { kind: "folder"; folder_id: string; name: string }
  | { kind: "tag"; tag_id: string; name: string };

export interface SidebarProps {
  active: LibraryFilter;
  onFilterChange: (f: LibraryFilter) => void;
  /** Total document count — used to hide the sidebar under the
   * steelman threshold from rigor #2. */
  documentCount: number;
}

export function Sidebar({ active, onFilterChange, documentCount }: SidebarProps) {
  const [folders, setFolders] = useState<Folder[]>([]);
  const [tags, setTags] = useState<Tag[]>([]);
  const [newFolderName, setNewFolderName] = useState<string>("");
  const [showCreate, setShowCreate] = useState<boolean>(false);

  const reload = useCallback(async () => {
    setFolders(await listFolders());
    setTags(await listTags());
  }, []);

  useEffect(() => {
    void reload();
    // Listen for cross-window localStorage updates (multi-tab edits).
    const handler = (e: StorageEvent) => {
      if (
        e.key === "antiek.library.folders.v1" ||
        e.key === "antiek.library.tags.v1"
      ) {
        void reload();
      }
    };
    window.addEventListener("storage", handler);
    return () => window.removeEventListener("storage", handler);
  }, [reload]);

  const onCreateFolder = async () => {
    const name = newFolderName.trim();
    if (!name) return;
    await createFolder(name);
    setNewFolderName("");
    setShowCreate(false);
    await reload();
  };

  // Steelman threshold: hide sidebar entirely if the user has nothing
  // to organize. Returns null so the grid takes the full width.
  const hasContent = folders.length > 0 || tags.length > 0 || documentCount > 8;
  if (!hasContent) {
    return null;
  }

  return (
    <aside
      className="w-56 shrink-0 border-r-edge border-sun bg-ice-1 dark:bg-charcoal-1 p-3 space-y-4"
      data-testid="library-sidebar"
      aria-label="Library filters"
    >
      <nav className="space-y-1">
        <SidebarButton
          label="All"
          isActive={active.kind === "all"}
          onClick={() => onFilterChange({ kind: "all" })}
          testId="library-sidebar-all"
        />
        <SidebarButton
          label="Recent"
          isActive={active.kind === "recent"}
          onClick={() => onFilterChange({ kind: "recent" })}
          testId="library-sidebar-recent"
        />
      </nav>

      <section>
        <div className="flex items-center justify-between mb-1.5">
          <p className="font-mono text-[10px] uppercase tracking-wider text-shadow-1 dark:text-moonlight">
            Folders
          </p>
          <button
            type="button"
            onClick={() => setShowCreate((s) => !s)}
            aria-label="New folder"
            className="font-mono text-[12px] text-shadow-1 dark:text-moonlight hover:text-ink dark:hover:text-bright"
            data-testid="library-sidebar-new-folder"
          >
            +
          </button>
        </div>
        {showCreate && (
          <div className="flex gap-1 mb-2">
            <input
              type="text"
              value={newFolderName}
              onChange={(e) => setNewFolderName(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") void onCreateFolder();
              }}
              placeholder="Folder name"
              className="flex-1 text-[12px] font-sans text-ink dark:text-bright bg-ice-0 dark:bg-charcoal-2 border-edge border-sun rounded px-2 h-7"
              data-testid="library-sidebar-folder-input"
            />
            <LemonButton size="sm" variant="primary" onClick={() => void onCreateFolder()}>
              Add
            </LemonButton>
          </div>
        )}
        <ul className="space-y-1">
          {folders.length === 0 && (
            <li className="text-[12px] text-shadow-1 dark:text-moonlight italic">
              No folders yet.
            </li>
          )}
          {folders.map((f) => (
            <li key={f.folder_id} className="flex items-center gap-1 group">
              <SidebarButton
                label={f.name}
                isActive={active.kind === "folder" && active.folder_id === f.folder_id}
                onClick={() =>
                  onFilterChange({ kind: "folder", folder_id: f.folder_id, name: f.name })
                }
                testId="library-sidebar-folder"
              />
              <button
                type="button"
                onClick={async (e) => {
                  e.stopPropagation();
                  await deleteFolder(f.folder_id);
                  await reload();
                  if (active.kind === "folder" && active.folder_id === f.folder_id) {
                    onFilterChange({ kind: "all" });
                  }
                }}
                className="opacity-0 group-hover:opacity-100 transition-opacity text-shadow-1 dark:text-moonlight text-[12px] font-mono px-1"
                aria-label={`Delete folder ${f.name}`}
              >
                ×
              </button>
            </li>
          ))}
        </ul>
      </section>

      <section>
        <p className="font-mono text-[10px] uppercase tracking-wider text-shadow-1 dark:text-moonlight mb-1.5">
          Tags
        </p>
        {tags.length === 0 ? (
          <p className="text-[12px] text-shadow-1 dark:text-moonlight italic">
            No tags yet.
          </p>
        ) : (
          <ul className="space-y-1">
            {tags.map((t) => (
              <li key={t.tag_id}>
                <SidebarButton
                  label={`#${t.name}`}
                  isActive={active.kind === "tag" && active.tag_id === t.tag_id}
                  onClick={() =>
                    onFilterChange({ kind: "tag", tag_id: t.tag_id, name: t.name })
                  }
                  testId="library-sidebar-tag"
                />
              </li>
            ))}
          </ul>
        )}
      </section>
    </aside>
  );
}

function SidebarButton({
  label,
  isActive,
  onClick,
  testId,
}: {
  label: string;
  isActive: boolean;
  onClick: () => void;
  testId?: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      data-testid={testId}
      data-active={isActive}
      className={
        "block w-full text-left px-2 py-1 rounded-sm font-sans text-[13px] " +
        (isActive
          ? "bg-sun text-ink"
          : "text-ink dark:text-bright hover:bg-ice-3 dark:hover:bg-charcoal-2")
      }
    >
      {label}
    </button>
  );
}

export default Sidebar;
