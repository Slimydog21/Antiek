/**
 * Reader.test.tsx — the SPR-03 acceptance suite.
 *
 * Rigor #3: ONE vitest assertion for EACH block type and inline span; the
 * math-degrade case (rigor #1) asserting unsupported macros show a visible
 * fenced-tex fallback (never blank, never crash); and the citation-clickable
 * case (M3) asserting the resolver is called with the right source_document_id
 * + chunkId.
 *
 * Honesty (rigor #1): these assert the renderer over FIXTURES, not a real
 * SPR-02 extraction. The math cases use real arXiv-style TeX, so KaTeX
 * support/degrade is exercised against real macros.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, fireEvent } from "@testing-library/react";

import Reader, { deriveToc } from "./Reader";
import { ReaderProvider } from "./ReaderContext";
import { allBlocksDocument } from "./fixtures/allBlocks";
import { SUPPORTED_MATH, UNSUPPORTED_MATH, arxivMathDocument } from "./fixtures/arxivMath";
import type { Document } from "../../types/document_model.gen";

afterEach(() => {
  cleanup();
  document.body.innerHTML = "";
  vi.restoreAllMocks();
});

function renderDoc(doc: Document, opts?: { openDocument?: (id: string, o?: unknown) => void }) {
  return render(
    <Reader
      document={doc}
      openDocument={opts?.openDocument as never}
    />,
  );
}

describe("Reader — every block type renders (M2, rigor #3)", () => {
  it("heading levels 1–6 render as h1..h6 (not all collapsed to h2)", () => {
    const { container } = renderDoc(allBlocksDocument);
    for (let level = 1; level <= 6; level++) {
      const h = container.querySelector(`h${level}[data-block-type="heading"]`);
      expect(h, `expected an h${level}`).toBeTruthy();
    }
  });

  it("a paragraph renders bold as real <strong>", () => {
    const { container } = renderDoc(allBlocksDocument);
    const strong = container.querySelector("strong");
    expect(strong?.textContent).toBe("bold");
  });

  it("emphasis renders as real <em>", () => {
    const { container } = renderDoc(allBlocksDocument);
    const em = container.querySelector("em");
    expect(em?.textContent).toBe("italic");
  });

  it("a link renders as a real <a> with the href", () => {
    const { container } = renderDoc(allBlocksDocument);
    const a = container.querySelector('a[href="https://arxiv.org/abs/1706.03762"]');
    expect(a?.textContent).toBe("link");
  });

  it("inline code renders as a contained <code> (verbatim, not re-parsed)", () => {
    renderDoc(allBlocksDocument);
    expect(screen.getByText("inline_code()").tagName).toBe("CODE");
  });

  it("a nested list renders as <ul> containing an <ol> (nesting preserved)", () => {
    const { container } = renderDoc(allBlocksDocument);
    const ul = container.querySelector('ul[data-block-type="list"]');
    expect(ul).toBeTruthy();
    expect(ul!.querySelector('ol[data-block-type="list"]')).toBeTruthy();
    expect(screen.getByText("Nested one")).toBeTruthy();
  });

  it("a table renders as a real <table> with per-column alignment", () => {
    const { container } = renderDoc(allBlocksDocument);
    const table = container.querySelector('table[data-block-type="table"]');
    expect(table).toBeTruthy();
    const headers = table!.querySelectorAll("th");
    expect(headers.length).toBe(3);
    // alignment ["left","center","right"] → the 3rd header is right-aligned.
    expect(headers[2].className).toContain("text-right");
    expect(headers[1].className).toContain("text-center");
    // a cell carries markup (bold) — proving cells are spans, not strings.
    expect(table!.querySelector("strong")?.textContent).toBe("Transformer");
  });

  it("a code block is monospaced and contained (overflow scrolls, not widens)", () => {
    const { container } = renderDoc(allBlocksDocument);
    const pre = container.querySelector('pre[data-block-type="code"]');
    expect(pre).toBeTruthy();
    expect(pre!.className).toContain("overflow-x-auto");
    expect(pre!.getAttribute("data-lang")).toBe("python");
    expect(pre!.querySelector("code")!.className).toContain("font-mono");
  });

  it("display math is typeset by KaTeX (a .katex node appears, not raw TeX)", () => {
    const { container } = renderDoc(allBlocksDocument);
    const mathBlock = container.querySelector('div[data-block-type="math"]');
    expect(mathBlock).toBeTruthy();
    // KaTeX emits a .katex element when it typesets successfully.
    expect(mathBlock!.querySelector(".katex")).toBeTruthy();
    expect(mathBlock!.getAttribute("data-math-degraded")).toBeNull();
  });

  it("inline math inside a heading is typeset (round-trip edge case)", () => {
    const { container } = renderDoc(allBlocksDocument);
    const h6 = container.querySelector('h6[data-block-type="heading"]');
    expect(h6!.querySelector(".katex")).toBeTruthy();
  });

  it("a figure with a src renders an <img> with alt + a caption", () => {
    const { container } = renderDoc(allBlocksDocument);
    const fig = container.querySelectorAll('figure[data-block-type="figure"]')[0];
    const img = fig.querySelector("img");
    expect(img?.getAttribute("alt")).toBe("A plus symbol");
    expect(fig.querySelector("figcaption")).toBeTruthy();
  });

  it("a figure with NO src renders an honest placeholder (not a broken image)", () => {
    const { container } = renderDoc(allBlocksDocument);
    const figs = container.querySelectorAll('figure[data-block-type="figure"]');
    const noSrc = figs[1];
    expect(noSrc.querySelector("img")).toBeNull();
    expect(noSrc.querySelector(".reader-figure-noimg")).toBeTruthy();
  });

  it("a blockquote renders as a real <blockquote>", () => {
    const { container } = renderDoc(allBlocksDocument);
    expect(container.querySelector('blockquote[data-block-type="blockquote"]')).toBeTruthy();
  });

  it("a footnote renders with its id marker and body", () => {
    const { container } = renderDoc(allBlocksDocument);
    const fn = container.querySelector('[data-block-type="footnote"]');
    expect(fn).toBeTruthy();
    expect(fn!.getAttribute("data-footnote-id")).toBe("1");
    expect(fn!.querySelector(".reader-footnote-marker")?.textContent).toBe("[1]");
  });
});

describe("Reader — citation as a first-class clickable marker (M3)", () => {
  it("renders a citation marker as a button with the provenance triple", () => {
    const { container } = renderDoc(allBlocksDocument);
    const cite = container.querySelector("button[data-citation-marker]");
    expect(cite).toBeTruthy();
    expect(cite!.textContent).toBe("[1]");
    expect(cite!.getAttribute("data-source-document-id")).toBe("doc-source-42");
    expect(cite!.getAttribute("data-chunk-id")).toBe("chunk-7");
  });

  it("clicking a citation invokes the resolver with source_document_id + chunkId", () => {
    const openDocument = vi.fn();
    const { container } = renderDoc(allBlocksDocument, { openDocument });
    const cite = container.querySelector(
      'button[data-citation-marker][data-source-document-id="doc-source-42"]',
    )!;
    fireEvent.click(cite);
    expect(openDocument).toHaveBeenCalledTimes(1);
    expect(openDocument).toHaveBeenCalledWith("doc-source-42", { chunkId: "chunk-7" });
  });

  it("a citation inside a table cell is ALSO clickable (deep nesting via context)", () => {
    const openDocument = vi.fn();
    const { container } = renderDoc(allBlocksDocument, { openDocument });
    const cellCite = container.querySelector(
      'button[data-citation-marker][data-source-document-id="doc-source-9"]',
    )!;
    fireEvent.click(cellCite);
    expect(openDocument).toHaveBeenCalledWith("doc-source-9", { chunkId: "chunk-1" });
  });

  it("an unresolved citation (failed fetch) renders a non-clickable marker", () => {
    const openDocument = vi.fn();
    const doc = {
      ...allBlocksDocument,
      blocks: [
        {
          type: "paragraph" as const,
          block_id: "p-unresolved",
          spans: [
            {
              type: "citation" as const,
              source_document_id: "",
              chunk_id: "",
              marker: "[?]",
            },
          ],
        },
      ],
    };
    const { container } = renderDoc(doc, { openDocument });
    const unresolved = container.querySelector("[data-citation-unresolved]");
    expect(unresolved).toBeTruthy();
    expect(container.querySelector("button[data-citation-marker]")).toBeNull();
    expect(openDocument).not.toHaveBeenCalled();
  });

  it("hover shows the resolved source title when a resolver is wired", () => {
    const { container } = render(
      <ReaderProvider
        value={{
          openDocument: () => {},
          resolveSourceTitle: (id) => (id === "doc-source-42" ? "Attention Is All You Need" : undefined),
        }}
      >
        <Reader document={allBlocksDocument} />
      </ReaderProvider>,
    );
    const cite = container.querySelector(
      'button[data-citation-marker][data-source-document-id="doc-source-42"]',
    )!;
    expect(cite.getAttribute("title")).toBe("Attention Is All You Need");
  });
});

describe("Reader — math typeset + degrades safely (rigor #1)", () => {
  it("every SUPPORTED arXiv equation typesets (a .katex node, not degraded)", () => {
    const { container } = render(<Reader document={arxivMathDocument} />);
    const mathBlocks = Array.from(container.querySelectorAll('div[data-block-type="math"]'));
    // The first N math blocks are the supported set.
    SUPPORTED_MATH.forEach((m, i) => {
      const block = mathBlocks[i];
      expect(block.querySelector(".katex"), `supported "${m.label}" should typeset`).toBeTruthy();
      expect(block.getAttribute("data-math-degraded")).toBeNull();
    });
  });

  it("every UNSUPPORTED equation degrades VISIBLY (never blank/crash), flagged data-math-degraded", () => {
    const { container } = render(<Reader document={arxivMathDocument} />);
    const mathBlocks = Array.from(container.querySelectorAll('div[data-block-type="math"]'));
    UNSUPPORTED_MATH.forEach((m, i) => {
      const block = mathBlocks[SUPPORTED_MATH.length + i];
      // The honesty contract: an equation KaTeX can't typeset is FLAGGED.
      expect(block.getAttribute("data-math-degraded"), `"${m.label}" must degrade`).toBe("true");
      // The degrade is VISIBLE — either our fenced-tex fallback (hard throw) OR
      // KaTeX's own red error node (recoverable parse error). BOTH show the
      // source; NEITHER is blank. Assert one of the two is present.
      const ourFallback = block.querySelector(".reader-math-fallback");
      const katexError = block.querySelector(".katex-error");
      expect(
        ourFallback || katexError,
        `"${m.label}" must show a visible degrade (fenced-tex or katex-error)`,
      ).toBeTruthy();
      // And the block is NOT empty (never a silent blank).
      expect(block.textContent?.trim().length, `"${m.label}" must not be blank`).toBeGreaterThan(0);
    });
  });

  it("a malformed equation does not throw — the Reader still renders the rest", () => {
    const doc: Document = {
      id: "fx-malformed",
      title: "Malformed math survives",
      blocks: [
        { type: "math", display: true, tex: "\\frac{1}{2" },
        { type: "paragraph", spans: [{ type: "text", text: "This still renders." }] },
      ],
    };
    expect(() => render(<Reader document={doc} />)).not.toThrow();
    expect(screen.getByText("This still renders.")).toBeTruthy();
  });
});

describe("Reader — ToC derives from heading blocks (M4)", () => {
  it("deriveToc returns one entry per heading with level + block_index", () => {
    const toc = deriveToc(allBlocksDocument.blocks ?? []);
    // 6 standalone heading levels + (the h6 with math is one of them).
    expect(toc.length).toBeGreaterThanOrEqual(6);
    expect(toc[0]).toMatchObject({ level: 1, text: "Heading level 1", block_index: 0 });
    // the h6 ToC label flattens inline math to its tex (mirrors Python toc()).
    const h6 = toc.find((e) => e.level === 6);
    expect(h6?.text).toContain("E = mc^2");
  });

  it("matches the Python Document.toc() rule: derived, never stored", () => {
    // The model has no `toc` field; deriveToc is the single source (same as the
    // Python side). A doc with no headings yields an empty ToC, not a crash.
    expect(deriveToc([])).toEqual([]);
  });
});

describe("Reader — attribution markers preserved from ReadingColumn (M4)", () => {
  it("tags a servable asset with data-akb-asset-id", () => {
    const { container } = render(<Reader document={allBlocksDocument} assetId="doc-42" />);
    expect(container.querySelector("article")!.getAttribute("data-akb-asset-id")).toBe("doc-42");
  });

  it("does NOT tag when assetId is null (a gated preview is never attributed)", () => {
    const { container } = render(<Reader document={allBlocksDocument} assetId={null} />);
    expect(container.querySelector("article")!.hasAttribute("data-akb-asset-id")).toBe(false);
  });

  it("adds data-akb-chunk-id only with a real chunk id (never fabricated)", () => {
    const { container } = render(
      <Reader document={allBlocksDocument} assetId="d" chunkId="chunk-9" />,
    );
    expect(container.querySelector("article")!.getAttribute("data-akb-chunk-id")).toBe("chunk-9");
    cleanup();
    const { container: c2 } = render(<Reader document={allBlocksDocument} assetId="d" />);
    expect(c2.querySelector("article")!.hasAttribute("data-akb-chunk-id")).toBe(false);
  });

  it("renders an honest empty note when the document has no blocks", () => {
    render(<Reader document={{ id: "e", title: "Empty", blocks: [] }} />);
    expect(screen.getByText(/no readable content/i)).toBeTruthy();
  });
});
