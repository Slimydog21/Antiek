import { useEffect, useState } from "react";

import LemonButton from "../../components/lemon/LemonButton";
import { toast } from "../../components/lemon/LemonToast";
import { getChunk } from "../../lib/api";
import type { ChunkResponse } from "../../lib/api";
import type { ParsedClaim, ParsedSynthesis, QualityScore, Recommendation } from "../../lib/synthesisParser";
import {
  RESTRICTED_TITLE,
  SERVABLE_CLASS,
  SERVABLE_TITLE,
  makeServabilityAugmentation,
} from "../../reading-physics/augmentations/servability";
import { makeIpHolderAugmentation } from "../../reading-physics/augmentations/ip-holder";
import type { ResolvedDecoration } from "../../reading-physics/facets/decorations";
import { anchorKey } from "../../reading-physics/facets/decorations";
import { collectDecorations } from "../../reading-physics/registry";
import type { ChunkId, ReadingContext } from "../../reading-physics/types";
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
          {/* SPR-11 M3 — a quiet quality cue, read from the persisted inline
              rubric (never recomputed here). Renders nothing when no score was
              persisted; flags a low score so the operator knows the answer may
              want another pass. */}
          <QualityCue score={synthesis.qualityScore} />
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

  // ── Facet apply pass (SPR-03: the first TWO-augmentation composition) ──
  //
  // Two augmentations now declare decorations on each source's range:
  //   - ServabilityAugmentation declares the §9.0 verdict class + tooltip;
  //   - IpHolderAugmentation declares the "whose work grounds this" owner name.
  // The decorations facet MERGES both contributions per source (§5.1), and the
  // surface here reads the combined verdict class AND owner name off ONE
  // resolved decoration. Neither augmentation imports the other — they meet
  // only at the named facet (PR-3). This is the physics' payoff on real shipped
  // code: composition for free, render byte-identical to the inline branch.
  // PR-1: the augmentations never touch the DOM; only this surface paints.
  const decorationByChunk = composedDecorationsByChunk(sources);

  return (
    <>
      {sources.map((s) => (
        <SourceCitation
          key={s.documentId}
          source={s}
          onPreview={onPreview}
          decoration={decorationByChunk.get(
            anchorKey({ kind: "chunk", chunkId: s.representativeChunkId as ChunkId }),
          )}
        />
      ))}
    </>
  );
}

/**
 * Run the decorations facet pass over the resolved sources, COMPOSING the
 * servability + IP-holder augmentations (SPR-03 M5), and return a lookup from a
 * source's anchor key → its combined decoration. This is the surface's
 * collect → combine half of the cycle (§2); SourceCitation owns enact. A plain
 * pure function — NOT a hook: NamedSources returns early above its call site,
 * so it cannot use hooks. The augmentations only declare, this never mutates
 * the DOM, and it runs each render (cheap — O(sources), pure).
 */
function composedDecorationsByChunk(
  sources: ResolvedSource[],
): Map<string, ResolvedDecoration> {
  // Both augmentations read substrate verdicts off each resolved source (PR-6:
  // read, never recompute) and declare a decoration per source on the SAME
  // anchor (the representative chunk). The facet merges them — servability's
  // verdict class with the IP-holder's owner name — so they compose without
  // importing each other (PR-3). The render context is minimal: decorations
  // need no layout-map (that resolves widget pixels, SPR-04), and the
  // augmentations pull no further substrate data, so `substrate` is a
  // shape-only stub never called this sprint.
  const servability = makeServabilityAugmentation(
    sources.map((s) => ({
      representativeChunkId: s.representativeChunkId,
      servable: s.servable,
    })),
  );
  const ipHolder = makeIpHolderAugmentation(
    sources.map((s) => ({
      representativeChunkId: s.representativeChunkId,
      ipHolderName: s.ipHolderName,
    })),
  );
  const ctx: ReadingContext = {
    synthesis: { question: null, claims: [] },
    layout: { resolve: () => null },
    substrate: {
      getChunk: () =>
        // Not used by the decorations pass (the surface resolves sources via
        // the shipped api.getChunk above); present only to satisfy the frozen
        // ReadingContext shape. SPR-04+ wires this to the real read API.
        Promise.reject(
          new Error("substrate.getChunk is not wired in the reading-physics slice"),
        ),
    },
  };
  // Collect both augmentations' declarations and combine. Order-independent:
  // passing [ipHolder, servability] yields the identical resolved set.
  const resolved = collectDecorations([servability, ipHolder], ctx);
  const byKey = new Map<string, ResolvedDecoration>();
  for (const d of resolved) byKey.set(d.key, d);
  return byKey;
}

