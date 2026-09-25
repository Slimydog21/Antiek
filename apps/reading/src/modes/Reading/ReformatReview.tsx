/**
 * ReformatReview — the provenance review surface for a DERIVED document
 * (reformat-provenance SPR-02). Renders ONLY when the open document is
 * derived (a plain document shows NOTHING — "the original shows no
 * marker").
 *
 *   - The honesty header: a generated reformat, from its source (human
 *     title, never a raw id), with the model + the date, PROVISIONAL —
 *     not yet forked. "Mostly generated" says so when the ceiling flipped.
 *   - Per-bite class markers (the calm contract): author's words
 *     (byte-verified ✓) / compressed / expanded / research-added. A sourced
 *     bite's trace JUMP opens the CORE document at the passage (one click —
 *     the unit-1 anchor chain; the full probe is SPR-03). A null-source
 *     bite shows the honest "generated connective tissue" line + the
 *     generation record note.
 *   - "Officially fork" + "Merge later", wired to unit 5's SHAPES — on a
 *     stack without the fork API they degrade HONESTLY (the named pending
 *     state, never a fake success).
 */
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { ApiError } from "../../lib/api";
import {
  getProvenance,
  postFork,
  postForkMerge,
  type ProvenanceBite,
  type ProvenanceResponse,
} from "../../api/reformat";
import { openWindow, readerWindowId } from "../../components/windows/openWindow";

const CLASS_LABELS: Record<string, string> = {
  author_verbatim: "author's words",
  llm_compressed: "compressed",
  llm_expanded: "expanded",
  research_supplemented: "research-added",
};

export default function ReformatReview({ documentId }: { documentId: string }) {
  const [provenance, setProvenance] = useState<ProvenanceResponse | null>(null);
  const [unavailable, setUnavailable] = useState(false);
  const [actionState, setActionState] = useState<
    Record<string, "idle" | "busy" | "pending" | "done">
  >({});

  useEffect(() => {
    let cancelled = false;
    setProvenance(null);
    setUnavailable(false);
    void getProvenance(documentId)
      .then((p) => {
        if (!cancelled) {
          setProvenance(p);
          setUnavailable(p === null);
        }
      })
      .catch(() => {
        if (!cancelled) setUnavailable(true);
      });
    return () => {
      cancelled = true;
    };
  }, [documentId]);

  if (unavailable || !provenance) return null; // a plain document shows nothing

  const gen = provenance.generation;

  async function runAction(kind: "fork" | "merge") {
    setActionState((s) => ({ ...s, [kind]: "busy" }));
    try {
      if (kind === "fork") {
        await postFork(gen.source_document_id, {
          derived_document_id: provenance!.document_id,
          generation_id: gen.generation_id,
        });
      } else {
        await postForkMerge(gen.generation_id, {
          from_derived_document_id: provenance!.document_id,
          generation_id: gen.generation_id,
        });
      }
      setActionState((s) => ({ ...s, [kind]: "done" }));
    } catch (e) {
      // HONEST DEGRADATION: a 404 means the unit-5 API isn't on this stack —
      // the named pending state, never a fake success.
      setActionState((s) => ({
        ...s,
        [kind]: e instanceof ApiError && e.status === 404 ? "pending" : "pending",
      }));
    }
  }

  return (
    <section
      className="border-b border-rule px-4 py-3 dark:border-charcoal-1"
      aria-label="Reformat review"
      data-reformat-review
    >
      {/* The honesty header. */}
      <p className="mb-1 font-serif text-xs italic text-ink-soft dark:text-starlight" data-reformat-header>
        A generated reformat{gen.source_title ? ` of ${gen.source_title}` : " of its source"} ·
        {" "}{gen.model} · {gen.created_at.slice(0, 10)} · provisional — not yet forked
      </p>
      {gen.mostly_generated && (
        <p className="mb-1 font-mono text-xxs text-sun-deep dark:text-sun" data-reformat-mostly>
          mostly generated — the model wrote most of this
        </p>
      )}

      {/* Per-bite class markers + the trace jump. */}
      <ol className="space-y-1.5" data-reformat-bites>
        {provenance.bites.map((bite) => (
          <BiteRow key={bite.bite_id} bite={bite} sourceDocumentId={gen.source_document_id} generationThreadId={gen.generation_id} />
        ))}
      </ol>

      {/* Merge later / officially fork — unit 5's shapes, honestly degrading. */}
      <div className="mt-2 flex items-center gap-3 border-t border-hairline pt-2">
        <button
          type="button"
          data-reformat-fork
          onClick={() => void runAction("fork")}
          disabled={actionState.fork === "busy" || actionState.fork === "done"}
          className="font-mono text-xs text-sun-deep underline-offset-2 hover:underline disabled:opacity-50 dark:text-sun"
        >
          {actionState.fork === "done" ? "forked" : "Officially fork"}
        </button>
        <button
          type="button"
          data-reformat-merge
          onClick={() => void runAction("merge")}
          disabled={actionState.merge === "busy" || actionState.merge === "done"}
          className="font-mono text-xs text-shadow-1 underline-offset-2 hover:underline dark:text-moonlight"
        >
          {actionState.merge === "done" ? "queued to merge" : "Merge later"}
        </button>
        {(actionState.fork === "pending" || actionState.merge === "pending") && (
          <span className="font-mono text-xxs text-shadow-1 dark:text-moonlight" role="status">
            fork/merge API pending — unit 5's implementation isn't on this stack yet
          </span>
        )}
      </div>
    </section>
  );
}

function BiteRow({
  bite,
  sourceDocumentId,
  generationThreadId,
}: {
  bite: ProvenanceBite;
  sourceDocumentId: string;
  generationThreadId: string;
}) {
  const label = CLASS_LABELS[bite.contribution_class] ?? bite.contribution_class;
  const firstPage = bite.source_page_hints.find((h) => h !== null) ?? null;

  function trace() {
    // The anchor chain: derived bite → source span → the core document
    // opened AT the passage (one reader per document — focus, never a dup).
    openWindow(
      "reader",
      {
        documentId: sourceDocumentId,
        origin: { from: "reformat", id: generationThreadId },
        ...(firstPage !== null ? { initialPage: firstPage } : {}),
      },
      { id: readerWindowId(sourceDocumentId), title: "The source passage" },
    );
  }

  return (
    <li
      className="font-serif text-xs leading-relaxed text-ink dark:text-bright"
      data-reformat-bite={bite.contribution_class}
      data-bite-ordinal={bite.ordinal}
    >
      <span className="mr-1 font-mono text-xxs uppercase tracking-wide text-shadow-1 dark:text-moonlight">
        {label}
        {bite.byte_verified ? " ✓" : ""} ·
      </span>
      {bite.source_refs ? (
        <button
          type="button"
          data-trace-jump={bite.bite_id}
          onClick={trace}
          className="font-mono text-xxs text-sun-deep underline decoration-dotted underline-offset-2 hover:underline dark:text-sun"
          title="Open the author's actual passage in the source"
        >
          trace to the source passage
        </button>
      ) : (
        <span className="font-mono text-xxs italic text-shadow-1 dark:text-moonlight">
          generated connective tissue — no direct source
        </span>
      )}
      {bite.investigation_id && (
        <Link
          to={`/inv/${encodeURIComponent(bite.investigation_id)}`}
          className="ml-1 font-mono text-xxs text-sun-deep underline-offset-2 hover:underline dark:text-sun"
        >
          the research →
        </Link>
      )}
    </li>
  );
}
