/**
 * DRW SPR-10 M6 — inline structural-gap surfacing.
 *
 * Shows the structural gaps (SPR-07) relevant to THIS document; clicking one
 * spins a research seeded from it. Only graph-grounded gaps appear — the
 * backend (`/reading/.../gaps`) returns gaps scoped to the document's nodes,
 * and SPR-07 guarantees every candidate traces to a structural fact (no LLM
 * free-association), so the UI renders what it is given without inventing.
 */

import LemonButton from "../../components/lemon/LemonButton";
import type { DocumentGap } from "../../api/reading";

const KIND_LABEL: Record<string, string> = {
  unanswered_question: "open question",
  unsupported_claim: "under-supported",
  contradiction: "contradiction",
};

export default function GapSidebar({ gaps, onSpin }: { gaps: DocumentGap[]; onSpin: (gap: DocumentGap) => void }) {
  if (!gaps.length) {
    return (
      <p className="text-[11px] text-shadow-1 dark:text-moonlight">
        No structural gaps for this document yet.
      </p>
    );
  }
  return (
    <ul className="flex flex-col gap-2">
      {gaps.map((g) => (
        <li key={g.gap_id} className="rounded-md border border-ice-4 bg-ice-1 p-2 dark:border-slate-2 dark:bg-charcoal-1">
          <div className="mb-1 flex items-center justify-between">
            <span className="text-[10px] uppercase tracking-[0.1em] text-shadow-1 dark:text-moonlight">
              {KIND_LABEL[g.kind] ?? g.kind}
            </span>
            <span className="font-mono text-[10px] text-shadow-1 dark:text-moonlight">
              impact {g.impact_score.toFixed(2)}
            </span>
          </div>
          <p className="mb-1.5 text-xs text-ink dark:text-bright">{g.question}</p>
          <LemonButton size="sm" variant="tertiary" onClick={() => onSpin(g)}>
            Spin a research →
          </LemonButton>
        </li>
      ))}
    </ul>
  );
}