function SourceCitation({
  source,
  onPreview,
  decoration,
}: {
  source: ResolvedSource;
  onPreview: (chunkId: string) => void;
  /** The COMBINED §9.0 decoration the ServabilityAugmentation declared for
   *  this source (SPR-02 facet apply pass). The augmentation declares the
   *  verdict (servable vs restricted) as a closed-vocabulary class; this
   *  component ENACTS it — choosing the DOM branch from the declared class,
   *  not by re-branching on `source.servable` inline. Undefined only if the
   *  pass produced no decoration for this source (defensive; treated as the
   *  restricted branch so an un-annotated source never silently opens). */
  decoration: ResolvedDecoration | undefined;
}) {
  const label = source.title ?? "an untitled source";
  const locator = source.locator ? `, ${source.locator}` : "";
  // SPR-10 M1 — "whose work grounds this": the IP-holder name is now declared
  // by the IpHolderAugmentation and merged into this combined decoration
  // (SPR-03 M5), no longer read inline off `source.ipHolderName`. The surface
  // owns the "published by …" phrasing (PR-6); the augmentation supplied only
  // the substrate-resolved name. Painted iff the combined decoration carries
  // exactly one owner (the single-source case). A null owner declared nothing,
  // so `ipHolderNames` is empty and no attribution is claimed — the honest
  // unknown. A non-servable source's owner was withheld by the endpoint
  // (ip_holder_name = null), so it never reaches the restricted branch below.
  const ownerName =
    decoration?.ipHolderNames.length === 1 ? decoration.ipHolderNames[0] : null;
  const owner = ownerName ? `, published by ${ownerName}` : "";

  // ENACT the declared §9.0 verdict (PR-6: the augmentation read `servable`
  // from the substrate; the surface honors it, never re-decides it). The
  // servable branch requires the explicitly-declared SERVABLE_CLASS; anything
  // else (RESTRICTED_CLASS, or a missing decoration) takes the withholding
  // branch — fail-closed so a source can never open without a positive
  // servable verdict.
  const servable = decoration?.classNames.includes(SERVABLE_CLASS) ?? false;

  if (!servable) {
    // §9.0: a restricted / taken-down source must NOT open. Show the
    // named source (so the reader knows what backs the claim) with an
    // honest "not available to open" state — never the content.
    return (
      <span
        className="text-[11px] text-ink-soft dark:text-starlight bg-ice-2 dark:bg-charcoal-1 px-1.5 py-0.5 rounded inline-flex items-center gap-1"
        title={decoration?.title ?? RESTRICTED_TITLE}
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
      title={decoration?.title ?? SERVABLE_TITLE}
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

// ── Quality cue (SPR-11 M3) ──────────────────────────────────────────
//
// A quiet, plain-language read of the §14.4 inline rubric. The score is
// READ from the persisted rubric event by the parser; this component only
// renders what it's handed and never re-implements scoring. Three states:
//   - absent  → render nothing (no fabricated score; the no-key / no-rubric
//     case is honest by saying nothing rather than inventing a verdict);
//   - clears the bar → a quiet positive cue, no number shoved forward;
//   - below the bar → a visible flag in plain words, so the operator knows
//     to give the answer another pass.
//
// The pass bar mirrors the substrate's PASS_THRESHOLD (0.5,
// substrate/synthesis_rubric/scorer.py); we don't recompute, we only
// compare the persisted composite against it to pick the wording. The four
// sub-scores, when the persisted note carried them, sit behind a collapsed
// "the detail" toggle so the default surface stays quiet (a raw dump is
// itself noise to the operator).

const QUALITY_PASS_BAR = 0.5;

function QualityCue({ score }: { score: QualityScore | null }) {
  // Absent: the synthesis carried no persisted rubric (no-key / nothing
  // scored). Show nothing rather than a guessed verdict.
  if (!score) return null;

  const low = score.composite < QUALITY_PASS_BAR;

  return (
    <div className="mt-3 text-xs">
      {low ? (
        <p className="text-amber-800 dark:text-sun leading-relaxed">
          This answer reads like it may want another pass before you rely on
          it. The draft came in under our quality bar, so it&rsquo;s worth a
          re-run or an edit.
        </p>
      ) : (
        <p className="text-shadow-1 dark:text-moonlight leading-relaxed">
          This answer clears our quality bar.
        </p>
      )}
      <QualityDetail score={score} />
    </div>
  );
}

/** Optional breakdown, collapsed by default — the four sub-readings the
 *  rubric noted, in plain words. Hidden entirely when the persisted note
 *  carried no sub-scores (an older or free-form note), so we never show
 *  empty rows. */
function QualityDetail({ score }: { score: QualityScore }) {
  const rows: Array<[string, number | null]> = [
    ["Voice and style", score.voiceStyle],
    ["Conviction", score.conviction],
    ["Sourcing", score.citationDensity],
    ["Stayed within the brief", score.constraintCompliance],
  ];
  const present = rows.filter(([, v]) => v !== null) as Array<[string, number]>;
  if (present.length === 0) return null;

  return (
    <details className="mt-1">
      <summary className="cursor-pointer text-shadow-1 dark:text-moonlight hover:text-ink dark:hover:text-bright transition-colors">
        the detail
      </summary>
      <dl className="mt-2 space-y-1">
        {present.map(([label, value]) => (
          <div key={label} className="flex items-baseline gap-2">
            <dt className="text-ink-soft dark:text-starlight">{label}</dt>
            <dd className="font-mono text-shadow-1 dark:text-moonlight">
              {Math.round(value * 100)}%
            </dd>
          </div>
        ))}
      </dl>
    </details>
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

