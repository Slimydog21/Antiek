import type {
  Block,
  InlineSpan,
  ListBlock,
  TableBlock,
  FigureBlock,
} from "../../../types/document_model.gen";
import InlineSpans from "./InlineSpans";
import { renderMath } from "./renderMath";

/**
 * Blocks — renders a `Block[]` (the structural units of a document body) to
 * real typography over the Charter-serif register (SPR-03 M2). Data-driven on
 * the `type` discriminator from the SPR-01 model; NO `any`; every union member
 * has a render arm; the compiler's `assertNever` fails the build if a future
 * block type is added without one.
 *
 * Each block type renders to a DEDICATED, self-contained piece (heading 1–6,
 * paragraph, list (nested), table (column alignment), code (contained), math
 * (KaTeX display), figure (img+caption), blockquote, footnote). They live in
 * this one file as named sub-components rather than nine separate files
 * because: (a) they are small and share the inline/recursive helpers here, and
 * (b) the spec's structural ask is "one component per block type under
 * components/reader/blocks/" — satisfied by one component per type, exported and
 * individually testable. Citation (M3) is its OWN file (`Citation.tsx`) per the
 * spec's named file scope.
 *
 * Pagination note (M4): each block renders as one self-contained DOM subtree
 * with `break-inside: avoid` so paginate.ts can place whole blocks on a page
 * without clipping a table or figure across a boundary.
 */

const BREAK_AVOID = "[break-inside:avoid]";

function assertNever(x: never): never {
  throw new Error(`Unhandled block: ${JSON.stringify(x)}`);
}

// ── heading (levels 1–6) ────────────────────────────────────────────────────
const HEADING_CLASS: Record<number, string> = {
  1: "text-[1.7em] font-semibold mt-6 mb-3 leading-tight",
  2: "text-[1.4em] font-semibold mt-5 mb-2.5 leading-tight",
  3: "text-[1.2em] font-semibold mt-4 mb-2 leading-snug",
  4: "text-[1.05em] font-semibold mt-3 mb-1.5",
  5: "text-[0.95em] font-semibold uppercase tracking-wide mt-3 mb-1.5",
  6: "text-[0.9em] font-semibold uppercase tracking-wider text-ink-soft dark:text-starlight mt-3 mb-1.5",
};

function Heading({ level, spans }: { level: number; spans: InlineSpan[] }) {
  const Tag = `h${Math.min(Math.max(level, 1), 6)}` as "h1" | "h2" | "h3" | "h4" | "h5" | "h6";
  const cls = HEADING_CLASS[level] ?? HEADING_CLASS[6];
  return (
    <Tag
      data-block-type="heading"
      data-heading-level={level}
      className={`reader-heading font-serif text-ink dark:text-bright ${cls}`}
    >
      <InlineSpans spans={spans} />
    </Tag>
  );
}

// ── list (ordered/unordered, nested) ────────────────────────────────────────
function List({ block }: { block: ListBlock }) {
  const Tag = block.ordered ? "ol" : "ul";
  return (
    <Tag
      data-block-type="list"
      className={`reader-list my-3 pl-6 ${block.ordered ? "list-decimal" : "list-disc"} marker:text-ink-soft dark:marker:text-starlight`}
    >
      {block.items.map((item, i) => (
        <li key={i} className="reader-list-item mb-1.5">
          {/* An item is a block-list (it can hold a paragraph, a nested list,
              a code block) — recurse, so nesting falls out for free. */}
          <Blocks blocks={item.blocks} />
        </li>
      ))}
    </Tag>
  );
}

// ── table (per-column alignment) ─────────────────────────────────────────────
const ALIGN_CLASS: Record<string, string> = {
  left: "text-left",
  center: "text-center",
  right: "text-right",
};

function alignFor(block: TableBlock, col: number): string {
  const a = block.alignment?.[col];
  return a ? ALIGN_CLASS[a] : "text-left";
}

