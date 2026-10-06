import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";

import { LemonModal } from "../components/lemon/LemonModal";
import { EmptyState, ErrorState, LoadingState } from "../components/states";
import { listBooks, type BookSummary } from "../api/books";
import { listInvestigations, type InvestigationSummary } from "../lib/api";
import { spawnNewTab, type NewTabTarget } from "./newTab";

/**
 * NewTabPickerContent — the prefix+c picker (lazy-loaded by NewTabPicker):
 * the account's documents and investigations, filtered, one opening as a
 * fresh top-level tab in its own tree (newTab.spawnNewTab).
 *
 * The corpus is account-wide, so the lists do not re-scope with the
 * project selection — the project decides which TREE the tab files under,
 * never which surfaces exist. Type to filter; ArrowDown leaves the filter
 * for the list, the arrows walk it, Enter opens, Esc closes (LemonModal).
 */

interface PickEntry {
  id: string;
  target: NewTabTarget;
  title: string;
  subtitle: string;
}

/** A section stays readable without the filter: this many rows, then a
 *  "type to filter" hint. */
const MAX_SHOWN = 50;

function documentEntry(book: BookSummary): PickEntry {
  return {
    id: `doc:${book.document_id}`,
    target: { kind: "reader", ref: book.document_id, title: book.title },
    title: book.title ?? "Untitled document",
    subtitle: book.author ?? "Document",
  };
}

function investigationEntry(inv: InvestigationSummary): PickEntry {
  return {
    id: `inv:${inv.investigation_id}`,
    target: {
      kind: "research",
      ref: `/inv/${inv.investigation_id}`,
      title: inv.question ?? null,
    },
    title: inv.question ?? inv.investigation_id,
    subtitle: `Investigation · ${inv.investigation_id.slice(0, 8)}`,
  };
}

interface LoadState {
  status: "loading" | "ready" | "error";
  documents: PickEntry[];
  investigations: PickEntry[];
  /** The raw message, for "Copy error details" — never on screen. */
  detail: string | null;
}

export default function NewTabPickerContent({ onClose }: { onClose: () => void }) {
  const [filter, setFilter] = useState("");
  const [load, setLoad] = useState<LoadState>({
    status: "loading",
    documents: [],
    investigations: [],
    detail: null,
  });
  const filterRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  const reload = () => {
    setLoad((s) => ({ ...s, status: "loading", detail: null }));
    // Either list may fail alone (the books gate and the research index are
    // separate services): one failure never blanks the other section.
    void Promise.all([
      listBooks("all").then((r) => r.books.map(documentEntry)).catch((e: unknown) => ({ failed: e })),
      listInvestigations({ limit: 50 })
        .then((r) => r.investigations.map(investigationEntry))
        .catch((e: unknown) => ({ failed: e })),
    ]).then(([docs, invs]) => {
      const failed = [docs, invs].filter((r): r is { failed: unknown } => !Array.isArray(r));
      setLoad({
        status: failed.length === 2 ? "error" : "ready",
        documents: Array.isArray(docs) ? docs : [],
        investigations: Array.isArray(invs) ? invs : [],
        detail: failed.length
          ? failed.map((f) => (f.failed instanceof Error ? f.failed.message : String(f.failed))).join("; ")
          : null,
      });
    });
  };

  useEffect(reload, []);

  // Give focus back, on close, to whatever had it when the picker opened
  // (KeySheet's pattern: a layout effect reads it before the dialog's own
  // effect moves focus in).
  useLayoutEffect(() => {
    const opener = document.activeElement;
    return () => {
      if (opener instanceof HTMLElement && opener.isConnected) opener.focus();
    };
  }, []);

  const needle = filter.trim().toLowerCase();
  const matches = (e: PickEntry) =>
    !needle || `${e.title} ${e.subtitle}`.toLowerCase().includes(needle);
  const sections = useMemo(
    () =>
      ([
        ["Documents", load.documents],
        ["Investigations", load.investigations],
      ] as const)
        .map(([heading, entries]) => ({
          heading,
          entries: entries.filter(matches),
        }))
        .filter((s) => s.entries.length > 0 || !needle),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [load.documents, load.investigations, needle],
  );

  const options = () =>
    Array.from(listRef.current?.querySelectorAll<HTMLElement>('[role="option"]') ?? []);

  // Arrows walk the list (the filter's ArrowDown steps into it). Scoped to
  // the picker's own elements: it claims no global key.
  const onListKeyDown = (e: React.KeyboardEvent) => {
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

  const pick = (entry: PickEntry) => {
    onClose();
    void spawnNewTab(entry.target);
  };

  return (
    <LemonModal open onClose={onClose} title="New tab" size="sm">
      <div data-keymap-owner="tab.new">
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
            }
          }}
          aria-label="Filter documents and investigations"
          placeholder="Type to filter"
          className="mb-3 w-full rounded border border-hairline bg-ice-0 px-2.5 py-1.5 text-sm text-ink placeholder:text-shadow-1 dark:bg-charcoal-1 dark:text-bright dark:placeholder:text-moonlight focus-visible:outline focus-visible:outline-2 focus-visible:outline-sun"
        />

        {load.status === "loading" ? (
          <LoadingState variant="inline" label="Opening your documents and investigations" />
        ) : load.status === "error" ? (
          <ErrorState
            variant="inline"
            title="Couldn't open your documents and investigations"
            body="Your work is untouched; only the lists didn't load."
            detail={load.detail}
            onRetry={reload}
          />
        ) : sections.length === 0 ? (
          <EmptyState
            variant="inline"
            art={false}
            title={needle ? `Nothing matches “${filter.trim()}”` : "Nothing to open yet"}
            body={needle ? undefined : "Documents and investigations you add appear here."}
          />
        ) : (
          <div
            ref={listRef}
            role="listbox"
            aria-label="Open as a new tab"
            onKeyDown={onListKeyDown}
            className="max-h-[60vh] overflow-auto"
          >
            {sections.map((section) => (
              <section key={section.heading} aria-label={section.heading} className="mb-2 last:mb-0">
                <h3 className="px-1 pb-1 font-mono text-xxs uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                  {section.heading}
                </h3>
                <ul>
                  {section.entries.slice(0, MAX_SHOWN).map((entry) => (
                    <li key={entry.id}>
                      <button
                        type="button"
                        role="option"
                        aria-selected={false}
                        onClick={() => pick(entry)}
                        className="flex w-full flex-col rounded px-2 py-1.5 text-left hover:bg-ice-2 dark:hover:bg-charcoal-1 focus-visible:outline focus-visible:outline-2 focus-visible:outline-sun"
                      >
                        <span className="truncate text-sm text-ink dark:text-bright">{entry.title}</span>
                        <span className="truncate text-xs text-shadow-1 dark:text-moonlight">
                          {entry.subtitle}
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
                {section.entries.length > MAX_SHOWN ? (
                  <p className="px-2 pt-1 text-xs text-shadow-1 dark:text-moonlight">
                    {section.entries.length - MAX_SHOWN} more — type to filter.
                  </p>
                ) : null}
              </section>
            ))}
          </div>
        )}
      </div>
    </LemonModal>
  );
}
