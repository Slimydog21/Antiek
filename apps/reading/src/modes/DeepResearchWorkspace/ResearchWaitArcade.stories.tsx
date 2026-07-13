import type { Meta, StoryObj } from "@storybook/react";
import { createRef, useEffect, useRef, type ComponentProps } from "react";

import ResearchWaitArcade from "./ResearchWaitArcade";

const meta = {
  title: "DeepResearch / Research wait arcade",
  component: ResearchWaitArcade,
  parameters: { layout: "padded" },
  args: {
    episodeId: "storybook:1",
    activeResearchCount: 3,
    offerAfterMs: 0,
    returnFocusRef: createRef<HTMLElement>(),
  },
} satisfies Meta<typeof ResearchWaitArcade>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Offer: Story = {};

export const Playing: Story = {
  render: (args) => <PlayingPreview {...args} />,
};

/** Story-only explicit activation; production receives no preview bypass. */
function PlayingPreview(props: ComponentProps<typeof ResearchWaitArcade>) {
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let frame = 0;
    const activate = () => {
      const play = rootRef.current?.querySelector<HTMLButtonElement>("button");
      if (play) play.click();
      else frame = window.requestAnimationFrame(activate);
    };
    frame = window.requestAnimationFrame(activate);
    return () => window.cancelAnimationFrame(frame);
  }, []);

  return (
    <div ref={rootRef}>
      <ResearchWaitArcade {...props} />
    </div>
  );
}
