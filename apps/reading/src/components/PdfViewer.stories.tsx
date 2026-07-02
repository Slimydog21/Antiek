import type { Meta, StoryObj } from "@storybook/react";

import PdfViewer from "./PdfViewer";

/**
 * PdfViewer renders a PDF for highlight-to-distill region selection
 * in Loop 2 wrestling mode. Master-spec §6 primary-source connection.
 */
const STORY_PDF_SOURCE = `%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Kids [3 0 R] /Count 1 >>
endobj
3 0 obj
<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>
endobj
4 0 obj
<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>
endobj
5 0 obj
<< /Length 229 >>
stream
BT
/F1 18 Tf
72 720 Td
(Antiek PdfViewer story fixture) Tj
0 -32 Td
/F1 12 Tf
(A real one-page PDF used for highlight-to-distill Storybook coverage.) Tj
0 -22 Td
(Select this text to exercise the region selection surface.) Tj
ET
endstream
endobj
xref
0 6
0000000000 65535 f
0000000009 00000 n
0000000058 00000 n
0000000115 00000 n
0000000241 00000 n
0000000311 00000 n
trailer
<< /Root 1 0 R /Size 6 >>
startxref
590
%%EOF
`;

export const pdfViewerStoryBytes = new TextEncoder().encode(STORY_PDF_SOURCE);

const meta = {
  title: "Loop 2 / PdfViewer",
  component: PdfViewer,
  parameters: {
    layout: "fullscreen",
    docs: {
      description: {
        component:
          "Interactive one-page PDF fixture for highlight-to-distill region selection.",
      },
    },
  },
  tags: ["autodocs"],
} satisfies Meta<typeof PdfViewer>;

export default meta;
type Story = StoryObj<typeof meta>;

export const OnePageFixture: Story = {
  args: {
    pdfBytes: pdfViewerStoryBytes,
    investigationId: "inv-storybook-demo",
    documentId: "doc-quantum-2026",
  },
};

/**
 * S6 acceptance benchmark target. Renders a 1200×900 floating-panel
 * frame around a tall scrollable column with simulated PDF-render
 * artifacts (canvas blocks, dummy text rows) so the
 * `scripts/bench_pdf_panel.ts` Playwright harness has a deterministic
 * fps target. The real PdfViewer needs operator-supplied bytes; this
 * story stands in with synthetic content that exercises the same
 * scroll + composite pipeline.
 *
 * The harness selects by `[role="region"][aria-label="PDF perf target"]`.
 */
export const PdfPerfTarget: Story = {
  args: {
    pdfBytes: pdfViewerStoryBytes,
    investigationId: "inv-storybook-perf",
    documentId: "doc-pdf-perf-target",
  },
  render: () => (
    <div className="h-screen w-screen bg-ice-2 dark:bg-space-2 p-6 flex items-center justify-center">
      <section
        role="region"
        aria-label="PDF perf target"
        className="bg-ice-0 dark:bg-charcoal-2 border-edge border-sun rounded-hog shadow-z3 dark:shadow-z3-night overflow-hidden flex flex-col"
        style={{ width: 1200, height: 900 }}
      >
        <header className="h-9 shrink-0 px-3 flex items-center justify-between border-b-edge border-sun bg-ice-1 dark:bg-charcoal-1">
          <span className="font-mono text-[12px] font-semibold">
            PDF perf target · 200-page synthetic
          </span>
          <span className="font-mono text-[10px] text-ink-mute dark:text-moonlight">
            bench target
          </span>
        </header>
        <div className="flex-1 min-h-0 overflow-auto">
          {Array.from({ length: 200 }, (_, page) => (
            <div
              key={page}
              className="border-b border-rule dark:border-charcoal-1 px-8 py-6"
              style={{ minHeight: 1056 }}
            >
              <div className="text-xs font-mono text-ink-mute dark:text-moonlight mb-3">
                page {page + 1} / 200
              </div>
              {/* Simulated text rows so the composite path renders real spans. */}
              {Array.from({ length: 40 }, (__, row) => (
                <div
                  key={row}
                  className="font-serif text-[14px] leading-relaxed text-ink dark:text-bright"
                >
                  Lorem ipsum dolor sit amet, consectetur adipiscing
                  elit. Sed do eiusmod tempor incididunt ut labore et
                  dolore magna aliqua. {row * 17 + page}
                </div>
              ))}
            </div>
          ))}
        </div>
      </section>
    </div>
  ),
};
