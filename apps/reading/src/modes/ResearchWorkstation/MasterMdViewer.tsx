import { useEffect, useState } from "react";

import LemonButton from "../../components/lemon/LemonButton";
import { toast } from "../../components/lemon/LemonToast";
import { getChunk } from "../../lib/api";
import type { ChunkResponse } from "../../lib/api";
import type { ParsedClaim, ParsedSynthesis, Recommendation } from "../../lib/synthesisParser";
import { openNotebook, openPdfPanel } from "../../workspace/actions";
import ChunkModal from "./ChunkModal";

/**
 * Renders a completed investigation's synthesis as a trustworthy
 * researcher's note: serif body, flowing prose, and — SPR-04 M1 — claim
 * support shown as NAMED SOURCES resolved through the provenance chain
 * (claim → chunk → document → title + locator), never the engine's
 * retrieval unit. A reader sees "from <em>Title</em>, p.12", not a
 * bracketed chunk count nor a raw chunk id.
 *
 * Source-opening honours the §9.0 retrieval gate: a named source opens
 * only when its source is servable (the `getChunk` endpoint carries the
 * verdict + withholds the body for a restricted source); a restricted /
 * taken-down source shows an honest "not available to open" state and is
 * never served.
 *
 * Falsification + execution risks are appendix material — collapsed by
 * default per the voice and style discipline (audit metadata, not
 * reading material).
 */
export default function MasterMdViewer({
  synthesis,
}: {
  synthesis: ParsedSynthesis;
}) {
  const [openChunkId, setOpenChunkId] = useState<string | null>(null);

  return (
    <div className="bg-ice-0 dark:bg-charcoal-2">
      <article className="max-w-3xl mx-auto px-6 py-10 font-serif text-ink dark:text-bright">
        {/* Header band */}
        <header className="mb-8 pb-6 border-b border-rule dark:border-charcoal-1">
          {synthesis.question && (
            <h1 className="text-2xl leading-tight mb-3">
              {synthesis.question}
            </h1>
          )}
          <div className="flex items-center gap-3 text-xs font-mono text-shadow-1 dark:text-moonlight">
            <RecommendationBadge rec={synthesis.recommendation} />
            <span className="text-ink-mute dark:text-moonlight">·</span>
            <span>${synthesis.totalCostUsd.toFixed(4)} spent</span>
            {synthesis.domainsPatched.length > 0 && (
              <>
                <span className="text-ink-mute dark:text-moonlight">·</span>
                <span>
                  patched {synthesis.domainsPatched.length} domain skill
                  {synthesis.domainsPatched.length === 1 ? "" : "s"}
                </span>
              </>
            )}
            <span className="ml-auto">
              <LemonButton
                size="sm"
                variant="secondary"
                onClick={() => {
                  // Opens the notebook editor as a floating panel, focused
                  // on a notebook keyed to this answer (re-opening from the
                  // same answer focuses the existing notebook, not a
                  // duplicate). The block model + live-synthesis resolution
                  // are architecture_notes §13; the copy here is plain
                  // (no "synthesis-section block" / "slash menu" jargon —
                  // SPR-04 M1 kills the jargon toasts).
                  const nbId =
                    "synthesis-" +
                    (synthesis.question ?? "untitled")
                      .toLowerCase()
                      .replace(/[^a-z0-9]+/g, "-")
                      .slice(0, 32);
                  openNotebook({
                    kind: "NotebookEditor",
                    mode: "floating",
                    notebookId: nbId,
                    title: "Save to notebook",
                  });
                  toast.ok("Notebook open — you can drop this answer in.");
                }}
              >
                Save to notebook
              </LemonButton>
            </span>
          </div>
        </header>

        {/* Thesis summary — flowing prose */}
        {synthesis.thesisSummary && (
          <section className="mb-8">
            <h2 className="text-sm font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight mb-3">
              Thesis
            </h2>
            <p className="text-base leading-relaxed">
              {synthesis.thesisSummary}
            </p>
          </section>
        )}

        {/* Thesis components — each with hoverable citations */}
        {synthesis.components.length > 0 && (
          <section className="mb-8">
            <h2 className="text-sm font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight mb-3">
              Components ({synthesis.components.length})
            </h2>
            <div className="space-y-6">
              {synthesis.components.map((c) => (
                <ClaimBlock
                  key={c.index}
                  claim={c}
                  onChunkClick={setOpenChunkId}
                />
              ))}
            </div>
          </section>
        )}

        {/* Appendix — falsifications + risks + constraints, collapsed */}
        <Appendix synthesis={synthesis} />
      </article>

      <ChunkModal
        chunkId={openChunkId}
        onClose={() => setOpenChunkId(null)}
      />
    </div>
  );
}

