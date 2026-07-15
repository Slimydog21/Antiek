import type { Meta, StoryObj } from "@storybook/react";
import { useEffect, type ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { expect, userEvent, waitFor, within } from "@storybook/test";

import SceneChrome from "../SceneChrome";
import { BrainstormFjordAtmosphere } from "./BrainstormFjordAtmosphere";
import BrainstormStation from "../../modes/BrainstormStation";

const nativeFetch = globalThis.fetch;

/** Install the empty watch-list response before BrainstormStation's effects run.
 * This keeps the story on the production route/component path while making its
 * network boundary deterministic for a11y and visual CI. */
function EmptyWatchListBoundary({ children }: { children: ReactNode }) {
  globalThis.fetch = async (input, init) => {
    const url = String(input);
    if (url.includes("/watch-for-later")) {
      return new Response(JSON.stringify({ count: 0, questions: [] }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }
    return nativeFetch(input, init);
  };

  useEffect(() => () => {
    globalThis.fetch = nativeFetch;
  }, []);

  return children;
}

const meta = {
  title: "Shell / Brainstorm fjord atmosphere (SPR-38)",
  component: BrainstormFjordAtmosphere,
  parameters: { layout: "fullscreen" },
  tags: ["autodocs", "a11y-audit"],
} satisfies Meta<typeof BrainstormFjordAtmosphere>;

export default meta;
type Story = StoryObj<typeof meta>;

async function waitForFjordImage(canvasElement: HTMLElement) {
  await waitFor(() => {
    expect(
      canvasElement.querySelector(
        '[data-brainstorm-fjord-image-ready="true"]',
      ),
    ).toBeTruthy();
  });
  // backdrop-filter composites one frame after the image load event.
  await new Promise((resolve) => window.setTimeout(resolve, 300));
}

export const HtmlAuthorityPlate: Story = {
  render: () => (
    <main className="relative h-screen overflow-hidden bg-ice-2 text-ink">
      <BrainstormFjordAtmosphere />
      <section className="relative z-10 mx-auto flex h-full max-w-5xl items-center px-8">
        <article className="max-w-xl rounded-hog-lg border border-glass bg-glass p-8 shadow-z2 backdrop-blur-glass">
          <p className="font-mono text-xs uppercase tracking-widest text-shadow-1">
            Brainstorm · idea coast
          </p>
          <h1 className="mt-3 font-serif text-3xl leading-tight">
            Give the unfinished thought somewhere to land.
          </h1>
          <p className="mt-4 font-serif text-lg leading-8 text-ink-soft">
            The fjord is atmosphere. Questions, selections, agents, and drafts
            remain accessible, selectable HTML above it.
          </p>
          <button type="button" className="mt-6 rounded bg-sun px-4 py-2 text-sm text-ink">
            Begin brainstorming
          </button>
        </article>
      </section>
    </main>
  ),
  play: async ({ canvasElement }) => waitForFjordImage(canvasElement),
};

export const FjordSkipOffer: Story = {
  parameters: { router: false },
  render: () => (
    <MemoryRouter initialEntries={["/brainstorm"]}>
      <EmptyWatchListBoundary>
        <main className="h-screen bg-ice-2 text-ink">
          <SceneChrome>
            <BrainstormStation />
          </SceneChrome>
        </main>
      </EmptyWatchListBoundary>
    </MemoryRouter>
  ),
  play: async ({ canvasElement }) => {
    await waitFor(() => {
      expect(
        within(canvasElement).getByRole("button", { name: "Play Fjord Skip" }),
      ).toBeTruthy();
    });
    await waitForFjordImage(canvasElement);
  },
};

export const FjordSkipPlaying: Story = {
  ...FjordSkipOffer,
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await waitFor(() => {
      expect(canvas.getByRole("button", { name: "Play Fjord Skip" })).toBeTruthy();
    });
    await userEvent.click(
      canvas.getByRole("button", { name: "Play Fjord Skip" }),
    );
    await waitFor(() => {
      expect(
        canvasElement.querySelector('[data-backdrop-ready="true"]'),
      ).toBeTruthy();
    });
    await waitForFjordImage(canvasElement);
  },
};
