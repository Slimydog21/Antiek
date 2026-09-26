/**
 * WriteOutlinePane — the C5 right pane for Write mode: ONE TAB PER OUTLINE
 * BUILDING-BLOCK, each a drag-and-drop target for source documents.
 *
 * Mode contract (ratified): in writing mode this pane REPLACES the C4
 * companion in the right pane (mounted by RightPaneForMode; in the docked
 * preset it is the "WriteOutline" right-dock panel). It is NOT the
 * companion — no agent tabs here; agents stay one keystroke away on the AI
 * sidecar (mod+/), untouched.
 *
 * Each block tab shows the block's content summary, its provenance kind,
 * and its source documents: the node-trace it was born from (when
 * node-backed) plus the sources the operator ASSIGNED by dropping them here
 * (repository search hits, left reader tabs). Assignment lands in
 * blockSources.ts, the honest session-scoped bridge until the write-through
 * endpoint lands (the copy says "session state", never a pretend-write).
 * A drop whose payload is not a source document is refused in words, and
 * nothing is assigned (parseSourceDragPayload).
 */
import { useEffect, useState } from "react";
import { matchPath, useLocation } from "react-router-dom";

import { EmptyState, ErrorState, LoadingState } from "../components/states";
import { getDeliverable } from "../lib/api";
import type { SectionResponse } from "../lib/api";
import {
  blockDisplayText,
  getSectionBlocks,
  type OutlineBlockView,
} from "../modes/Write/writeApi";
import { useBlockSources } from "./blockSources";
import { useWriteOutline } from "./writeOutlineStore";
import { SOURCE_DOCUMENT_MIME } from "./sourceDrag";

export { SOURCE_DOCUMENT_MIME };

/** The drag payload a source document carries (repository hits, reader tabs). */
export interface SourceDocumentDragPayload {
  document_id: string;
  document_title: string | null;
}

/**
 * Read a drop's payload, or null when it is not a source document. The
 * payload crosses a drag boundary any page or extension can write to, so it
 * is parsed, never trusted: malformed JSON, a non-object, and a missing or
 * blank document id are refused. A title that is not a string reads as none.
 */
export function parseSourceDragPayload(raw: string): SourceDocumentDragPayload | null {
  let value: unknown;
  try {
    value = JSON.parse(raw);
  } catch {
    return null;
  }
  if (typeof value !== "object" || value === null || Array.isArray(value)) return null;
  const record = value as Record<string, unknown>;
  const id = typeof record.document_id === "string" ? record.document_id.trim() : "";
  if (!id) return null;
  const title = typeof record.document_title === "string" ? record.document_title.trim() || null : null;
  return { document_id: id, document_title: title };
}

interface SectionBlocks {
  section: SectionResponse;
  blocks: OutlineBlockView[];
}

/** Stable empty record for the selector (a fresh `{}` per call loops
 *  useSyncExternalStore). */
const NO_ASSIGNMENTS: Record<string, never[]> = {};