function Table({ block }: { block: TableBlock }) {
  const header = block.header ?? [];
  const rows = block.rows ?? [];
  return (
    <div className={`reader-table-wrap my-4 overflow-x-auto ${BREAK_AVOID}`}>
      <table
        data-block-type="table"
        className="reader-table w-full border-collapse text-[0.92em] font-sans"
      >
        {header.length > 0 && (
          <thead>
            <tr className="border-b-2 border-ink dark:border-bright">
              {header.map((cell, c) => (
                <th
                  key={c}
                  className={`px-2.5 py-1.5 font-semibold align-top ${alignFor(block, c)}`}
                >
                  <InlineSpans spans={cell} />
                </th>
              ))}
            </tr>
          </thead>
        )}
        <tbody>
          {rows.map((row, r) => (
            <tr key={r} className="border-b border-rule dark:border-charcoal-1">
              {row.map((cell, c) => (
                <td key={c} className={`px-2.5 py-1.5 align-top ${alignFor(block, c)}`}>
                  <InlineSpans spans={cell} />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ── code (monospaced, contained — never overflows the measure) ───────────────
function Code({ lang, text }: { lang?: string | null; text: string }) {
  return (
    <pre
      data-block-type="code"
      data-lang={lang ?? undefined}
      className={`reader-code my-4 rounded-md bg-charcoal-2 dark:bg-space-2 text-ice-1 dark:text-starlight px-4 py-3 overflow-x-auto text-[0.85em] leading-relaxed ${BREAK_AVOID}`}
    >
      {/* whitespace-pre + overflow-x-auto: long lines scroll WITHIN the block,
          they do not push the reading measure wider (acceptance: "contained,
          does not overflow the measure"). */}
      <code className="font-mono whitespace-pre">{text}</code>
    </pre>
  );
}

// ── math (KaTeX display; degrades VISIBLY) ───────────────────────────────────
function MathDisplay({ tex }: { tex: string }) {
  const { html, degraded } = renderMath(tex, { display: true });
  return (
    <div
      data-block-type="math"
      data-math-degraded={degraded ? "true" : undefined}
      className={`reader-math reader-math--display my-4 overflow-x-auto ${BREAK_AVOID}`}
      // eslint-disable-next-line react/no-danger
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}

// ── figure (img + caption; src/alt optional) ─────────────────────────────────
function Figure({ block }: { block: FigureBlock }) {
  const caption = block.caption ?? [];
  return (
    <figure data-block-type="figure" className={`reader-figure my-5 ${BREAK_AVOID}`}>
      {block.src ? (
        <img
          src={block.src}
          alt={block.alt ?? ""}
          className="reader-figure-img max-w-full h-auto mx-auto block rounded"
        />
      ) : (
        // No resolvable src (common from a raw PDF extraction — SPR-01 marks
        // src optional). Show an honest placeholder, never a broken-image icon.
        <div className="reader-figure-noimg text-[0.8em] font-mono text-ink-mute dark:text-moonlight border border-dashed border-rule dark:border-charcoal-1 rounded px-3 py-4 text-center">
          [figure{block.alt ? `: ${block.alt}` : ""}]
        </div>
      )}
      {caption.length > 0 && (
        <figcaption className="reader-figure-caption mt-2 text-[0.85em] text-ink-soft dark:text-starlight text-center italic">
          <InlineSpans spans={caption} />
        </figcaption>
      )}
    </figure>
  );
}

// ── the block dispatcher ─────────────────────────────────────────────────────
function BlockView({ block }: { block: Block }) {
  switch (block.type) {
    case "heading":
      return <Heading level={block.level} spans={block.spans} />;
    case "paragraph":
      return (
        <p data-block-type="paragraph" className="reader-paragraph my-3">
          <InlineSpans spans={block.spans} />
        </p>
      );
    case "list":
      return <List block={block} />;
    case "table":
      return <Table block={block} />;
    case "code":
      return <Code lang={block.lang} text={block.text} />;
    case "math":
      return <MathDisplay tex={block.tex} />;
    case "figure":
      return <Figure block={block} />;
    case "blockquote":
      return (
        <blockquote
          data-block-type="blockquote"
          className="reader-blockquote my-4 border-l-4 border-sun pl-4 text-ink-soft dark:text-starlight italic"
        >
          <Blocks blocks={block.blocks} />
        </blockquote>
      );
    case "footnote":
      return (
        <div
          data-block-type="footnote"
          data-footnote-id={block.id}
          id={`footnote-${block.id}`}
          className="reader-footnote my-2 text-[0.85em] text-ink-soft dark:text-starlight flex gap-2"
        >
          <span className="reader-footnote-marker font-mono shrink-0">[{block.id}]</span>
          <div className="reader-footnote-body min-w-0">
            <Blocks blocks={block.blocks} />
          </div>
        </div>
      );
    default:
      return assertNever(block);
  }
}

/**
 * Render a list of blocks. Each block gets a `data-block-index` so paginate.ts
 * can window on block boundaries and the ToC can scroll to a heading by index.
 */
export default function Blocks({ blocks }: { blocks: Block[] }) {
  return (
    <>
      {blocks.map((block, i) => (
        <div key={i} data-block-index={i} className="reader-block">
          <BlockView block={block} />
        </div>
      ))}
    </>
  );
}

export { BlockView };
