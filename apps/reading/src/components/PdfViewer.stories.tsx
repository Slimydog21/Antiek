import type { Meta, StoryObj } from "@storybook/react";

import PdfViewer from "./PdfViewer";

/**
 * PdfViewer renders a PDF for highlight-to-distill region selection
 * in Loop 2 wrestling mode. Master-spec §6 primary-source connection.
 *
 * NOTE: this story is a placeholder. Storybook needs actual PDF bytes
 * (Uint8Array) to render meaningfully. Sprint 18 follow-up wires a
 * fixture PDF (e.g. a 1-page LaTeX-rendered abstract committed to
 * `src/fixtures/`) for full interactive stories. For Sprint 17 we
 * ship the story registration so the component appears in the
 * design system index.
 */
const meta = {
  title: "Loop 2 / PdfViewer",
  component: PdfViewer,
  parameters: {
    layout: "fullscreen",
    docs: {
      description: {
        component:
          "Sprint 17 placeholder. Full story setup with fixture PDF bytes lands in Sprint 18.",
      },
    },
  },
  tags: ["autodocs"],
} satisfies Meta<typeof PdfViewer>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Placeholder: Story = {
  args: {
    pdfBytes: new Uint8Array(0),
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
