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
import { startInvestigation } from "../../lib/api";
import {
  getPassageSnippet,
  getProvenance,
  postFork,
  postForkMerge,
  type PassageSnippet,
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
          <BiteRow
            key={bite.bite_id}
            bite={bite}
            sourceDocumentId={gen.source_document_id}
            generationThreadId={gen.generation_id}
            generationRecordNote={`generated with ${gen.model}`}
          />
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
  generationRecordNote,
}: {
  bite: ProvenanceBite;
  sourceDocumentId: string;
  generationThreadId: string;
  generationRecordNote: string;
}) {
  const [open, setOpen] = useState(false);
  const label = CLASS_LABELS[bite.contribution_class] ?? bite.contribution_class;
  const firstPage = bite.source_page_hints.find((h) => h !== null) ?? null;

  function traceJump() {
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
      <button
        type="button"
        data-bite-trace-toggle={bite.bite_id}
        onClick={() => setOpen((o) => !o)}
        className="font-mono text-xxs text-shadow-1 underline decoration-dotted underline-offset-2 hover:text-ink dark:text-moonlight dark:hover:text-bright"
        title="This bite's full provenance"
      >
        {open ? "close trace" : "trace"}
      </button>
      {open && (
        <BiteTrace
          bite={bite}
          sourceDocumentId={sourceDocumentId}
          generationRecordNote={generationRecordNote}
          onTraceJump={traceJump}
        />
      )}
    </li>
  );
}

/** The FULL trace (SPR-03): class + byte-verification + every source span
 *  with its jump + the investigation / the honest null line + the
 *  generation record. The calm contract holds — one click per fact, never
 *  a quote-bomb. The SPR-00 arena owns the final shape; this is the trace
 *  CONTENT, arena-swappable. */
function BiteTrace({
  bite,
  sourceDocumentId,
  generationRecordNote,
  onTraceJump,
}: {
  bite: ProvenanceBite;
  sourceDocumentId: string;
  generationRecordNote: string;
  onTraceJump: () => void;
}) {
  const [snippet, setSnippet] = useState<PassageSnippet | null>(null);
  const [question, setQuestion] = useState("");
  const [probeState, setProbeState] = useState<"idle" | "busy" | "launched">("idle");

  async function pullSnippet() {
    if (!bite.source_refs?.length) return;
    const span = bite.source_refs[0];
    const value = await getPassageSnippet(sourceDocumentId, span);
    setSnippet(value);
    // The probing composer prefills from the gate-served snippet (never
    // from a withheld body — metadata-only there).
    setQuestion((q) => q || (value.text ?? "the cited core passage"));
  }

  async function probe() {
    const q = question.trim();
    if (q.length < 3) return;
    setProbeState("busy");
    try {
      // THE MANDATORY CITATION (the agent-facing rule): a probe's chase
      // ALWAYS carries the resolved core span refs in its context — the
      // reasoning trace may weave; the citation is not optional. The
      // existing spawn fields carry it — never a new schema.
      const citation = bite.source_refs?.length
        ? "Core passages: " +
          bite.source_refs
            .map(
              (s) =>
                `${sourceDocumentId} ${s.node_id} [${s.start_scalar}:${s.end_scalar}]`,
            )
            .join("; ")
        : `No direct source — generated connective tissue (${generationRecordNote})`;
      await startInvestigation({
        question: q,
        context: citation,
        spawn_context: snippet?.text ?? citation,
        // A research_supplemented bite's probe descends from ITS
        // investigation; a plain bite's probe is a lawful cold start.
        ...(bite.investigation_id
          ? { parent_investigation_id: bite.investigation_id }
          : {}),
      });
      setProbeState("launched");
    } finally {
      setProbeState((s) => (s === "busy" ? "idle" : s));
    }
  }

  return (
    <div
      className="mt-1 rounded-hog border border-rule bg-ice-0 px-2 py-1.5 font-mono text-xxs text-shadow-1 dark:border-charcoal-1 dark:bg-charcoal-2 dark:text-moonlight"
      data-bite-trace={bite.bite_id}
    >
      <p>
        {CLASS_LABELS[bite.contribution_class] ?? bite.contribution_class}
        {bite.contribution_class === "author_verbatim"
          ? bite.byte_verified
            ? " — byte-verified against the source span"
            : " — NOT byte-verified (an honest anomaly)"
          : ""}
      </p>
      {bite.source_refs ? (
        <ul className="mt-1 space-y-1">
          {bite.source_refs.map((_span, i) => (
            <li key={i}>
              core passage, page{" "}
              {(bite.source_page_hints[i] ?? 0) + 1}{" "}
              <button
                type="button"
                data-trace-jump={bite.bite_id}
                onClick={onTraceJump}
                className="text-sun-deep underline decoration-dotted underline-offset-2 hover:underline dark:text-sun"
                title="Open the author's actual passage in the source"
              >
                open the source passage
              </button>
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-1 italic">
          generated connective tissue — no direct source · {generationRecordNote}
        </p>
      )}
      {bite.investigation_id && (
        <p className="mt-1">
          research-added ·{" "}
          <Link
            to={`/inv/${encodeURIComponent(bite.investigation_id)}`}
            className="text-sun-deep underline-offset-2 hover:underline dark:text-sun"
          >
            the investigation
          </Link>
        </p>
      )}

      {/* Pull-a-snippet + probe deeper. */}
      {bite.source_refs ? (
        <div className="mt-1.5 border-t border-hairline pt-1.5">
          <button
            type="button"
            data-pull-snippet={bite.bite_id}
            onClick={() => void pullSnippet()}
            className="text-sun-deep underline decoration-dotted underline-offset-2 hover:underline dark:text-sun"
          >
            pull the core passage
          </button>
          {snippet && (
            <blockquote
              data-probe-snippet
              className="mt-1 border-l-edge border-sun pl-2 font-serif not-italic text-ink-soft dark:text-starlight"
            >
              {snippet.text ??
                `a withheld passage — page ${(snippet.page_index_hint ?? 0) + 1} (metadata only)`}
            </blockquote>
          )}
          <div className="mt-1">
            {probeState === "launched" ? (
              <p role="status" className="text-success">
                probing — the chase is running with the core spans cited
              </p>
            ) : (
              <>
                <input
                  type="text"
                  value={question}
                  onChange={(e) => setQuestion(e.target.value)}
                  placeholder="probe deeper — the core spans ride the citation"
                  aria-label="Probe deeper from this bite"
                  className="w-full rounded-hog border border-rule bg-ice-0 px-1.5 py-0.5 dark:border-charcoal-1 dark:bg-charcoal-2"
                />
                <button
                  type="button"
                  data-probe-launch={bite.bite_id}
                  onClick={() => void probe()}
                  disabled={probeState === "busy" || question.trim().length < 3}
                  className="mt-1 text-sun-deep underline decoration-dotted underline-offset-2 hover:underline disabled:opacity-50 dark:text-sun"
                >
                  {probeState === "busy" ? "launching…" : "probe deeper"}
                </button>
              </>
            )}
          </div>
        </div>
      ) : null}
    </div>
  );
}
