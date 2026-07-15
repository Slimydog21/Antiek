import type { Meta, StoryObj } from "@storybook/react";

import LemonButton from "../../components/lemon/LemonButton";
import LemonTextarea from "../../components/lemon/LemonTextarea";
import AIActionFailure from "../../shared/AIActionFailure";
import Thinking from "../../shared/Thinking";
import { ResearchExpeditionDeskFrame, type ResearchExpeditionPhase } from "./StartResearch";

const meta = {
  title: "Research / Expedition Desk",
  parameters: { layout: "fullscreen", lostpixel: { waitBeforeScreenshot: 800 } },
  tags: ["autodocs", "a11y-audit"],
} satisfies Meta;
export default meta;
type Story = StoryObj<typeof meta>;

function Fixture({
  phase,
  children,
  production = false,
}: {
  phase: ResearchExpeditionPhase;
  children: React.ReactNode;
  production?: boolean;
}) {
  return (
    <main className="h-screen">
      <ResearchExpeditionDeskFrame phase={phase} visualFixture={!production}>
        {children}
      </ResearchExpeditionDeskFrame>
    </main>
  );
}

function Composer({ attached = false }: { attached?: boolean }) {
  return (
    <div className="research-expedition-desk__launch-card w-full max-w-3xl rounded-hog-lg border border-rule p-6 shadow-z1">
      <h2 className="mb-2 text-center font-serif text-2xl text-ink">What do you want to research?</h2>
      <p className="mb-6 text-center font-serif text-sm text-shadow-1">Interrogate one question now, or inspect its paths before launch.</p>
      <div className="flex flex-col gap-3">
        <LemonTextarea aria-label="Research question" value={attached ? "Which evidence would reverse this thesis?" : ""} readOnly minRows={3} />
        {attached && <p role="status" className="font-mono text-[11px] text-aurora">Added “market-map.md” to your corpus.</p>}
        <div className="flex flex-wrap items-center justify-between gap-3">
          <span className="font-mono text-[11px] text-shadow-1">Depth · Deep · reasoning-heavier</span>
          <div className="flex gap-2"><LemonButton variant="secondary">Break into sub-questions</LemonButton><LemonButton variant="primary">Ask</LemonButton></div>
        </div>
      </div>
    </div>
  );
}

export const Ready: Story = { render: () => <Fixture phase="Ready"><Composer /></Fixture> };

export const AttachmentReady: Story = { render: () => <Fixture phase="Ready"><Composer attached /></Fixture> };

export const Starting: Story = {
  render: () => (
    <Fixture phase="Under way">
      <section className="research-expedition-desk__state" role="status" aria-live="polite" aria-label="Research in progress">
        <div className="mb-4 flex justify-center"><Thinking size={48} label="The investigation is working" /></div>
        <p className="mb-1 font-serif text-base text-ink">Working on it…</p>
        <p className="font-mono text-xs text-shadow-1">12 events so far · $0.0342</p>
      </section>
    </Fixture>
  ),
};

export const Cascade: Story = {
  render: () => (
    <Fixture phase="Charting">
      <section className="research-expedition-desk__proposal" aria-label="Cascade proposal">
        <h2 className="mb-1 text-center font-serif text-2xl text-ink">Breaking this into sub-questions</h2>
        <p className="mb-5 text-center font-serif text-sm text-shadow-1">Which technical decisions explain the quality gap?</p>
        <ol className="space-y-2 font-serif text-sm text-ink">
          <li className="rounded-hog border border-rule bg-ice-0 p-3">1 · What evidence defines research quality?</li>
          <li className="rounded-hog border border-rule bg-ice-0 p-3">2 · Which architectures preserve source authority?</li>
          <li className="rounded-hog border border-rule bg-ice-0 p-3">3 · Where do current systems lose operator control?</li>
        </ol>
      </section>
    </Fixture>
  ),
};

export const Failure: Story = {
  render: () => (
    <Fixture phase="Needs attention">
      <div className="research-expedition-desk__launch-card w-full max-w-xl rounded-hog-lg border border-rule p-6 shadow-z1">
        <AIActionFailure title="The research could not start" onRetry={() => undefined} />
      </div>
    </Fixture>
  ),
};

export const ProductionRaster: Story = {
  parameters: { lostpixel: { disable: true } },
  render: () => <Fixture phase="Ready" production><Composer attached /></Fixture>,
};
