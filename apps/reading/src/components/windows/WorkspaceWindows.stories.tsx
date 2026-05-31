import type { Meta, StoryObj } from "@storybook/react";
import { useEffect } from "react";

import LemonButton from "../lemon/LemonButton";
import type { AdFillView } from "../../modes/Reading/AdBorder";
import { useWindows } from "../../workspace/windowsStore";
import { WindowsLayer } from "./WindowsLayer";
import { WorkspaceWindow } from "./WorkspaceWindow";

/**
 * SPR-09 acceptance gate — transparent, ad-bordered workspace windows over the
 * scene. The pale gradient under the windows stands in for SPR-04's
 * mountainscape so the glass transparency reads.
 *
 * The operator should be able to:
 *   1. Drag a window by its title bar; resize from the bottom-right grip.
 *   2. Expand a window to full (opaque) and restore it to floating (glass).
 *   3. Open several windows ("multiple terminals") and click between them —
 *      the focused window gets live glass + a sun outline; unfocused windows
 *      drop the backdrop blur (perf) and dim slightly.
 *   4. See the Times-Square ad border: a paid edge shows "Sponsored", an
 *      unbought edge shows the house slot ("From the library") — never blank.
 */
const meta = {
  title: "Windows / WorkspaceWindows",
  parameters: {
    layout: "fullscreen",
    // framer-motion spring lands at slightly different phases per run; skip
    // the pixel shot like the sibling Workspace/Demo story.
    lostPixel: { skipShot: true },
  },
  tags: ["autodocs"],
} satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

const PAID_TOP: AdFillView = {
  kind: "ad",
  ad: {
    advertiserName: "Werner & Co.",
    creativeUrl: "https://placehold.co/64",
    landingUrl: "https://example.com",
  },
};
const HOUSE: AdFillView = {
  kind: "house",
  house: { documentId: "doc-2", title: "On the Shortness of Life", author: "Seneca" },
};

/** A faux scene so the glass windows have something to reveal. */
function FauxScene() {
  return (
    <div
      aria-hidden="true"
      className="absolute inset-0 bg-gradient-to-br from-ice-2 via-glacial-1 to-glacial-2 dark:from-space-2 dark:via-charcoal-2 dark:to-slate-1"
    />
  );
}

function Stage({ children }: { children: React.ReactNode }) {
  return (
    <div className="relative h-screen w-screen overflow-hidden bg-ice-2 dark:bg-space-2">
      <FauxScene />
      {children}
    </div>
  );
}

/** Two windows, each hosting a placeholder page, with ad borders. */
export const TwoWindows: Story = {
  render: () => {
    function Demo() {
      const reset = useWindows((s) => s.reset);
      const open = useWindows((s) => s.open);
      useEffect(() => {
        reset();
        open("library", {}, { id: "win:library", title: "Library", rect: { x: 120, y: 100 } });
        open("stats", {}, { id: "win:stats", title: "Substrate stats", rect: { x: 520, y: 240 } });
      }, [reset, open]);
      return (
        <Stage>
          <WorkspaceWindow
            id="win:library"
            adFills={{ top: PAID_TOP, bottom: HOUSE }}
          >
            <div className="p-8 text-ink dark:text-bright">
              <h1 className="font-serif text-2xl mb-2">Library</h1>
              <p className="text-sm text-shadow-1 dark:text-moonlight">
                A product page hosted inside a transparent window. The scene
                shows through the glass body; drag the title bar to move it.
              </p>
            </div>
          </WorkspaceWindow>
          <WorkspaceWindow id="win:stats" adFills={{ top: HOUSE, bottom: HOUSE }}>
            <div className="p-8 text-ink dark:text-bright">
              <h1 className="font-serif text-2xl mb-2">Substrate stats</h1>
              <p className="text-sm text-shadow-1 dark:text-moonlight">
                Click between windows to restack; expand one to full to see it
                go opaque (so the scene blur can pause behind it).
              </p>
            </div>
          </WorkspaceWindow>
        </Stage>
      );
    }
    return <Demo />;
  },
};

/** Live spawn — open windows via the store, like the launcher does. */
export const SpawnAndStack: Story = {
  render: () => {
    function Demo() {
      const reset = useWindows((s) => s.reset);
      const open = useWindows((s) => s.open);
      const order = useWindows((s) => s.order);
      useEffect(() => reset(), [reset]);
      return (
        <Stage>
          <div className="absolute top-3 left-3 z-[400] flex gap-2 pointer-events-auto">
            <LemonButton onClick={() => open("library", {}, { title: "Library" })}>
              Open a window
            </LemonButton>
            <span className="font-mono text-[12px] text-ink dark:text-bright self-center">
              {order.length} open (cap 8)
            </span>
          </div>
          <WindowsLayer />
        </Stage>
      );
    }
    return <Demo />;
  },
};
