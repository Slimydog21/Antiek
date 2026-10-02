import type { Meta, StoryObj } from "@storybook/react";
import ReadingTypography from "./ReadingTypography";
import ReadingAppearance from "./ReadingAppearance";
import ReadingColumn from "./ReadingColumn";
import MasterMdViewer from "../../modes/ResearchWorkstation/MasterMdViewer";
import type { ParsedSynthesis } from "../../lib/synthesisParser";
import AppearancePanel from "../../modes/Settings/AppearancePanel";
import { DEFAULT_READING_TYPOGRAPHY, READING_FONTS, readingTypographyStyle } from "../../lib/readingTypography";

const TEXT = "# A place for a thought\n\nThe best place to think is one where you can forget the page and follow the thought. A quiet sentence leaves room for an unexpected idea. A familiar word can gather new meaning when there is time to read it carefully.\n\nReading on a screen gives us a choice. We can make the type larger, give the lines more room, or choose letterforms that feel easier to follow. Keep the setting that helps you stay with the passage.\n\nIl1 O0 rn m · é ö ñ · 0123456789";

const meta = { title: "Reading/Typography", component: ReadingTypography, tags: ["a11y-audit"] } satisfies Meta<typeof ReadingTypography>;
export default meta;
type Story = StoryObj<typeof meta>;

export const Reader: Story = {
  render: () => <main className="min-h-screen bg-card text-1 p-4 sm:p-8">
    <header className="flex flex-wrap items-center justify-between gap-4 max-w-3xl mx-auto mb-8"><h1 className="text-xl font-serif">Typography specimen</h1><div className="flex items-center gap-2"><ReadingAppearance /><ReadingTypography /></div></header>
    <ReadingColumn assetId="typography-fixture" text={TEXT} />
  </main>,
};

export const Settings: Story = {
  render: () => <main className="max-w-2xl mx-auto bg-card text-1 p-4 sm:p-8"><AppearancePanel /></main>,
};

const manuscript = {
  synthesisId: null,
  thesisSummary: "A quiet page gives the reader room to follow an idea and consider its evidence.",
  components: [{ index: 1, claim: "Typography preferences should follow the reader across books and research notes.", rationale: "The font, size, spacing and line width are personal choices. The cited material and its provenance stay attached to the passage.", confidence: "moderate", effectiveSourceTier: null, hedgingRequired: false, chunkIds: [], supportingPathIndices: [] }],
  falsificationConditions: [{ condition: "The change fails if the chosen size reaches the preview but leaves the research claim at a fixed size.", specificObservable: "Compare the rendered claim with the thesis after changing text size." }],
  executionRisks: [{ risk: "A font download may fail.", mitigation: "Reading continues in an installed font." }],
  recommendation: "undetermined", hardConstraintsSatisfied: null, totalCostUsd: 0,
  question: "A note on reading", masterMdPath: null, domainsPatched: [], chunkCitations: {}, qualityScore: null,
  reuseProvenance: [], compoundingStat: null,
} satisfies ParsedSynthesis;

export const Manuscript: Story = {
  render: () => <MasterMdViewer synthesis={manuscript} />,
};

export const Portfolio: Story = {
  render: () => <main className="bg-card text-1 px-4 py-8 sm:px-8">
    <h1 className="text-xl max-w-3xl mx-auto mb-3">Antiek's reading fonts</h1>
    <p className="max-w-3xl mx-auto text-sm text-2 mb-10">The same passage in each face. This is a visual comparison, not a reading-speed test.</p>
    <div className="max-w-3xl mx-auto grid gap-10">
      {READING_FONTS.map((font) => <section key={font.id} className="border-t border-hairline pt-4">
        <h2 className="text-base font-semibold mb-1">{font.name}</h2><p className="text-sm text-2 mb-4">{font.description}</p>
        <div className="reading-prose" style={readingTypographyStyle({ ...DEFAULT_READING_TYPOGRAPHY, font: font.id })}>
          <p>The best place to think is one where you can forget the page and follow the thought. A quiet sentence leaves room for an unexpected idea.</p>
          <p className="mt-3"><em>Read at your own pace.</em> <strong>Keep what matters.</strong> Il1 · O0 · rn m</p>
        </div>
      </section>)}
    </div>
  </main>,
};
