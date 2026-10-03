/**
 * ForkProvenance.tsx — the fork tab's provenance header (thread-merge +
 * document fork SPR-01, the SPR-00 verdict's salvage from spike B: the
 * provenance rail note becomes the fork tab's header content).
 *
 * Renders ONLY for a fork — a plain document shows nothing, and the line is
 * the whole truth in one glance: what this is, where it came from, and that
 * the original is untouched. The source title comes from the lineage row's
 * join, never a guess; a fork whose session hasn't learned its lineage yet
 * shows nothing rather than a wrong line.
 */
import { useForkLineage } from "../../workspace/forkLineage";

export default function ForkProvenance({ documentId }: { documentId: string }) {
  const forkedFrom = useForkLineage((s) => s.byFork[documentId] ?? null);
  if (!forkedFrom) return null;
  const from = forkedFrom.parent_title?.trim() || "its source";
  return (
    <p
      data-fork-provenance
      className="mt-1 font-serif text-xs italic text-ink-soft dark:text-starlight"
    >
      Forked from {from} on {forkedFrom.created_at.slice(0, 10)} · the original is
      untouched
      {forkedFrom.note ? (
        <span className="not-italic text-shadow-1 dark:text-moonlight">
          {" "}
          — {forkedFrom.note}
        </span>
      ) : null}
    </p>
  );
}
