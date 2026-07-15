import type { Meta, StoryObj } from "@storybook/react";

import LemonCard from "../../components/lemon/LemonCard";
import { SourceIntakeFieldStationFrame } from "./index";

const meta = {
  title: "Sources / Source Intake Field Station",
  parameters: { layout: "fullscreen", lostpixel: { waitBeforeScreenshot: 500 } },
  tags: ["autodocs", "a11y-audit"],
} satisfies Meta;
export default meta;
type Story = StoryObj<typeof meta>;

function Console({ detected = false }: { detected?: boolean }) {
  return (
    <form className="source-intake-station__form w-full rounded-lg border border-rule p-5 space-y-4">
      <label className="block text-xs font-medium text-ink">URLs (one per line)
        <textarea aria-label="Source URLs" readOnly value={detected ? "https://arxiv.org/abs/2402.03300" : ""} rows={4} className="mt-2 w-full rounded border border-rule p-3 font-mono text-sm" />
      </label>
      {detected && <p className="font-mono text-xs text-shadow-1">Detected: arxiv</p>}
      <div className="source-intake-station__settings grid grid-cols-3 gap-3">
        <label className="text-xs">Kind<select aria-label="Source kind" className="mt-1 w-full rounded border border-rule p-2"><option>Auto-detect</option></select></label>
        <label className="text-xs">Investigation id<input aria-label="Investigation id" readOnly value="__operator__" className="mt-1 w-full rounded border border-rule p-2 font-mono" /></label>
        <label className="text-xs">Max episodes<input aria-label="Maximum podcast episodes" readOnly value="10" className="mt-1 w-full rounded border border-rule p-2" /></label>
      </div>
      <div className="flex justify-end"><button type="button" className="rounded bg-ink px-4 py-2 text-sm text-white">Ingest</button></div>
    </form>
  );
}

function Manifest({ mixed = false }: { mixed?: boolean }) {
  return (
    <section className="source-intake-station__manifest" aria-label="Recent ingests">
      <h2 className="mb-3 font-serif text-base">Recent ingests</h2>
      <div className="space-y-2">
        <LemonCard className="p-3"><strong className="font-mono text-xs">ingested · arxiv</strong><p className="mt-1 font-serif">Attention Is All You Need</p><small>42 chunks</small></LemonCard>
        {mixed && <LemonCard className="p-3"><strong className="font-mono text-xs text-emperor">error</strong><p className="mt-1 font-mono text-sm">https://example.com/field-note</p><small>This source could not be received. Check the address and try again.</small></LemonCard>}
      </div>
    </section>
  );
}

function Fixture({ phase, children, production = false }: { phase: "Ready" | "Receiving" | "Filed" | "Needs attention"; children: React.ReactNode; production?: boolean }) {
  return <main className="h-screen"><SourceIntakeFieldStationFrame phase={phase} visualFixture={!production}><div className="source-intake-station__workspace">{children}</div></SourceIntakeFieldStationFrame></main>;
}

export const Idle: Story = { render: () => <Fixture phase="Ready"><Console /></Fixture> };
export const DetectedInput: Story = { render: () => <Fixture phase="Ready"><Console detected /></Fixture> };
export const Receiving: Story = { render: () => <Fixture phase="Receiving"><Console detected /><p role="status" className="mt-4 text-center font-mono text-xs">Receiving sources in order…</p></Fixture> };
export const Filed: Story = { render: () => <Fixture phase="Filed"><Console /><Manifest /></Fixture> };
export const MixedResult: Story = { render: () => <Fixture phase="Needs attention"><Console /><Manifest mixed /></Fixture> };
export const ProductionRaster: Story = { parameters: { lostpixel: { disable: true } }, render: () => <Fixture phase="Ready" production><Console detected /></Fixture> };
