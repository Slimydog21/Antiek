import type { Meta, StoryObj } from "@storybook/react";

import { EvidenceArchiveAtlasFrame, type EvidenceArchivePhase } from "./index";

const meta = { title: "Documents / Evidence Archive Atlas", component: EvidenceArchiveAtlasFrame, parameters: { layout: "fullscreen", lostpixel: { waitBeforeScreenshot: 500 } }, tags: ["autodocs", "a11y-audit"] } satisfies Meta<typeof EvidenceArchiveAtlasFrame>;
export default meta;
type Story = StoryObj<typeof meta>;

function Survey({ counts = [12, 8, 5, 3, 1] }: { counts?: number[] }) {
  return <><section className="evidence-archive-atlas__tiers grid grid-cols-5 gap-2" aria-label="Documents by source tier">{counts.map((count, i) => <div key={i} className="rounded-md border border-rule px-3 py-2 text-center"><p className="font-serif text-base">{count}</p><p className="font-mono text-[10px] uppercase">Tier {i + 1}</p></div>)}</section><p className="evidence-archive-atlas__tier-caption">Tier 1 is peer-reviewed primary evidence; Tier 5 is anonymous material.</p></>;
}

function Filters({ tier = "all", investigation = "" }: { tier?: string; investigation?: string }) {
  return <section className="evidence-archive-atlas__filters space-y-3 rounded-md border border-rule p-4" aria-label="Archive filters"><div className="flex flex-wrap gap-2">{["all", "tier 1", "tier 2", "tier 3", "tier 4", "tier 5"].map((label) => <button key={label} aria-pressed={label === tier} className={`rounded-md px-2.5 py-1 font-mono text-xs ${label === tier ? "bg-ink text-white" : "bg-ice-3"}`}>{label}</button>)}</div><label className="block text-xs">Investigation id<input readOnly value={investigation} className="mt-1.5 w-full rounded border border-rule p-2 font-mono" /></label></section>;
}

function Table() { return <table className="w-full border-collapse text-left"><thead><tr><th>Title</th><th>Investigation</th><th>Tier</th></tr></thead><tbody><tr className="border-t border-rule"><td className="py-3 font-serif">Attention Is All You Need</td><td className="font-mono text-xs">inv-transform</td><td>tier 1</td></tr><tr className="border-t border-rule"><td className="py-3 font-serif">Model routing field notes</td><td className="font-mono text-xs">unassigned</td><td>tier 3</td></tr></tbody></table>; }

function Fixture({ phase, production = false, children }: { phase: EvidenceArchivePhase; production?: boolean; children: React.ReactNode }) { return <main className="h-screen"><EvidenceArchiveAtlasFrame phase={phase} visualFixture={!production}><div className="evidence-archive-atlas__console space-y-6">{children}</div></EvidenceArchiveAtlasFrame></main>; }

export const Surveying: Story = { render: () => <Fixture phase="Surveying"><Survey counts={[0, 0, 0, 0, 0]} /><Filters /><p role="status">Charting the archive…</p></Fixture> };
export const EmptyRange: Story = { render: () => <Fixture phase="Empty range"><Survey counts={[0, 0, 0, 0, 0]} /><Filters /><p role="status">Nothing is filed yet. Bring sources into range first.</p></Fixture> };
export const Charted: Story = { render: () => <Fixture phase="Charted"><Survey /><Filters /><Table /></Fixture> };
export const Filtered: Story = { render: () => <Fixture phase="Charted"><Survey counts={[0, 0, 5, 0, 0]} /><Filters tier="tier 3" investigation="inv-routing" /><Table /></Fixture> };
export const NeedsAttention: Story = { render: () => <Fixture phase="Needs attention"><Survey counts={[0, 0, 0, 0, 0]} /><Filters /><p role="alert" className="text-emperor">The archive could not be charted. Try again.</p></Fixture> };
export const ProductionRaster: Story = { parameters: { lostpixel: { disable: true } }, render: () => <Fixture phase="Charted" production><Survey /><Filters /><Table /></Fixture> };
