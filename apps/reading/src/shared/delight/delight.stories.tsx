import type { Meta, StoryObj } from "@storybook/react";

import LemonButton from "../../components/lemon/LemonButton";
import WernerThinking from "../../brand/werner/animated/WernerThinking";
import CelebrateBurst from "./CelebrateBurst";
import { useCelebrate } from "./useCelebrate";

/**
 * Stories — the inspection surface for U-05 M2/M5. "Feels alive but not
 * slow" is an operator visual judgment; these stories are where it's made.
 * Trigger the beat, confirm it's brief, fires once, and that the trigger
 * button stays clickable straight through it (non-blocking). Toggle the OS
 * reduce-motion setting to see the calm, instant baseline.
 */

const meta = {
  title: "Delight / Signature beats",
  parameters: { layout: "centered" },
} satisfies Meta;

export default meta;
type Story = StoryObj;

/** The bare primitive: Werner's one-shot celebrate, armed by a button. */
export const CelebratePrimitive: Story = {
  render: () => {
    const { celebrating, celebrate } = useCelebrate();
    return (
      <div className="flex flex-col items-center gap-4 p-10">
        <div className="relative flex h-20 w-20 items-center justify-center">
          {celebrating ? (
            <CelebrateBurst active size={72} />
          ) : (
            <span className="text-xs font-mono text-shadow-1 dark:text-moonlight">
              (idle)
            </span>
          )}
        </div>
        <LemonButton variant="primary" onClick={celebrate}>
          Fire the beat
        </LemonButton>
        <p className="max-w-xs text-center text-xs font-mono text-shadow-1 dark:text-moonlight">
          Fires once, retires on its own at the slow token (800 ms). Click
          again mid-beat — it restarts, never stacks.
        </p>
      </div>
    );
  },
};

/**
 * The one wired beat — research-starts. Simulates StartResearch's payoff:
 * the moment a research is under way, the celebrate beat plays over the
 * ongoing thinking mark. The button stays clickable through the beat,
 * standing in for "navigation/input is never gated."
 */
export const ResearchStarts: Story = {
  render: () => {
    const { celebrating, celebrate } = useCelebrate();
    return (
      <div className="flex flex-col items-center gap-5 p-10">
        <div
          className="relative flex h-16 w-16 items-center justify-center"
          role="status"
          aria-live="polite"
        >
          {celebrating && (
            <CelebrateBurst
              active
              size={48}
              className="absolute inset-0 items-center justify-center"
            />
          )}
          <WernerThinking size={48} label="The investigation is working" />
        </div>
        <p className="text-sm font-serif text-ink dark:text-bright">
          Starting your research…
        </p>
        <LemonButton variant="secondary" onClick={celebrate}>
          Start a research
        </LemonButton>
      </div>
    );
  },
};

/**
 * Filed, not built — the other three product payoffs reuse this exact
 * primitive at their own trigger. Their surfaces don't exist in this run,
 * so there's nothing to wire; this documents the adoption point (full
 * detail in src/design/motion/README.md).
 */
export const FiledBeats: Story = {
  render: () => (
    <div className="max-w-md p-8 text-sm font-serif text-ink dark:text-bright">
      <p className="mb-3 font-mono text-xs uppercase tracking-wider text-shadow-1 dark:text-moonlight">
        Filed beats (reuse this primitive)
      </p>
      <ul className="list-disc space-y-1.5 pl-5">
        <li>
          <strong>draft-generates</strong> (Write) — celebrate at the first
          token of a generated draft.
        </li>
        <li>
          <strong>biography-assembles</strong> (Speak) — celebrate when an
          assembled biography first renders.
        </li>
        <li>
          <strong>book-opens</strong> (Read) — celebrate on a freshly added
          book's first open.
        </li>
      </ul>
    </div>
  ),
};