// ── Sub-components ───────────────────────────────────────────────────

function ClaimBlock({
  claim,
  onChunkClick,
}: {
  claim: ParsedClaim;
  onChunkClick: (chunkId: string) => void;
}) {
  return (
    <div className="text-base leading-relaxed">
      <span className="font-mono text-xs text-ink-mute dark:text-moonlight mr-2">
        {claim.index}.
      </span>
      <span data-claim-id={String(claim.index)}>{claim.claim}</span>
      {claim.rationale && (
        <p className="text-sm text-ink-soft dark:text-starlight mt-2 leading-relaxed pl-6 border-l-2 border-rule dark:border-charcoal-1 ml-1">
          {claim.rationale}
        </p>
      )}
      <div className="mt-2 flex items-center gap-2 flex-wrap pl-6">
        <ConfidenceChip
          confidence={claim.confidence}
          tier={claim.effectiveSourceTier}
        />
        <NamedSources chunkIds={claim.chunkIds} onPreview={onChunkClick} />
        {claim.supportingPathIndices.length > 0 && (
          <span className="text-[10px] font-mono text-shadow-1 dark:text-moonlight">
            + {claim.supportingPathIndices.length} cross-domain path
            {claim.supportingPathIndices.length === 1 ? "" : "s"}
          </span>
        )}
      </div>
    </div>
  );
}

// ── Named sources (SPR-04 M1) ────────────────────────────────────────
//
// Resolve each cited chunk through the provenance chain (getChunk →
// document title + locator + §9.0 servability verdict), group the
// chunks by document, and render one NAMED source per document. This is
// the chunk-count → named-source translation: the engine's retrieval
// unit (the chunk) is collapsed into the human unit (the source), so a
// claim backed by three chunks of one paper reads as one named source,
// not a bracketed chunk count.

interface ResolvedSource {
  documentId: string;
  /** The source's title; null when the document carries no title. */
  title: string | null;
  /** A human locator (e.g. "p.12") derived from a chunk's section_path,
   *  or null when no chunk in the group encodes one. */
  locator: string | null;
  /** A representative chunk id for the inline preview + ⌘-open. */
  representativeChunkId: string;
  /** §9.0: whether clicking may open this source. False ⇒ honest
   *  "not available to open"; the body is already withheld by the API. */
  servable: boolean;
  /** SPR-10 M1 — "whose work grounds this": the source's IP-holder name
   *  (e.g. "MIT Press"), or null when the document has no resolved owner
   *  (honest "unknown owner", never invented). The §9.0 gate withholds the
   *  owner for a non-servable source, so this is null there too. */
  ipHolderName: string | null;
}

/** Derive a "p.NNN" locator from a section_path, when present. */
function locatorFromSectionPath(sectionPath: string | null): string | null {
  if (!sectionPath) return null;
  const m = sectionPath.match(/p\.?\s*(\d+)/i);
  return m ? `p.${m[1]}` : null;
}

/** Group resolved chunks by document into named sources, picking the
 *  first locator found per document. Order follows first appearance so
 *  the render is stable. */
function groupByDocument(chunks: ChunkResponse[]): ResolvedSource[] {
  const byDoc = new Map<string, ResolvedSource>();
  for (const c of chunks) {
    const existing = byDoc.get(c.document_id);
    const locator = locatorFromSectionPath(c.section_path);
    if (existing) {
      if (!existing.locator && locator) existing.locator = locator;
      continue;
    }
    byDoc.set(c.document_id, {
      documentId: c.document_id,
      title: c.document_title,
      locator,
      representativeChunkId: c.chunk_id,
      servable: c.servable,
      // §9.0: the endpoint already withholds the owner for a non-servable
      // source, so this is null there; we never invent it. (`?? null`
      // tolerates an older endpoint that omits the field entirely.)
      ipHolderName: c.ip_holder_name ?? null,
    });
  }
  return Array.from(byDoc.values());
}

