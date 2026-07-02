import { Fragment } from "react";

import type { InlineSpan } from "../../../types/document_model.gen";
import Citation from "./Citation";
import { renderMath } from "./renderMath";

/**
 * InlineSpans — renders an `InlineSpan[]` (the leaves of block content) to real
 * typography (SPR-03 M2). Data-driven on the `type` discriminator from the
 * SPR-01 model; NO `any`, every member of the union is handled, and the
 * compiler's exhaustiveness check (`assertNever`) fails the build if a future
 * span type is added without a render arm.
 *
 * The arms:
 *  - text      → verbatim text
 *  - strong    → <strong> wrapping nested spans (so `**a *b* c**` nests)
 *  - emphasis  → <em> wrapping nested spans
 *  - link      → <a> (an internal_document_id is a navigation hint SPR-05 wires;
 *                here it renders as a normal link — a link is NAVIGATION, not
 *                PROVENANCE; see SPR-01 docstring)
 *  - code      → inline <code> (verbatim, never re-parsed)
 *  - math      → inline KaTeX via renderMath (degrades VISIBLY on unsupported
 *                macros — rigor #1)
 *  - citation  → the first-class <Citation> marker (M3)
 */

function assertNever(x: never): never {
  throw new Error(`Unhandled inline span: ${JSON.stringify(x)}`);
}

function InlineSpanOne({ span }: { span: InlineSpan }) {
  switch (span.type) {
    case "text":
      return <>{span.text}</>;
    case "strong":
      return (
        <strong className="font-semibold">
          <InlineSpans spans={span.children} />
        </strong>
      );
    case "emphasis":
      return (
        <em className="italic">
          <InlineSpans spans={span.children} />
        </em>
      );
    case "link":
      return (
        <a
          href={span.href}
          // External links open in a new tab; an internal_document_id is a hint
          // SPR-05 can resolve to an in-app open. We keep it as a data attribute
          // so that wiring is additive, not a rewrite.
          {...(span.internal_document_id
            ? { "data-internal-document-id": span.internal_document_id }
            : { target: "_blank", rel: "noopener noreferrer" })}
          className="text-aurora dark:text-sky underline underline-offset-2 hover:decoration-2"
        >
          <InlineSpans spans={span.children} />
        </a>
      );
    case "code":
      return (
        <code className="reader-inline-code font-mono text-[0.92em] px-1 py-px rounded bg-ice-3 dark:bg-charcoal-1 text-ink dark:text-bright">
          {span.text}
        </code>
      );
    case "math": {
      const { html, degraded } = renderMath(span.tex, { display: false });
      // KaTeX emits trusted HTML (or our escaped fallback). dangerouslySet is
      // the standard, safe-here pattern: the input is verbatim TeX from the
      // typed model and KaTeX/our fallback escape it.
      return (
        <span
          className="reader-math reader-math--inline"
          data-math-degraded={degraded ? "true" : undefined}
          // eslint-disable-next-line react/no-danger
          dangerouslySetInnerHTML={{ __html: html }}
        />
      );
    }
    case "citation":
      return <Citation span={span} />;
    default:
      return assertNever(span);
  }
}

export default function InlineSpans({ spans }: { spans: InlineSpan[] }) {
  return (
    <>
      {spans.map((span, i) => (
        <Fragment key={i}>
          <InlineSpanOne span={span} />
        </Fragment>
      ))}
    </>
  );
}
