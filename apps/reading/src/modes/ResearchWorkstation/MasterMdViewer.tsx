import { useState } from "react";

import LemonButton from "../../components/lemon/LemonButton";
import { toast } from "../../components/lemon/LemonToast";
import type { ParsedClaim, ParsedSynthesis, Recommendation } from "../../lib/synthesisParser";
import { openNotebook } from "../../workspace/actions";
import ChunkModal from "./ChunkModal";

/**
 * Renders a completed investigation's synthesis as a hybrid markdown +
 * structured-claim-span document. Reading typography (serif body) for
 * the substantive prose; sans-serif chrome for chips and metadata.
 *
 * Hover any claim's chunk-citation chip to expand to a modal with the
 * actual chunk text. Cross-mode deep-link via the modal's "Open in
 * document viewer" button (Sprint 11 day 6).
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
                  // S7 acceptance — "Add to notebook" from MasterMdViewer.
                  // Opens the TipTap notebook editor as a floating panel
                  // pre-seeded with a master-section block referencing
                  // this synthesis. The block resolves the live synthesis
                  // at render time per architecture_notes §13.
                  // Derive a stable notebook id from the question so
                  // re-opening from the same synthesis focuses the
                  // existing notebook rather than creating a duplicate.
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
                    title: "Add to notebook",
                  });
                  toast.ok("Notebook open — paste the synthesis-section block via the slash menu.");
                }}
              >
                Add to notebook
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
        {claim.chunkIds.map((cid) => (
          <button
            key={cid}
            onClick={() => onChunkClick(cid)}
            className="text-[10px] font-mono text-ink-soft dark:text-starlight bg-ice-3 dark:bg-charcoal-1 hover:bg-ice-4 dark:bg-charcoal-1 px-1.5 py-0.5 rounded transition-colors"
            title="Click to view source chunk"
          >
            {shortenChunkId(cid)}
          </button>
        ))}
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

function shortenChunkId(cid: string): string {
  if (cid.length <= 18) return cid;
  return cid.slice(0, 14) + "…";
}