function NamedSources({
  chunkIds,
  onPreview,
}: {
  chunkIds: string[];
  onPreview: (chunkId: string) => void;
}) {
  const [sources, setSources] = useState<ResolvedSource[] | null>(null);

  useEffect(() => {
    if (chunkIds.length === 0) {
      setSources([]);
      return;
    }
    let live = true;
    void (async () => {
      // Resolve each cited chunk through the provenance chain. A failed
      // fetch is dropped (honest: a source that can't be resolved is not
      // a source we'll name — rigor #1, never fabricate a title), so the
      // count of named sources can be fewer than the count of chunks.
      const settled = await Promise.allSettled(chunkIds.map((id) => getChunk(id)));
      if (!live) return;
      const ok = settled
        .filter((r): r is PromiseFulfilledResult<ChunkResponse> => r.status === "fulfilled")
        .map((r) => r.value);
      setSources(groupByDocument(ok));
    })();
    return () => {
      live = false;
    };
  }, [chunkIds]);

  if (chunkIds.length === 0) return null;
  if (sources === null) {
    return (
      <span className="text-[11px] text-shadow-1 dark:text-moonlight italic">
        resolving sources…
      </span>
    );
  }
  if (sources.length === 0) {
    // Resolved, but no source could be named (all fetches failed / no
    // titles). Honest, not a fabricated citation.
    return (
      <span className="text-[11px] text-shadow-1 dark:text-moonlight italic">
        source unavailable
      </span>
    );
  }

  return (
    <>
      {sources.map((s) => (
        <SourceCitation key={s.documentId} source={s} onPreview={onPreview} />
      ))}
    </>
  );
}

function SourceCitation({
  source,
  onPreview,
}: {
  source: ResolvedSource;
  onPreview: (chunkId: string) => void;
}) {
  const label = source.title ?? "an untitled source";
  const locator = source.locator ? `, ${source.locator}` : "";
  // SPR-10 M1 — "whose work grounds this": append the IP holder only when the
  // endpoint resolved one. Null ⇒ unknown owner, shown by simply not claiming
  // one (never an invented "published by …"). A non-servable source already
  // has ipHolderName = null (§9.0 withholds it), so the protected attribution
  // never leaks onto the restricted branch below.
  const owner = source.ipHolderName ? `, published by ${source.ipHolderName}` : "";

  if (!source.servable) {
    // §9.0: a restricted / taken-down source must NOT open. Show the
    // named source (so the reader knows what backs the claim) with an
    // honest "not available to open" state — never the content.
    return (
      <span
        className="text-[11px] text-ink-soft dark:text-starlight bg-ice-2 dark:bg-charcoal-1 px-1.5 py-0.5 rounded inline-flex items-center gap-1"
        title="This source isn’t available to open here (its license restricts it)."
      >
        from {label}
        {locator}
        <span className="text-[10px] text-shadow-1 dark:text-moonlight">
          · not available to open
        </span>
      </span>
    );
  }

  return (
    <button
      onClick={(e) => {
        // ⌘/Ctrl-click opens the source jumped to its page; plain click
        // previews the chunk inline first (the modal path).
        if (e.metaKey || e.ctrlKey) {
          e.preventDefault();
          void (async () => {
            try {
              const chunk = await getChunk(source.representativeChunkId);
              if (!chunk.servable) {
                toast.err(`${label} isn’t available to open.`);
                return;
              }
              const page = source.locator
                ? parseInt(source.locator.replace(/\D/g, ""), 10)
                : undefined;
              openPdfPanel({
                documentId: chunk.document_id,
                page,
                title: `${label}${source.locator ? ` · ${source.locator}` : ""}`,
              });
            } catch (err) {
              toast.err(
                `Could not open ${label}: ${
                  err instanceof Error ? err.message : String(err)
                }`,
              );
            }
          })();
          return;
        }
        onPreview(source.representativeChunkId);
      }}
      className="text-[11px] text-ink-soft dark:text-starlight bg-ice-3 dark:bg-charcoal-1 hover:bg-ice-4 px-1.5 py-0.5 rounded transition-colors"
      title="Click to preview · ⌘-click to open the source"
    >
      from {label}
      {locator}
      {owner}
    </button>
  );
}

