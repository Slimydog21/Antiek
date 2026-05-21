// SPR-06 / M2+M5 — Library grid (the main library landing page).
//
// Replaces the existing DocumentsIndex view as the user's library
// entry. Reuses the substrate `/documents` query (per rigor #4,
// don't duplicate the data layer) and augments per-card with the
// metadata blob, paywall flag, last-read timestamp, and folder/tag
// filtering.
//
// Behavior events (M5):
//   - `document_opened` fires on card click. Required state fields:
//     `document_id` (taxonomy schema).
//   - `document_imported` is mentioned in the sprint spec but is NOT
//     yet in the closed taxonomy (substrate/behavior/taxonomy.py).
//     We do NOT emit it here — emitting an unknown event type would
//     throw at the boundary. The taxonomy migration to add it is
//     a substrate-side change out of scope for SPR-06; we surface
//     the discrepancy in the handoff and leave a TODO at the would-
//     be call site.

import { useCallback, useEffect, useMemo, useState } from "react";

import { apiFetch } from "../../lib/api";
import { emitBehaviorEvent, BehaviorEventType } from "../../lib/behaviorEvents";
import { useAuth } from "../../lib/auth";
import { LemonButton } from "../../components/lemon";
import { listDocumentsInFolder } from "../../../api/library/folders";
import {
  listDocumentsWithTag,
  listTags,
  listTagsForDocument,
} from "../../../api/library/tags";
import type { IngestJob } from "../../../api/library/types";

import { EmptyState } from "./EmptyState";
import { LibraryCard, type LibraryDocument } from "./LibraryCard";
import { Sidebar, type LibraryFilter } from "./Sidebar";
import { UrlPasteBar } from "./UrlPasteBar";
import {
  effectiveAlwaysStartAtLibrary,
  recordLastOpenedDocument,
  writeUserSettings,
} from "../../settings/userSettings";

type SortKey = "last_read_desc" | "imported_desc" | "title_asc";

interface DocumentListResponse {
  documents: Array<{
    document_id: string;
    title: string | null;
    source_uri: string | null;
    document_type: string | null;
    source_tier: number;
    investigation_id: string | null;
    content_class: string | null;
    ip_holder_id: string | null;
  }>;
}

const PAGE_SIZE = 50;

/** localStorage key for per-doc last-opened timestamps. The substrate
 * doesn't expose this today; we keep it client-side per-device. */
const LAST_OPENED_MAP_KEY = "antiek.library.lastOpenedMap.v1";

function readLastOpenedMap(): Record<string, string> {
  if (typeof window === "undefined" || !window.localStorage) return {};
  const raw = window.localStorage.getItem(LAST_OPENED_MAP_KEY);
  if (!raw) return {};
  try {
    return JSON.parse(raw) as Record<string, string>;
  } catch {
    return {};
  }
}

function writeLastOpenedMap(map: Record<string, string>): void {
  if (typeof window === "undefined" || !window.localStorage) return;
  window.localStorage.setItem(LAST_OPENED_MAP_KEY, JSON.stringify(map));
}

