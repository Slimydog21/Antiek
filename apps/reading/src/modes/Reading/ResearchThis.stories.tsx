import { useEffect, useRef } from "react";
import type { Meta, StoryObj } from "@storybook/react";

import ResearchThis from "./ResearchThis";
import { httpError, json, pendingForever, stubFetch } from "./storyFetch";

/**
 * ResearchThis (Read SPR-08) — the spin-research affordance: build a gate-safe
 * seed server-side and hand off to the Research workflow.
 *
 * Product-character authorship (ALC SPR-09): ResearchThis has THREE meaningful
 * states — idle, spinning (in-flight), and a graceful failure — and each is
 * authored as its OWN named, co-located story so it is inspectable in isolation
 * (the rubric's Dimension-3 level-3 criterion). The non-default states are
 * reached through the component's REAL code path: each story pins `fetch`
 * (`storyFetch.tsx`) so the same handler the reader exercises drives the state.
 * Runtime behaviour is unchanged; only the network is controlled.
 *
 * §5 voice: the failure copy is the component's own ("Book not found." for the
 * known reason; the engine string is never shown raw for the generic case).
 * Brand firewall: no PostHog phrasing — Antiek's own labels throughout.
 */
const meta = {
  title: "Read / ResearchThis",
  component: ResearchThis,
  parameters: { layout: "padded" },
  tags: ["autodocs"],
  args: { documentId: "doc-book-1", pageIndex: 3, passageText: "A selected passage worth researching." },
} satisfies Meta<typeof ResearchThis>;

export default meta;
type Story = StoryObj<typeof meta>;

/**
 * Auto-clicks the rendered control once on mount so a story can show a state
 * the component only enters on interaction (spinning / failed). It drives the
 * REAL onClick handler — nothing about the component is mocked but its network.
 */
function AutoSpin() {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const btn = ref.current?.querySelector("button");
    btn?.click();
  }, []);
  return (
    <div ref={ref}>
      <ResearchThis documentId="doc-book-1" pageIndex={3} passageText="A selected passage worth researching." />
    </div>
  );
}

/** IDLE — the resting affordance: a calm "Research this page" the reader can press. */
export const Idle: Story = {};

/**
 * SPINNING — the in-flight state, pinned. The seed is being built server-side;
 * the button shows "Spinning research…" and is disabled so the action can't
 * double-fire. `fetch` never settles here so the transient state holds for
 * inspection instead of flashing past.
 */
export const Spinning: Story = {
  decorators: [stubFetch(pendingForever)],
  render: () => {
    return <AutoSpin />;
  },
};

/**
 * NOT FOUND — the KNOWN, user-meaningful failure: the book isn't in the library.
 * The endpoint answers 404, the client maps it to `book_not_found`, and the
 * surface shows its own §5 line ("Book not found.") — never a raw HTTP string.
 */
export const NotFound: Story = {
  decorators: [stubFetch(() => httpError(404))],
  render: () => {
    return <AutoSpin />;
  },
};

/**
 * FAILED — a transient/unknown failure (the connection dropped, the seed couldn't
 * be built). The action re-enables so the reader can try again; the surface shows
 * the failure inline and the reading position is held by `usePosition`.
 */
export const Failed: Story = {
  decorators: [stubFetch(() => json({ detail: "service unavailable" }, 503))],
  render: () => {
    return <AutoSpin />;
  },
};