function ConfidenceChip({
  confidence,
  tier,
}: {
  confidence: ParsedClaim["confidence"];
  tier: number | null;
}) {
  const colorClass =
    confidence === "high"
      ? "bg-emerald-100 text-emerald-800"
      : confidence === "moderate"
        ? "bg-sun/20 text-amber-800"
        : confidence === "low"
          ? "bg-orange-100 text-orange-800"
          : "bg-ice-3 dark:bg-charcoal-1 text-ink-soft dark:text-starlight";
  return (
    <span
      className={`text-[10px] font-mono uppercase tracking-wide px-1.5 py-0.5 rounded ${colorClass}`}
    >
      {confidence}
      {tier !== null && ` · tier ${tier}`}
    </span>
  );
}

function RecommendationBadge({ rec }: { rec: Recommendation }) {
  const color =
    rec === "proceed"
      ? "bg-emerald-100 text-emerald-800"
      : rec === "pass"
        ? "bg-red-100 text-red-800"
        : rec === "conditional"
          ? "bg-sun/20 text-amber-800"
          : "bg-ice-3 dark:bg-charcoal-1 text-ink-soft dark:text-starlight";
  return (
    <span
      className={`text-[10px] font-mono uppercase tracking-wider px-2 py-0.5 rounded ${color}`}
    >
      {rec.replace(/_/g, " ")}
    </span>
  );
}

function Appendix({ synthesis }: { synthesis: ParsedSynthesis }) {
  const hasContent =
    synthesis.falsificationConditions.length > 0 ||
    synthesis.executionRisks.length > 0 ||
    synthesis.hardConstraintsSatisfied !== null;
  if (!hasContent) return null;
  return (
    <details className="border-t border-rule dark:border-charcoal-1 pt-6 mt-8">
      <summary className="text-sm font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight cursor-pointer hover:text-ink dark:text-bright transition-colors">
        Appendix — falsification, risks, constraints
      </summary>
      <div className="mt-4 space-y-6 text-sm">
        {synthesis.falsificationConditions.length > 0 && (
          <section>
            <h3 className="text-xs font-mono uppercase text-ink-soft dark:text-starlight mb-2">
              Falsification conditions
            </h3>
            <ol className="list-decimal list-inside space-y-2 text-ink dark:text-bright">
              {synthesis.falsificationConditions.map((f, i) => (
                <li key={i}>
                  <span>{f.condition}</span>
                  {f.specificObservable && (
                    <div className="text-xs text-shadow-1 dark:text-moonlight mt-0.5 pl-6 italic">
                      Observable: {f.specificObservable}
                    </div>
                  )}
                </li>
              ))}
            </ol>
          </section>
        )}
        {synthesis.executionRisks.length > 0 && (
          <section>
            <h3 className="text-xs font-mono uppercase text-ink-soft dark:text-starlight mb-2">
              Execution risks
            </h3>
            <ul className="list-disc list-inside space-y-2 text-ink dark:text-bright">
              {synthesis.executionRisks.map((r, i) => (
                <li key={i}>
                  <span>{r.risk}</span>
                  {r.mitigation && (
                    <div className="text-xs text-shadow-1 dark:text-moonlight mt-0.5 pl-6 italic">
                      Mitigation: {r.mitigation}
                    </div>
                  )}
                </li>
              ))}
            </ul>
          </section>
        )}
        {synthesis.hardConstraintsSatisfied !== null && (
          <section>
            <h3 className="text-xs font-mono uppercase text-ink-soft dark:text-starlight mb-2">
              Constraint compliance
            </h3>
            <p className="text-ink dark:text-bright">
              Hard constraints:{" "}
              {synthesis.hardConstraintsSatisfied ? (
                <span className="text-emerald-700">satisfied</span>
              ) : (
                <span className="text-emperor">violated</span>
              )}
            </p>
          </section>
        )}
      </div>
    </details>
  );
}