export default function LibraryGrid() {
  const { state: authState } = useAuth();
  const userId =
    authState.status === "authenticated"
      ? authState.identity.user_id
      : "__operator__";

  const [docs, setDocs] = useState<LibraryDocument[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<LibraryFilter>({ kind: "all" });
  const [sort, setSort] = useState<SortKey>("last_read_desc");
  const [page, setPage] = useState<number>(0);
  const [prefillUrl, setPrefillUrl] = useState<string | undefined>(undefined);
  const [tagsByDoc, setTagsByDoc] = useState<Record<string, string[]>>({});
  const [filteredDocIds, setFilteredDocIds] = useState<Set<string> | null>(null);
  const [lastOpenedMap, setLastOpenedMap] = useState<Record<string, string>>(() =>
    readLastOpenedMap(),
  );
  const [alwaysStartHere, setAlwaysStartHere] = useState<boolean>(() =>
    effectiveAlwaysStartAtLibrary(),
  );

  /** Reuse the existing /documents endpoint. Per rigor #4, the data
   * layer is shared with DocumentsIndex — only the layout changes. */
  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      params.set("limit", "500");
      const resp = await apiFetch(`/documents?${params.toString()}`);
      if (!resp.ok) {
        throw new Error(`GET /documents: HTTP ${resp.status}`);
      }
      const data = (await resp.json()) as DocumentListResponse;
      const lastOpened = readLastOpenedMap();
      setLastOpenedMap(lastOpened);
      // The /documents endpoint surfaces a subset of fields. We hydrate
      // metadata from a second per-doc call only when needed (paywall
      // flag, content_type). Today we fold what's in the listing into
      // the LibraryDocument shape; richer metadata loads lazily once
      // a per-doc endpoint exists.
      const out: LibraryDocument[] = (data.documents ?? []).map((r) => ({
        document_id: r.document_id,
        title: r.title,
        source_uri: r.source_uri,
        document_type: r.document_type,
        source_tier: r.source_tier,
        metadata: { content_type: r.document_type },
        last_read_at: lastOpened[r.document_id] ?? null,
        read_progress: null,
      }));
      setDocs(out);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  // Hydrate tag names for hover chips (lazy; first cheap call).
  useEffect(() => {
    if (docs.length === 0) return;
    let cancelled = false;
    (async () => {
      const allTags = await listTags();
      const tagNameById = new Map(allTags.map((t) => [t.tag_id, t.name]));
      const result: Record<string, string[]> = {};
      for (const d of docs) {
        const tagIds = await listTagsForDocument(d.document_id);
        result[d.document_id] = tagIds
          .map((id) => tagNameById.get(id))
          .filter((n): n is string => Boolean(n));
      }
      if (!cancelled) setTagsByDoc(result);
    })();
    return () => {
      cancelled = true;
    };
  }, [docs]);

  // Resolve the filtered set when a folder/tag is selected.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      if (filter.kind === "all" || filter.kind === "recent") {
        if (!cancelled) setFilteredDocIds(null);
        return;
      }
      let ids: string[] = [];
      if (filter.kind === "folder") {
        ids = await listDocumentsInFolder(filter.folder_id);
      } else if (filter.kind === "tag") {
        ids = await listDocumentsWithTag(filter.tag_id);
      }
      if (!cancelled) setFilteredDocIds(new Set(ids));
    })();
    return () => {
      cancelled = true;
    };
  }, [filter]);

  const onCardOpen = useCallback(
    (doc: LibraryDocument) => {
      // M5 — emit document_opened. Per the taxonomy schema, state
      // requires document_id; action requires reading_mode. Reading
      // mode defaults to "wrestle" since that's the surface we're
      // navigating to.
      try {
        emitBehaviorEvent({
          eventType: BehaviorEventType.DOCUMENT_OPENED,
          state: { document_id: doc.document_id, entry_route: "library" },
          action: { reading_mode: "wrestle" },
          userId,
          documentId: doc.document_id,
        });
      } catch {
        // Per the milestone acceptance criterion "If emit fails, UI
        // flow is unaffected." Swallow and continue.
      }
      // Record last-opened per device.
      recordLastOpenedDocument(doc.document_id);
      const newMap = { ...lastOpenedMap, [doc.document_id]: new Date().toISOString() };
      writeLastOpenedMap(newMap);
      setLastOpenedMap(newMap);
    },
    [lastOpenedMap, userId],
  );

  const onImportTerminal = useCallback(
    (job: IngestJob) => {
      if (job.status === "succeeded") {
        // Taxonomy v2 (2026-05-22): document_imported is now in the
        // closed taxonomy. emitBehaviorEvent is synchronous; wrap in
        // try/catch so emit failures are non-fatal per SPR-01 rigor.
        // Metadata (paywalled, sidecar_applied, bytes_ingested) lives
        // in the job's free-form `metadata` blob; we forward what's there.
        const md = job.metadata ?? {};
        try {
          emitBehaviorEvent({
            eventType: BehaviorEventType.DOCUMENT_IMPORTED,
            state: {
              document_id: job.document_id ?? "unknown",
              source_url: job.url ?? null,
              content_type: job.content_type ?? null,
              import_path: typeof md.import_path === "string" ? md.import_path : null,
            },
            action: {
              outcome: "succeeded",
              paywalled: typeof md.paywalled === "boolean" ? md.paywalled : null,
              sidecar_applied:
                typeof md.sidecar_applied === "boolean" ? md.sidecar_applied : null,
              bytes_ingested:
                typeof md.bytes_ingested === "number" ? md.bytes_ingested : null,
            },
          });
        } catch {
          // Swallow — per SPR-01 emit-failure-non-fatal rigor.
        }
        void reload();
      }
    },
    [reload],
  );

  // Apply sort + filter to the visible list.
  const visible = useMemo(() => {
    let pool = docs;
    if (filter.kind === "recent") {
      const cutoff = Date.now() - 30 * 24 * 60 * 60 * 1000;
      pool = pool.filter((d) => {
        if (!d.last_read_at) return false;
        const t = Date.parse(d.last_read_at);
        return !Number.isNaN(t) && t >= cutoff;
      });
    } else if (filteredDocIds !== null) {
      pool = pool.filter((d) => filteredDocIds.has(d.document_id));
    }

    const sorted = pool.slice();
    if (sort === "last_read_desc") {
      sorted.sort((a, b) => {
        const at = a.last_read_at ? Date.parse(a.last_read_at) : 0;
        const bt = b.last_read_at ? Date.parse(b.last_read_at) : 0;
        return bt - at;
      });
    } else if (sort === "title_asc") {
      sorted.sort((a, b) => (a.title ?? a.document_id).localeCompare(b.title ?? b.document_id));
    } else {
      // imported_desc: we don't have an imported_at on the listing
      // shape; document_id sorts in approximately-insert order for
      // the synthetic hash-based ids the SPR-03 pipeline mints.
      sorted.sort((a, b) => b.document_id.localeCompare(a.document_id));
    }
    return sorted;
  }, [docs, filter.kind, filteredDocIds, sort]);

  const paged = useMemo(() => {
    const start = page * PAGE_SIZE;
    return visible.slice(start, start + PAGE_SIZE);
  }, [visible, page]);

  const pageCount = Math.max(1, Math.ceil(visible.length / PAGE_SIZE));

  const isFullyEmpty = !loading && docs.length === 0 && !error;

  return (
    <div className="flex h-full" data-testid="library-grid-root">
      <Sidebar
        active={filter}
        onFilterChange={(f) => {
          setFilter(f);
          setPage(0);
        }}
        documentCount={docs.length}
      />

      <main className="flex-1 overflow-y-auto">
        <div className="max-w-6xl mx-auto px-6 py-6 space-y-6">
          <header className="flex items-start justify-between gap-4 flex-wrap">
            <div className="space-y-2">
              <h1 className="font-serif text-[24px] text-ink dark:text-bright">Library</h1>
              <p className="text-[13px] text-shadow-2 dark:text-starlight">
                Kindle for the internet — paste any URL or PDF and we'll keep
                it here for you.
              </p>
            </div>
            <label className="flex items-center gap-2 text-[12px] font-mono text-shadow-1 dark:text-moonlight cursor-pointer select-none">
              <input
                type="checkbox"
                checked={alwaysStartHere}
                onChange={(e) => {
                  const next = e.target.checked;
                  setAlwaysStartHere(next);
                  writeUserSettings({ alwaysStartAtLibrary: next });
                }}
                data-testid="library-always-start-toggle"
              />
              Always start here on login
            </label>
          </header>

          <UrlPasteBar
            userId={userId}
            onImportTerminal={onImportTerminal}
            prefillUrl={prefillUrl}
          />

          {isFullyEmpty && (
            <EmptyState
              onSuggestionClick={(url) => setPrefillUrl(url)}
            />
          )}

          {!isFullyEmpty && (
            <>
              <div className="flex items-center justify-between gap-3 flex-wrap">
                <div className="flex items-center gap-2 font-mono text-[11px] uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                  <span>{visible.length} doc{visible.length === 1 ? "" : "s"}</span>
                  {filter.kind === "folder" && <span>· folder: {filter.name}</span>}
                  {filter.kind === "tag" && <span>· tag: #{filter.name}</span>}
                  {filter.kind === "recent" && <span>· recent (30d)</span>}
                </div>
                <div className="flex items-center gap-2">
                  <label className="font-mono text-[10px] uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                    Sort
                  </label>
                  <select
                    value={sort}
                    onChange={(e) => setSort(e.target.value as SortKey)}
                    className="text-[12px] font-mono border-edge border-sun rounded h-7 px-2 bg-ice-0 dark:bg-charcoal-2 text-ink dark:text-bright"
                    data-testid="library-sort-select"
                  >
                    <option value="last_read_desc">Last read ↓</option>
                    <option value="imported_desc">Imported ↓</option>
                    <option value="title_asc">Title ↑</option>
                  </select>
                </div>
              </div>

              {error && (
                <p className="text-[13px] text-emperor font-mono">
                  {error}
                </p>
              )}

              {loading && (
                <p className="text-[13px] italic text-shadow-1 dark:text-moonlight">
                  Loading…
                </p>
              )}

              {!loading && visible.length === 0 && (
                <p className="text-[13px] italic text-shadow-1 dark:text-moonlight">
                  No documents in this filter.
                </p>
              )}

              <ul
                className="grid grid-cols-[repeat(auto-fill,minmax(220px,1fr))] gap-4"
                data-testid="library-grid"
              >
                {paged.map((doc) => (
                  <li key={doc.document_id}>
                    <LibraryCard
                      doc={doc}
                      tagNames={tagsByDoc[doc.document_id] ?? []}
                      onOpen={onCardOpen}
                    />
                  </li>
                ))}
              </ul>

              {pageCount > 1 && (
                <div className="flex items-center justify-center gap-3 py-4">
                  <LemonButton
                    type="button"
                    variant="tertiary"
                    size="sm"
                    onClick={() => setPage((p) => Math.max(0, p - 1))}
                    disabled={page === 0}
                  >
                    ‹ Prev
                  </LemonButton>
                  <span className="font-mono text-[11px] text-shadow-1 dark:text-moonlight">
                    Page {page + 1} of {pageCount}
                  </span>
                  <LemonButton
                    type="button"
                    variant="tertiary"
                    size="sm"
                    onClick={() => setPage((p) => Math.min(pageCount - 1, p + 1))}
                    disabled={page >= pageCount - 1}
                  >
                    Next ›
                  </LemonButton>
                </div>
              )}
            </>
          )}
        </div>
      </main>
    </div>
  );
}
