import katex from "katex";

/**
 * renderMath — the ONE KaTeX entry point for the Reader (SPR-03 M2, rigor #1).
 *
 * KaTeX does NOT support every LaTeX macro an arXiv paper uses (``\label``,
 * ``\ref``, many ``amsmath`` environments, custom ``\newcommand`` macros, etc.).
 * The honesty bar this sprint must hold is: unsupported math degrades to a
 * VISIBLE fenced-``tex`` fallback — never a silent blank, never a crash. So we
 * call KaTeX with ``throwOnError: false`` AND wrap it: if KaTeX raises (or its
 * own error-colour path triggers), we return the raw TeX in a labelled
 * ``<code class="reader-math-fallback">`` element the reader can SEE, so a
 * macro KaTeX can't typeset still shows its source rather than vanishing.
 *
 * Returns an object with the HTML string KaTeX produced (or the escaped raw TeX
 * for the fallback) plus a ``degraded`` flag the caller can use to tag the DOM
 * (tests assert on it; the visible fallback styling keys on it).
 *
 * Why ``katex`` directly and not ``rehype-katex``: the Reader renders the TYPED
 * model (a ``MathSpan.tex`` / ``MathBlock.tex`` string), not a re-parsed
 * markdown document, so there is no markdown AST for the rehype plugin to walk.
 * ``rehype-katex`` is the right tool when react-markdown parses a string; here
 * the math is already isolated as a verbatim ``tex`` field, so the direct KaTeX
 * call is the honest, minimal path. (``rehype-katex`` remains available for the
 * one place we DO let react-markdown parse a string — see ``InlineMarkdown``.)
 */

export interface RenderedMath {
  /** Trusted HTML: KaTeX output, or escaped raw TeX for the visible fallback. */
  html: string;
  /** True when KaTeX could not typeset the source and we degraded to raw TeX. */
  degraded: boolean;
}

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

export function renderMath(tex: string, opts: { display: boolean }): RenderedMath {
  try {
    // ``throwOnError: false`` makes KaTeX render an error node (a red ``<span
    // class="katex-error">`` carrying the source) instead of throwing for a
    // RECOVERABLE parse error — e.g. an unsupported environment like
    // ``\begin{equation}`` or unbalanced braces. That error node is ITSELF a
    // visible degrade (the source is shown, not blank), but it is KaTeX's
    // rendering, not our fenced-tex fallback. We detect it and report
    // ``degraded: true`` so the honesty signal is accurate: a macro KaTeX
    // could not typeset is FLAGGED, whether it threw or rendered an error node.
    // (Verified empirically: ``\begin{equation}`` and ``\frac{1}{2`` do NOT
    // throw with this flag — they emit ``katex-error``; a genuinely unknown
    // command may render or error depending on ``strict``. Both visible-error
    // paths count as a degrade.)
    const html = katex.renderToString(tex, {
      displayMode: opts.display,
      throwOnError: false,
      // The colour KaTeX paints an in-string error in — kept visible (not the
      // page text colour) so a partially-failed expression is obvious.
      errorColor: "#c63d24",
      // Defensive: cap macro expansion so a pathological ``\newcommand`` loop
      // in an extracted paper can't hang the render.
      maxExpand: 1000,
      strict: false,
    });
    // KaTeX rendered a visible error node ⇒ a degrade (the equation did not
    // typeset; the reader sees the source in red).
    const degraded = html.includes("katex-error");
    return { html, degraded };
  } catch (err) {
    // Hard failure — KaTeX could not typeset this at all. Degrade VISIBLY to
    // the raw TeX source in a labelled fenced element (rigor #1: never blank,
    // never crash). The reader sees exactly what the paper wrote.
    if (typeof console !== "undefined" && console.warn) {
      console.warn(
        `[Reader] KaTeX could not typeset math; showing raw TeX. tex=${JSON.stringify(
          tex.slice(0, 120),
        )}`,
        err,
      );
    }
    const tag = opts.display ? "div" : "span";
    const cls = opts.display
      ? "reader-math-fallback reader-math-fallback--display"
      : "reader-math-fallback reader-math-fallback--inline";
    const html = `<${tag} class="${cls}" data-math-degraded="true" title="This equation could not be typeset; showing its TeX source."><code>${escapeHtml(
      tex,
    )}</code></${tag}>`;
    return { html, degraded: true };
  }
}
