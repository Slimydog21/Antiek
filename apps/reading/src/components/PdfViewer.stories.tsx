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