export default function WriteOutlinePane() {
  const location = useLocation();
  const deliverableId = matchPath("/write/:deliverableId", location.pathname)?.params
    .deliverableId as string | undefined;

  const [sections, setSections] = useState<SectionBlocks[]>([]);
  // Loading, loaded and failed are three states: an empty piece is not a
  // piece still loading, and a failure offers a retry.
  const [status, setStatus] = useState<"loading" | "ready" | "failed">("loading");
  const [attempt, setAttempt] = useState(0);
  // The last drop that was not a source document, said once in words.
  const [refusedDrop, setRefusedDrop] = useState(false);
  const activeBlockId = useWriteOutline((s) => s.activeBlockId);
  const setActiveBlock = useWriteOutline((s) => s.setActiveBlock);
  const setBlocks = useWriteOutline((s) => s.setBlocks);
  const assignments = useBlockSources((s) =>
    deliverableId ? (s.records[deliverableId] ?? NO_ASSIGNMENTS) : NO_ASSIGNMENTS,
  );
  const assign = useBlockSources((s) => s.assign);
  const unassign = useBlockSources((s) => s.unassign);
  const ensureDeliverable = useBlockSources((s) => s.ensureDeliverable);

  useEffect(() => {
    if (!deliverableId) {
      setSections([]);
      setBlocks([]);
      return;
    }
    let cancelled = false;
    setStatus("loading");
    void (async () => {
      try {
        const detail = await getDeliverable(deliverableId);
        if (cancelled || !detail) {
          if (!cancelled) setStatus("failed");
          return;
        }
        const perSection = await Promise.all(
          [...detail.sections]
            .sort((a, b) => a.section_index - b.section_index)
            .map(async (section) => ({
              section,
              blocks: (await getSectionBlocks(section.section_id)).sort(
                (a, b) => a.block_index - b.block_index,
              ),
            })),
        );
        if (cancelled) return;
        setSections(perSection);
        setStatus("ready");
        setBlocks(
          perSection.flatMap((s) => s.blocks.map((b) => b.outline_block_id)),
        );
        void ensureDeliverable(deliverableId);
      } catch {
        if (!cancelled) setStatus("failed");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [deliverableId, setBlocks, ensureDeliverable, attempt]);

  const flat = sections.flatMap((s) =>
    s.blocks.map((b) => ({ section: s.section, block: b })),
  );
  const active = flat.find((f) => f.block.outline_block_id === activeBlockId) ?? null;

  if (!deliverableId) {
    return (
      <section aria-label="Outline" data-write-outline className="flex h-full flex-col p-3">
        <EmptyState
          variant="inline"
          art={false}
          title="No piece open"
          body="Open a piece to see its building blocks here: one tab each, ready to take source documents by drag-and-drop."
        />
      </section>
    );
  }

  return (
    <section
      aria-label="Outline"
      data-write-outline
      className="flex h-full min-h-0 min-w-0 flex-col"
    >
      {status === "loading" ? (
        <div className="shrink-0 border-b border-hairline">
          <LoadingState variant="inline" shape="strip" label="Opening the outline" />
        </div>
      ) : null}
      {status === "ready" && flat.length > 0 ? (
      <div
        role="tablist"
        aria-label="Outline blocks"
        className="flex items-center gap-1 shrink-0 overflow-x-auto border-b border-hairline px-1.5 py-1"
      >
        {flat.map(({ section, block }) => {
          const assigned = assignments[block.outline_block_id] ?? [];
          const isActive = block.outline_block_id === activeBlockId;
          return (
            <button
              key={block.outline_block_id}
              type="button"
              role="tab"
              aria-selected={isActive}
              data-block-tab={block.outline_block_id}
              onClick={() => setActiveBlock(block.outline_block_id)}
              onDragOver={(e) => {
                if (e.dataTransfer.types.includes(SOURCE_DOCUMENT_MIME)) e.preventDefault();
              }}
              onDrop={(e) => {
                const raw = e.dataTransfer.getData(SOURCE_DOCUMENT_MIME);
                if (!raw) return;
                e.preventDefault();
                const payload = parseSourceDragPayload(raw);
                if (!payload) {
                  setRefusedDrop(true);
                  return;
                }
                setRefusedDrop(false);
                assign(deliverableId, block.outline_block_id, payload);
                setActiveBlock(block.outline_block_id);
              }}
              className={`flex max-w-[150px] items-center gap-1 rounded px-1.5 py-0.5 text-xs ${
                isActive
                  ? "bg-ice-2 text-ink dark:bg-charcoal-1 dark:text-bright"
                  : "text-ink-soft hover:bg-ice-2 dark:text-moonlight dark:hover:bg-charcoal-1"
              }`}
              title={`${section.title ?? "section"} · drop a source document to assign it`}
            >
              <span className="truncate">{blockDisplayText(block)}</span>
              {assigned.length > 0 ? (
                <span className="shrink-0 font-mono text-sun-deep" aria-label={`${assigned.length} assigned sources`}>
                  ·{assigned.length}
                </span>
              ) : null}
            </button>
          );
        })}
      </div>
      ) : null}
      {refusedDrop ? <DropRefusedNote onDismiss={() => setRefusedDrop(false)} /> : null}

      <div className="min-h-0 flex-1 overflow-auto">
        {status === "loading" ? null : status === "failed" ? (
          <div className="p-3">
            <ErrorState
              variant="inline"
              title="Couldn't open this piece's outline"
              body="The piece itself is untouched; its blocks just didn't load."
              onRetry={() => setAttempt((n) => n + 1)}
            />
          </div>
        ) : active ? (
          <BlockCard
            section={active.section}
            block={active.block}
            assigned={assignments[active.block.outline_block_id] ?? []}
            onUnassign={(documentId) =>
              unassign(deliverableId, active.block.outline_block_id, documentId)
            }
          />
        ) : flat.length === 0 ? (
          <div className="p-3">
            <EmptyState
              variant="inline"
              art={false}
              title="No blocks yet"
              body="Add them in the outline on the left; each block gets a tab here."
            />
          </div>
        ) : (
          <p className="p-3 text-sm text-ink-soft dark:text-moonlight">Pick a block tab.</p>
        )}
      </div>
    </section>
  );
}

/** The honest refusal a drop that is not a source document gets. */
export function DropRefusedNote({ onDismiss }: { onDismiss: () => void }) {
  return (
    <div
      role="status"
      aria-label="Drop refused"
      data-drop-refused
      className="flex shrink-0 items-start gap-2 border-b border-hairline px-3 py-2 text-xs text-ink-soft dark:text-moonlight"
    >
      <p className="flex-1">
        That drop wasn&apos;t a source document, so nothing was assigned. Drag a repository hit
        or a document tab from the left onto a block&apos;s tab.
      </p>
      <button
        type="button"
        onClick={onDismiss}
        aria-label="Dismiss"
        className="shrink-0 px-0.5 text-shadow-1 hover:text-ink dark:text-moonlight dark:hover:text-bright focus-visible:outline focus-visible:outline-2 focus-visible:outline-sun"
      >
        ×
      </button>
    </div>
  );
}

function provenanceLabel(b: OutlineBlockView): string {
  if (b.is_user_originated || b.provenance_kind !== "graph_node") return "yours";
  return b.block_kind === "open_question" ? "question" : b.block_kind;
}

export function BlockCard({
  section,
  block,
  assigned,
  onUnassign,
}: {
  section: SectionResponse;
  block: OutlineBlockView;
  assigned: { document_id: string; document_title: string | null }[];
  onUnassign: (documentId: string) => void;
}) {
  return (
    <div className="flex flex-col gap-2 p-3" data-block-card={block.outline_block_id}>
      <div className="flex items-center gap-2">
        <span className="text-xxs uppercase tracking-wider text-shadow-1 dark:text-moonlight">
          {provenanceLabel(block)}
        </span>
        <span className="text-xxs text-shadow-1 dark:text-moonlight">
          {section.title ?? "untitled section"}
        </span>
      </div>
      <p className="text-sm font-serif leading-relaxed text-ink dark:text-bright">
        {blockDisplayText(block)}
      </p>
      <div>
        <p className="text-xxs uppercase tracking-wider text-shadow-1 dark:text-moonlight">
          Source documents
        </p>
        {assigned.length === 0 ? (
          <p className="mt-1 text-xs text-ink-soft dark:text-moonlight" data-no-sources>
            None assigned yet. Drag a repository hit or a document tab from the left
            onto this block&apos;s tab. Assignments are session state for now: they
            aren&apos;t saved with the piece yet.
          </p>
        ) : (
          <ul className="mt-1 flex flex-col gap-0.5" data-assigned-sources>
            {assigned.map((a) => (
              <li key={a.document_id} className="flex items-center gap-1 text-xs">
                <span className="truncate text-ink dark:text-bright">
                  {a.document_title ?? a.document_id}
                </span>
                <button
                  type="button"
                  onClick={() => onUnassign(a.document_id)}
                  aria-label={`Remove ${a.document_title ?? a.document_id} from this block`}
                  className="shrink-0 px-0.5 text-shadow-1 hover:text-ink dark:hover:text-bright"
                >
                  ×
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
