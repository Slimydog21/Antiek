import { useEffect, useState } from "react";

import {
  composeResearchArtifacts,
  type ArtifactIndexResponse,
} from "../../api/research";

export default function ResearchCompositionReview({
  investigationIds,
}: {
  investigationIds?: unknown;
}) {
  const ids = Array.isArray(investigationIds)
    ? investigationIds.filter(
        (value): value is string =>
          typeof value === "string" && value.length > 0 && value === value.trim(),
      )
    : [];
  const valid = ids.length >= 2 && ids.length <= 8 && new Set(ids).size === ids.length;
  const [index, setIndex] = useState<ArtifactIndexResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setIndex(null);
    setError(null);
    if (!valid) {
      setError("This research collection is no longer valid.");
      return () => {
        cancelled = true;
      };
    }
    void composeResearchArtifacts(ids)
      .then((result) => {
        if (!cancelled) setIndex(result);
      })
      .catch(() => {
        if (!cancelled) setError("Couldn’t load this research collection.");
      });
    return () => {
      cancelled = true;
    };
  }, [investigationIds]);

  return (
    <section className="h-full overflow-auto p-5 text-ink dark:text-bright">
      <header className="mb-5 border-b border-rule pb-4 dark:border-charcoal-1">
        <h1 className="font-serif text-xl">Research composition review</h1>
        <p className="mt-1 text-sm text-shadow-1 dark:text-moonlight">
          Collected research — not yet synthesized.
        </p>
      </header>
      {error && <p role="alert" className="text-sm text-emperor">{error}</p>}
      {!error && !index && <p className="text-sm italic text-shadow-1">Loading…</p>}
      {index && (
        <>
          <section className="mb-5 border border-rule bg-parchment-1 p-3 dark:border-charcoal-1 dark:bg-ink" aria-label="Draft basis">
            <div className="flex items-baseline justify-between gap-3">
              <h2 className="font-mono text-[11px] uppercase tracking-wider">Draft basis</h2>
              <span className="font-mono text-[10px] uppercase text-shadow-1">Version {index.composition_version}</span>
            </div>
            <p className="mt-2 text-sm">This fingerprint names the exact ordered inputs shown below.</p>
            <p className="mt-1 break-all font-mono text-[10px] text-shadow-1" title={index.composition_id}>
              {index.composition_id}
            </p>
            <p className="mt-2 text-xs text-shadow-1">No model, spend approval, synthesis, or merge has run.</p>
          </section>
          <ol className="divide-y divide-rule border-y border-rule dark:divide-charcoal-1 dark:border-charcoal-1">
            {index.members.map((member, position) => (
              <li key={member.investigation_id} className="grid grid-cols-[2.5rem_1fr] gap-3 py-4">
                <span className="pt-0.5 font-mono text-xs text-shadow-1" aria-label={`Position ${position + 1}`}>
                  {String(position + 1).padStart(2, "0")}
                </span>
                <div>
                  <h2 className="font-serif text-base leading-snug">{member.question}</h2>
                  <p className="mt-1 font-mono text-[10px] uppercase tracking-wide text-shadow-1">
                    {member.blocks.length} {member.blocks.length === 1 ? "block" : "blocks"} · hash {member.content_hash.slice(0, 12)}
                  </p>
                  {member.blocks.length > 0 && (
                    <ul className="mt-3 space-y-2 border-l border-rule pl-3 dark:border-charcoal-1">
                      {member.blocks.map((block) => (
                        <li key={`${block.kind}:${block.node_id}`} className="text-sm leading-snug">
                          <span className="mr-2 font-mono text-[10px] uppercase text-shadow-1">{block.kind}</span>
                          {block.label}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              </li>
            ))}
          </ol>
          <section className="mt-5" aria-label="Content conflicts">
            <h2 className="font-mono text-[11px] uppercase tracking-wider">Content conflicts</h2>
            {index.conflicts.length === 0 ? (
              <p className="mt-2 text-sm text-shadow-1">No matching content hashes.</p>
            ) : (
              <ul className="mt-2 space-y-1 text-sm">
                {index.conflicts.map((conflict) => (
                  <li key={`${conflict.first_investigation_id}:${conflict.second_investigation_id}`}>
                    {conflict.first_investigation_id} and {conflict.second_investigation_id} share hash {conflict.content_hash.slice(0, 12)}.
                  </li>
                ))}
              </ul>
            )}
          </section>
        </>
      )}
    </section>
  );
}
