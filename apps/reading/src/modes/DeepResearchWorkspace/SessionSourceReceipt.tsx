import type { ResearchSourcePolicy } from "../../lib/api";

const SOURCE_LABELS: Record<ResearchSourcePolicy, string> = {
  operator_corpus: "Corpus",
  web: "Web",
  arxiv: "arXiv",
  substack: "Substack",
};

export default function SessionSourceReceipt({
  policy,
  execution,
}: {
  policy: ResearchSourcePolicy[];
  execution: "metadata_only" | "runner_consumed" | null;
}) {
  if (policy.length === 0) return null;
  return (
    <section className="rounded-md border border-rule bg-ice-0 px-3 py-2 text-[11px] font-mono text-ink-mute dark:border-charcoal-1 dark:bg-charcoal-2 dark:text-moonlight">
      <span className="uppercase tracking-wider text-shadow-1 dark:text-moonlight">
        Session sources
      </span>
      <span className="ml-2 text-ink dark:text-bright">
        {policy.map((item) => SOURCE_LABELS[item] ?? item).join(" · ")}
      </span>
      <span className="ml-2 font-serif text-[12px]">
        {execution === "runner_consumed"
          ? "runner source receipts should now be inspected"
          : "carried as launch metadata; retrieval receipts arrive separately"}
      </span>
    </section>
  );
}
