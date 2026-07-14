import type { Meta, StoryObj } from "@storybook/react";
import { MemoryRouter } from "react-router-dom";

import SceneChrome from "../SceneChrome";
import { ResearchObservatoryAtmosphere } from "./ResearchObservatoryAtmosphere";

const meta = {
  title: "Shell / Research observatory atmosphere (SPR-25)",
  component: ResearchObservatoryAtmosphere,
  parameters: { layout: "fullscreen" },
  tags: ["autodocs", "a11y-audit"],
} satisfies Meta<typeof ResearchObservatoryAtmosphere>;

export default meta;
type Story = StoryObj<typeof meta>;

export const HtmlAuthorityPlate: Story = {
  render: () => (
    <main className="relative h-screen overflow-hidden bg-space-2 text-ink">
      <ResearchObservatoryAtmosphere />
      <section className="relative z-10 mx-auto flex h-full max-w-5xl items-center px-8">
        <article className="max-w-xl rounded-hog-lg border border-glass bg-glass p-8 shadow-z2 backdrop-blur-glass">
          <p className="font-mono text-xs uppercase tracking-widest text-shadow-1">
            Research workstation · environment proof
          </p>
          <h1 className="mt-3 font-serif text-3xl leading-tight">
            The mountain is atmosphere. This evidence is real HTML.
          </h1>
          <p className="mt-4 font-serif text-lg leading-8 text-ink-soft">
            Werner, documents, graphs, citations, and controls are deliberately
            absent from the bitmap. The product owns them as accessible,
            selectable, provenance-bearing interfaces.
          </p>
          <button type="button" className="mt-6 rounded bg-sun px-4 py-2 text-sm text-ink">
            Start research
          </button>
        </article>
      </section>
    </main>
  ),
};

export const SceneChromeIntegration: Story = {
  parameters: { router: false },
  render: () => (
    <MemoryRouter initialEntries={["/"]}>
      <main className="h-screen bg-space-2 text-ink">
        <SceneChrome>
          <section className="flex h-full items-center justify-center p-8">
            <article className="max-w-xl rounded-hog-lg border border-glass bg-glass p-8 shadow-z2">
              <p className="font-mono text-xs uppercase tracking-widest text-shadow-1">
                Live SceneChrome integration
              </p>
              <h1 className="mt-3 font-serif text-3xl leading-tight">
                Ask a question worth chasing.
              </h1>
              <p className="mt-4 font-serif text-lg leading-8 text-ink-soft">
                The route, action bar, tabs, focus order, and working surface
                remain real HTML. The observatory stays behind them.
              </p>
              <button type="button" className="mt-6 rounded bg-sun px-4 py-2 text-sm text-ink">
                Start research
              </button>
            </article>
          </section>
        </SceneChrome>
      </main>
    </MemoryRouter>
  ),
};
