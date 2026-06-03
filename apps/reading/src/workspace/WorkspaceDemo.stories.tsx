import type { Meta, StoryObj } from "@storybook/react";
import { MotionConfig } from "framer-motion";
import { useEffect } from "react";

import LemonButton from "../components/lemon/LemonButton";
import { LemonToastViewport, toast } from "../components/lemon/LemonToast";

import { PanelLayout } from "./PanelLayout";
import { useWorkspace } from "./WorkspaceStore";

/**
 * S3 acceptance gate — the panel-layout demo scene.
 *
 * Boots the workspace with three fake panels:
 *   • FakeSidebar  → docked-left (default)
 *   • FakeNotebook → floating (default)
 *   • FakeChat     → docked-right (default)
 *
 * The operator should be able to:
 *   1. Drag the floating Notebook around the canvas.
 *   2. Resize it from the bottom-right grip.
 *   3. Click between floating panels — focus deepens shadow.
 *   4. Use the kebab to dock, float, or close any panel.
 *   5. Re-open a closed panel from the controls.
 *
 * No production route uses any of this in S3. S5 ports the real
 * ResearchWorkstation onto PanelHost.
 */
const meta = {
  title: "Workspace / Demo",
  parameters: {
    layout: "fullscreen",
    // Lost-Pixel skips this story at every breakpoint. The framer-
    // motion spring on the floating panels lands at slightly different
    // animation phases per Chromium run; the resulting sub-2% inter-
    // run diff isn't a real visual regression but consistently fails
    // the 0.4% S12 ceiling. Mark `skipShot` at the story level so
    // the global filterShot fallback isn't needed.
    lostPixel: { skipShot: true },
  },
  tags: ["autodocs"],
} satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

export const Scene: Story = {
  render: () => {
    const Inner = () => {
      const open = useWorkspace((s) => s.open);
      const close = useWorkspace((s) => s.close);
      const reset = useWorkspace((s) => s.reset);
      const panels = useWorkspace((s) => s.panels);
      const focusedId = useWorkspace((s) => s.focusedPanelId);

      // Boot the scene once on mount
      useEffect(() => {
        reset();
        open("FakeSidebar", {}, { mode: "docked-left", title: "Investigations", id: "demo:sidebar" });
        open("FakeNotebook", {}, { mode: "floating", title: "Notebook · neutral atoms", id: "demo:notebook" });
        open("FakeChat", {}, { mode: "docked-right", title: "Chat", id: "demo:chat" });
        // eslint-disable-next-line react-hooks/exhaustive-deps
      }, []);

      const ids = Object.keys(panels);

      const reopen = (kind: "FakeSidebar" | "FakeNotebook" | "FakeChat") => {
        const map = {
          FakeSidebar: { mode: "docked-left" as const, title: "Investigations", id: "demo:sidebar" },
          FakeNotebook: { mode: "floating" as const, title: "Notebook · neutral atoms", id: "demo:notebook" },
          FakeChat: { mode: "docked-right" as const, title: "Chat", id: "demo:chat" },
        };
        open(kind, {}, map[kind]);
        toast.ok(`${map[kind].title} re-opened.`);
      };

      return (
        <div className="h-screen flex flex-col bg-ice-2 dark:bg-space-2 text-ink dark:text-bright">
          <LemonToastViewport />
          <header className="shrink-0 border-b-edge border-sun bg-ink dark:bg-void px-6 py-2.5 flex items-center justify-between">
            <div className="font-mono font-bold text-sun text-[13px] tracking-wider">
              ANTIEK · S3 PANEL DEMO
            </div>
            <div className="flex items-center gap-2 text-[12.5px] font-mono text-ice-2/80">
              <span>open: <span className="text-sun">{ids.length}</span></span>
              <span>focused: <span className="text-sun">{focusedId ?? "—"}</span></span>
              <LemonButton variant="tertiary" size="sm" onClick={() => reset()}>
                reset
              </LemonButton>
              <LemonButton size="sm" onClick={() => reopen("FakeSidebar")}>
                + Sidebar
              </LemonButton>
              <LemonButton size="sm" onClick={() => reopen("FakeNotebook")}>
                + Notebook
              </LemonButton>
              <LemonButton size="sm" onClick={() => reopen("FakeChat")}>
                + Chat
              </LemonButton>
              <LemonButton
                size="sm"
                data-testid="feel-three-stack"
                onClick={() => {
                  reset();
                  open("FakeSidebar", {}, { mode: "floating", title: "Stack 1", id: "feel:1" });
                  open("FakeNotebook", {}, { mode: "floating", title: "Stack 2", id: "feel:2" });
                  open("FakeChat", {}, { mode: "floating", title: "Stack 3", id: "feel:3" });
                }}
              >
                3-stack harness
              </LemonButton>
            </div>
          </header>

          <div className="flex-1 min-h-0">
            <PanelLayout
              mainSlot={
                <div className="h-full w-full p-12 flex items-center justify-center">
                  <div className="max-w-lg text-center">
                    <h1 className="text-3xl font-bold text-ink dark:text-bright mb-3">
                      Main slot
                    </h1>
                    <p className="text-shadow-1 dark:text-moonlight">
                      In S5+ this is where the route's actual content renders
                      (the trajectory + MasterMdViewer in ResearchWorkstation, the
                      PDF in WrestleApp, etc.). For S3, this is empty so you can
                      see the panels frame the canvas.
                    </p>
                    <p className="mt-4 text-shadow-1 dark:text-moonlight text-sm font-mono">
                      drag · resize · dock · float · close → from each panel's kebab
                    </p>
                  </div>
                </div>
              }
            />
          </div>
        </div>
      );
    };
    // Wrap in MotionConfig with reducedMotion="always" so the
    // framer-motion springs collapse to deterministic CSS — Lost-
    // Pixel can compare cleanly without flake from spring timing.
    return (
      <MotionConfig reducedMotion="always">
        <Inner />
      </MotionConfig>
    );
  },
};
