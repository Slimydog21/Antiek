import type { Document } from "../../../types/document_model.gen";

/**
 * arxivMathDocument — a fixture of REAL arXiv-style equations spanning what
 * KaTeX supports and what it does NOT (SPR-03 rigor #1: math degrades VISIBLY,
 * never silent-blank, never crash). Each math block is annotated with whether
 * KaTeX is expected to render it or degrade it, so the math-fidelity test
 * asserts the EXPECTED behaviour rather than eyeballing.
 *
 * Caveat held sharp (rigor #1): this is still a HAND-WRITTEN fixture of
 * arXiv-style TeX, NOT a real SPR-02 extraction of a fetched arXiv PDF. It
 * proves the renderer's KaTeX path + degrade path are correct; it does NOT
 * prove SPR-02 recovers these from a paper. The handoff states which was
 * verified.
 */

export interface MathCase {
  label: string;
  tex: string;
  /** Expectation: does KaTeX render this, or must it degrade to a visible
   *  fenced-tex fallback? Asserted by the math-fidelity test. */
  expectRender: boolean;
  reason: string;
}

/** The supported cases — standard math KaTeX handles. */
export const SUPPORTED_MATH: MathCase[] = [
  {
    label: "attention",
    tex: "\\mathrm{Attention}(Q,K,V) = \\mathrm{softmax}\\!\\left(\\frac{QK^\\top}{\\sqrt{d_k}}\\right)V",
    expectRender: true,
    reason: "fractions, sqrt, transpose, mathrm — all core KaTeX.",
  },
  {
    label: "gaussian",
    tex: "p(x) = \\frac{1}{\\sqrt{2\\pi\\sigma^2}}\\exp\\!\\left(-\\frac{(x-\\mu)^2}{2\\sigma^2}\\right)",
    expectRender: true,
    reason: "exp, fractions, greek — core KaTeX.",
  },
  {
    label: "sum-limits",
    tex: "\\sum_{i=1}^{n} x_i^2 \\geq \\frac{1}{n}\\left(\\sum_{i=1}^n x_i\\right)^2",
    expectRender: true,
    reason: "sum with limits, inequalities — core KaTeX.",
  },
  {
    label: "aligned-env",
    tex: "\\begin{aligned} a &= b + c \\\\ &= d \\end{aligned}",
    expectRender: true,
    reason: "the `aligned` environment IS supported by KaTeX.",
  },
  {
    label: "cases-env",
    tex: "f(x) = \\begin{cases} a & x > 0 \\\\ b & x \\le 0 \\end{cases}",
    expectRender: true,
    reason: "the `cases` environment IS supported by KaTeX.",
  },
];

/** The unsupported cases — constructs KaTeX genuinely CANNOT typeset even in
 *  non-strict mode, VERIFIED empirically (each emits a `katex-error` node or
 *  throws). These MUST degrade to a VISIBLE form — KaTeX's red error node OR
 *  our fenced-tex fallback — never a silent blank, never a crash, and the
 *  Reader must FLAG them `data-math-degraded="true"`.
 *
 *  HONESTY CAVEAT (rigor #1): KaTeX in non-strict mode renders some UNKNOWN
 *  commands SILENTLY (e.g. `\includegraphics`, a truly undefined `\foo`) with
 *  no error — those are NOT flagged as degraded because KaTeX itself doesn't
 *  signal a failure. That is a real, named limitation: a paper using a custom
 *  `\newcommand` macro the extractor didn't expand can render as empty/garbled
 *  math without a flag. Detecting that would require a TeX allowlist we do not
 *  have this sprint. Recorded, not pretended away. */
export const UNSUPPORTED_MATH: MathCase[] = [
  {
    label: "unbalanced-brace",
    // A genuinely malformed expression (unbalanced) → katex-error node.
    tex: "\\frac{1}{2",
    expectRender: false,
    reason: "malformed TeX (unbalanced brace) — KaTeX emits a visible error node.",
  },
  {
    label: "tikz-picture",
    // TikZ diagrams (common in arXiv) are pure-LaTeX, not math — KaTeX cannot
    // render them at all. → katex-error.
    tex: "\\begin{tikzpicture} \\draw (0,0) -- (1,1); \\end{tikzpicture}",
    expectRender: false,
    reason: "TikZ is unsupported by KaTeX (it is a drawing package) → visible error.",
  },
];

export const arxivMathDocument: Document = {
  id: "fixture-arxiv-math",
  title: "arXiv math — supported and degraded",
  attribution: { ip_holder_id: "arxiv", source_url: null, content_class: "source_declared_open" },
  schema_version: 1,
  blocks: [
    { type: "heading", level: 2, spans: [{ type: "text", text: "Supported equations (KaTeX typesets)" }] },
    ...SUPPORTED_MATH.map((m) => ({ type: "math" as const, display: true, tex: m.tex })),
    { type: "heading", level: 2, spans: [{ type: "text", text: "Unsupported (degrade to visible TeX)" }] },
    ...UNSUPPORTED_MATH.map((m) => ({ type: "math" as const, display: true, tex: m.tex })),
  ],
};
