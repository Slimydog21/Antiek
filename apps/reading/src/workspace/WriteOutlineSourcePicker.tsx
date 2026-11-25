/**
 * WriteOutlineSourcePicker — the keyboard half of source assignment (C5).
 *
 * The outline pane's block tabs took a source document by drag-and-drop
 * ONLY: an operator without a pointer had no path. This small in-pane
 * overlay is that path (WCAG 2.5.7's dragging-alternative discipline): it
 * lists exactly the candidates that produce a SourceDocumentDragPayload —
 * the open reader tabs (what SiblingStrip drags) and the repository search
 * hits that name a source document (what BlockRepository drags) — both
 * through the EXISTING stores/API, no parallel data path. Typing filters
 * (the tabs client-side, the repository through the same debounced search
 * the shelf uses); the arrows walk the list; Enter assigns through the
 * pane's one assignment callback — the same write path a drop takes; Esc
 * closes (a transient overlay: one Esc, one handler) and returns focus to
 * the block tab that opened it.
 *
 * The pattern is NewTabPickerContent's, shrunk to an in-pane overlay: a
 * filter input plus a role=listbox of focusable options, never a modal.
 */
import { useEffect, useMemo, useRef, useState } from "react";

import { EmptyState, LoadingState } from "../components/states";
import { searchRepository } from "../modes/Write/writeApi";
import { ESC_OVERLAY_PROPS } from "./escapeOverlay";
import { registerKeyboardOwner } from "./keyboardOwnership";
import { labelForTab } from "./tabLabels";
import { titleKey, useTabTitles, type TitleEntry } from "./tabTitles";
import { useTabTrees } from "./tabTreeStore";
import type { TabTree } from "./tabTree";
import type { SourceDocumentDragPayload } from "./WriteOutlinePane";

/** A section stays readable without the filter: this many rows, then a
 *  "type to filter" hint (NewTabPickerContent's rule). */
const MAX_SHOWN = 50;

/**
 * The source documents the open reader tabs can hand a block — the SAME
 * payload SiblingStrip puts on the drag: the tab's ref is the document id,
 * and only a real title (never a fallback noun or a passage) becomes the
 * document title. Deduped: two tabs on one document are one source.
 */
export function readerTabSources(
  trees: Record<string, TabTree | null>,
  entries: Record<string, TitleEntry>,
): SourceDocumentDragPayload[] {
  const seen = new Set<string>();
  const out: SourceDocumentDragPayload[] = [];
  for (const tree of Object.values(trees)) {
    if (!tree) continue;
    for (const node of Object.values(tree.nodes)) {
      if (node.kind !== "reader" || seen.has(node.ref)) continue;
      seen.add(node.ref);
      const parent = node.parent_tab_id ? (tree.nodes[node.parent_tab_id] ?? null) : null;
      const label = labelForTab(node, parent, entries[titleKey(node.kind, node.ref)]);
      out.push({
        document_id: node.ref,
        document_title: label.source === "title" ? label.text : null,
      });
    }
  }
  return out;
}

interface Candidate {
  key: string;
  payload: SourceDocumentDragPayload;
  title: string;
  subtitle: string;
}

