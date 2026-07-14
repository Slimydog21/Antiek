import type { Meta, StoryObj } from "@storybook/react";
import { MemoryRouter } from "react-router-dom";

import SceneChrome from "../SceneChrome";
import { SpeakListeningRoomAtmosphere } from "./SpeakListeningRoomAtmosphere";

const meta = {
  title: "Shell / Speak listening-room atmosphere (SPR-27)",
  component: SpeakListeningRoomAtmosphere,
  parameters: { layout: "fullscreen" },
  tags: ["autodocs", "a11y-audit"],
} satisfies Meta<typeof SpeakListeningRoomAtmosphere>;

export default meta;
type Story = StoryObj<typeof meta>;

export const HtmlAuthorityPlate: Story = {
  render: () => (
    <main className="relative h-screen overflow-hidden bg-space-2 text-ink">
      <SpeakListeningRoomAtmosphere />
      <section className="relative z-10 mx-auto flex h-full max-w-5xl items-center px-8">
        <article className="max-w-xl rounded-hog-lg border border-glass bg-glass p-8 shadow-z2 backdrop-blur-glass">
          <p className="font-mono text-xs uppercase tracking-widest text-shadow-1">Speak workspace · environment proof</p>
          <h1 className="mt-3 font-serif text-3xl leading-tight">The room listens. The remembrance is real HTML.</h1>
          <p className="mt-4 font-serif text-lg leading-8 text-ink-soft">Werner, portraits, transcripts, microphones, recording controls, consent, and state are absent from the bitmap.</p>
          <button type="button" className="mt-6 rounded bg-sun px-4 py-2 text-sm text-ink">Begin remembrance</button>
        </article>
      </section>
    </main>
  ),
};

export const SceneChromeIntegration: Story = {
  parameters: { router: false },
  render: () => (
    <MemoryRouter initialEntries={["/speak"]}>
      <main className="h-screen bg-space-2 text-ink">
        <SceneChrome>
          <section className="flex h-full items-center justify-center p-8">
            <article className="max-w-xl rounded-hog-lg border border-glass bg-glass p-8 shadow-z2">
              <p className="font-mono text-xs uppercase tracking-widest text-shadow-1">Live SceneChrome integration</p>
              <h1 className="mt-3 font-serif text-3xl leading-tight">Gather the voices that remember them.</h1>
              <p className="mt-4 font-serif text-lg leading-8 text-ink-soft">Capture, consent, transcription, focus order, and actions stay real HTML. The empty listening room remains behind them.</p>
              <button type="button" className="mt-6 rounded bg-sun px-4 py-2 text-sm text-ink">Begin remembrance</button>
            </article>
          </section>
        </SceneChrome>
      </main>
    </MemoryRouter>
  ),
};
