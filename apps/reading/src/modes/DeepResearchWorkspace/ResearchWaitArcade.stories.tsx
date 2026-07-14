import type { Meta, StoryObj } from "@storybook/react";
import { createRef, useEffect, useRef, type ComponentProps } from "react";
import { MemoryRouter } from "react-router-dom";

import { WernerIceCursorShell } from "../../werner/WernerIceCursorShell";
import { useStationInstrumentSuspended } from "../../werner/stationInstrumentSuspension";
import ResearchWaitArcade from "./ResearchWaitArcade";

const meta = {
  title: "DeepResearch / Research wait arcade",
  component: ResearchWaitArcade,
  parameters: { layout: "padded", router: false },
  args: {
    episodeId: "storybook:1",
    activeResearchCount: 3,
    offerAfterMs: 0,
    returnFocusRef: createRef<HTMLElement>(),
  },
} satisfies Meta<typeof ResearchWaitArcade>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Offer: Story = {
  render: (args) => <CursorPolicyPreview {...args} />,
};

export const Playing: Story = {
  render: (args) => <CursorPolicyPreview {...args} playing />,
  parameters: {
    lostpixel: { waitForSelector: '[data-backdrop-ready="true"]' },
  },
};

/** Story-only proof harness; production receives no preview bypass. */
function CursorPolicyPreview({
  playing = false,
  ...props
}: ComponentProps<typeof ResearchWaitArcade> & { playing?: boolean }) {
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let frame = 0;
    const activate = () => {
      window.dispatchEvent(
        new PointerEvent("pointermove", { clientX: 160, clientY: 92 }),
      );
      if (!playing) return;
      const play = rootRef.current?.querySelector<HTMLButtonElement>("button");
      if (play) play.click();
      else frame = window.requestAnimationFrame(activate);
    };
    frame = window.requestAnimationFrame(activate);
    return () => window.cancelAnimationFrame(frame);
  }, [playing]);

  return (
    <MemoryRouter initialEntries={["/brainstorm"]}>
      <div
        ref={rootRef}
        className="relative min-h-screen bg-ice-2 p-6 text-ink dark:bg-space-2 dark:text-bright"
      >
        <CursorPolicyStatus />
        <ResearchWaitArcade {...props} />
        <WernerIceCursorShell />
      </div>
    </MemoryRouter>
  );
}

function CursorPolicyStatus() {
  const suspended = useStationInstrumentSuspended();
  return (
    <p className="mb-4 font-mono text-[11px] uppercase tracking-wide text-shadow-1 dark:text-moonlight">
      Cursor owner · {suspended ? "game control — native canvas" : "research lens — route"}
    </p>
  );
}