export default function WriteOutlineSourcePicker({
  blockLabel,
  onPick,
  onClose,
  onDismiss,
}: {
  /** The block's display text, for the overlay's accessible name. */
  blockLabel: string;
  /** Enter on an option: the pane's one assignment callback (the drop path). */
  onPick: (payload: SourceDocumentDragPayload) => void;
  /** Esc / a pick: close and return focus to the block tab. */
  onClose: () => void;
  /** A pointer press outside: close quietly, focus stays where it landed
   *  (the overflow menu's rule). */
  onDismiss: () => void;
}) {
  const [filter, setFilter] = useState("");
  const [hits, setHits] = useState<SourceDocumentDragPayload[] | null>(null);
  const [searchFailed, setSearchFailed] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const filterRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  const trees = useTabTrees((s) => s.trees);
  const titleEntries = useTabTitles((s) => s.entries);
  const tabSources = useMemo(() => readerTabSources(trees, titleEntries), [trees, titleEntries]);

  // Opening puts focus in the filter (the picker's one text field).
  useEffect(() => {
    filterRef.current?.focus();
  }, []);

  // The repository half of the candidate set: the same debounced search the
  // shelf runs, kept to hits that NAME a source document (only those can
  // produce the assignment payload). A failure never blanks the open tabs.
  const needle = filter.trim().toLowerCase();
  useEffect(() => {
    let cancelled = false;
    const handle = setTimeout(() => {
      searchRepository({ q: needle || undefined, limit: 50 })
        .then((found) => {
          if (cancelled) return;
          setSearchFailed(false);
          setHits(
            found
              .filter((h): h is typeof h & { document_id: string } => !!h.document_id)
              .map((h) => ({ document_id: h.document_id, document_title: h.document_title })),
          );
        })
        .catch(() => {
          if (!cancelled) {
            setSearchFailed(true);
            setHits([]);
          }
        });
    }, 250);
    return () => {
      cancelled = true;
      clearTimeout(handle);
    };
  }, [needle]);

  // Esc is this overlay's while it is open (scope "overlay"; a hidden pane
  // leaves it for the active layer, A1c low 11). A pointer press outside
  // closes quietly.
  useEffect(() => {
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) onDismiss();
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape" || e.defaultPrevented || ref.current?.closest("[hidden]")) return;
      e.preventDefault();
      onClose();
    };
    document.addEventListener("mousedown", onDoc);
    const removeKeyboardOwner = registerKeyboardOwner(
      document,
      {
        id: "write.outline.sourcePicker",
        scope: "overlay",
        eligible: (e) => e.key === "Escape" && !e.defaultPrevented && !ref.current?.closest("[hidden]"),
      },
      onKey,
    );
    return () => {
      document.removeEventListener("mousedown", onDoc);
      removeKeyboardOwner();
    };
  }, [onClose, onDismiss]);

  const sections = useMemo(() => {
    const tabs: Candidate[] = tabSources
      .filter((s) => !needle || (s.document_title ?? "").toLowerCase().includes(needle))
      .map((s) => ({
        key: `tab:${s.document_id}`,
        payload: s,
        title: s.document_title ?? s.document_id,
        subtitle: "Open tab",
      }));
    const listed = new Set(tabs.map((t) => t.payload.document_id));
    const repo: Candidate[] = (hits ?? [])
      .filter((s) => !listed.has(s.document_id))
      .map((s) => ({
        key: `repo:${s.document_id}`,
        payload: s,
        title: s.document_title ?? s.document_id,
        subtitle: "Repository",
      }));
    return ([
      ["Open tabs", tabs],
      ["Repository", repo],
    ] as const)
      .map(([heading, entries]) => ({ heading, entries }))
      .filter((s) => s.entries.length > 0);
  }, [tabSources, hits, needle]);

  const options = () =>
    Array.from(listRef.current?.querySelectorAll<HTMLElement>('[role="option"]') ?? []);

  // Arrows walk the list (the filter's ArrowDown steps into it); Enter picks
  // the focused option. Scoped to the picker's own elements: it claims no
  // global key.
  const onListKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") {
      // preventDefault keeps the browser's own activation from double-firing
      // the click; jsdom has no activation behavior, so tests drive the same
      // path.
      const current = document.activeElement;
      if (current instanceof HTMLElement && current.getAttribute("role") === "option") {
        e.preventDefault();
        current.click();
      }
      return;
    }
    if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
    const items = options();
    if (items.length === 0) return;
    e.preventDefault();
    const cur = items.indexOf(document.activeElement as HTMLElement);
    const next =
      e.key === "ArrowDown"
        ? (cur + 1) % items.length
        : (cur - 1 + items.length) % items.length;
    items[next].focus();
  };

  return (
    <div
      ref={ref}
      role="dialog"
      aria-label={`Assign a source to ${blockLabel}`}
      data-source-picker=""
      {...ESC_OVERLAY_PROPS}
      className="absolute inset-x-2 top-10 z-10 rounded border border-hairline bg-ice-0 p-2 shadow-z2 dark:bg-charcoal-2 dark:shadow-z2-night"
    >
      <input
        ref={filterRef}
        type="search"
        value={filter}
        onChange={(e) => setFilter(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown") {
            const first = options()[0];
            if (first) {
              e.preventDefault();
              first.focus();
            }
          } else if (e.key === "Enter") {
            // Type + Enter assigns the top match without leaving the filter.
            const first = options()[0];
            if (first) {
              e.preventDefault();
              first.click();
            }
          }
        }}
        aria-label="Filter source documents"
        placeholder="Type to filter sources"
        className="mb-2 w-full rounded border border-hairline bg-ice-0 px-2 py-1 text-xs text-ink placeholder:text-shadow-1 dark:bg-charcoal-1 dark:text-bright dark:placeholder:text-moonlight focus-visible:outline focus-visible:outline-2 focus-visible:outline-sun"
      />
      {searchFailed ? (
        <p role="status" className="px-1 pb-1 text-xxs text-emperor" data-source-search-failed>
          The repository search didn&apos;t answer; your open tabs are still listed.
        </p>
      ) : null}
      {hits === null && sections.length === 0 ? (
        <LoadingState variant="inline" label="Looking up your sources" />
      ) : sections.length === 0 ? (
        <EmptyState
          variant="inline"
          art={false}
          title={needle ? `No sources match “${filter.trim()}”` : "No source documents yet"}
          body={needle ? undefined : "Open a document tab or run a research to fill the repository."}
        />
      ) : (
        <div
          ref={listRef}
          role="listbox"
          aria-label="Source documents"
          onKeyDown={onListKeyDown}
          className="max-h-[50vh] overflow-auto"
        >
          {sections.map((section) => (
            <section key={section.heading} aria-label={section.heading} className="mb-1 last:mb-0">
              <h3 className="px-1 pb-0.5 font-mono text-xxs uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                {section.heading}
              </h3>
              <ul>
                {section.entries.slice(0, MAX_SHOWN).map((entry) => (
                  <li key={entry.key}>
                    <button
                      type="button"
                      role="option"
                      aria-selected={false}
                      onClick={() => onPick(entry.payload)}
                      className="flex w-full items-baseline gap-1.5 rounded px-2 py-1 text-left hover:bg-ice-2 dark:hover:bg-charcoal-1 focus-visible:outline focus-visible:outline-2 focus-visible:outline-sun"
                    >
                      <span className="truncate text-xs text-ink dark:text-bright">{entry.title}</span>
                      <span className="shrink-0 text-xxs text-shadow-1 dark:text-moonlight">
                        {entry.subtitle}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
              {section.entries.length > MAX_SHOWN ? (
                <p className="px-2 pt-1 text-xxs text-shadow-1 dark:text-moonlight">
                  {section.entries.length - MAX_SHOWN} more — type to filter.
                </p>
              ) : null}
            </section>
          ))}
        </div>
      )}
    </div>
  );
}
