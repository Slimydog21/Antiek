/**
 * Residual (auj): knowledge-dense publication quick-call presets (pure catalog).
 *
 * Extracted from PublicationAttachPanel so arxiv/substack/url connectors are
 * hard to vary and importable without panel coupling (parity competitiveDrQuality).
 *
 * Presets only insert refs — never auto-hydrate or invent live body.
 * Dual-gate L1/L2 live injectors remain operator-only.
 */

export type KnowledgeDensePublicationKind = "arxiv" | "substack" | "url";

export type KnowledgeDensePublicationPreset = {
  id: string;
  label: string;
  reference: string;
  kind: KnowledgeDensePublicationKind;
};

/**
 * Curated knowledge-dense publication handles for deep research.
 * Residual trail: agx · ask · asy · ati · auh · auj extract.
 */
export const KNOWLEDGE_DENSE_PUBLICATION_PRESETS: readonly KnowledgeDensePublicationPreset[] =
  [
    {
      id: "attention-is-all-you-need",
      label: "Attention (arXiv)",
      reference: "arxiv:1706.03762",
      kind: "arxiv",
    },
    {
      id: "bert",
      label: "BERT (arXiv)",
      reference: "arxiv:1810.04805",
      kind: "arxiv",
    },
    {
      id: "gpt-3",
      label: "GPT-3 (arXiv)",
      reference: "arxiv:2005.14165",
      kind: "arxiv",
    },
    {
      id: "scaling-laws",
      label: "Scaling laws (arXiv)",
      reference: "arxiv:2001.08361",
      kind: "arxiv",
    },
    // Residual (ask): RAG + Constitutional AI — knowledge-dense deep research spine.
    {
      id: "retrieval-augmented-generation",
      label: "RAG (arXiv)",
      reference: "arxiv:2005.11401",
      kind: "arxiv",
    },
    {
      id: "constitutional-ai",
      label: "Constitutional AI (arXiv)",
      reference: "arxiv:2212.08073",
      kind: "arxiv",
    },
    // Residual (asy): ReAct + Toolformer — agentic multi-step / tool-use DR spine.
    {
      id: "react-synergizing-reasoning",
      label: "ReAct (arXiv)",
      reference: "arxiv:2210.03629",
      kind: "arxiv",
    },
    {
      id: "toolformer",
      label: "Toolformer (arXiv)",
      reference: "arxiv:2302.04761",
      kind: "arxiv",
    },
    // Residual (ati): Tree of Thoughts — multi-path deliberate reasoning.
    {
      id: "tree-of-thoughts",
      label: "Tree of Thoughts (arXiv)",
      reference: "arxiv:2305.10601",
      kind: "arxiv",
    },
    // Residual (auh): Self-Consistency — sample-and-vote multi-path quality.
    {
      id: "self-consistency",
      label: "Self-Consistency (arXiv)",
      reference: "arxiv:2203.11171",
      kind: "arxiv",
    },
    {
      id: "lilian-weng-attention",
      label: "Lilian Weng · Attention",
      reference: "https://lilianweng.github.io/posts/2018-06-24-attention/",
      kind: "url",
    },
    {
      id: "substack-example",
      label: "Substack (example URL)",
      reference:
        "https://www.lesswrong.com/posts/7MCqRnZzvszsxgtJi/mysteries-of-mode-collapse",
      kind: "substack",
    },
  ] as const;

/** Count of curated knowledge-dense connectors (Settings/honesty chrome). */
export function knowledgeDensePresetCount(): number {
  return KNOWLEDGE_DENSE_PUBLICATION_PRESETS.length;
}

/** Lookup by id — never invents missing presets. */
export function knowledgeDensePresetById(
  id: string | null | undefined,
): KnowledgeDensePublicationPreset | null {
  const key = String(id || "").trim();
  if (!key) return null;
  return (
    KNOWLEDGE_DENSE_PUBLICATION_PRESETS.find((p) => p.id === key) ?? null
  );
}
