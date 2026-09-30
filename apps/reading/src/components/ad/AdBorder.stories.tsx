import type { Meta, StoryObj } from "@storybook/react";

import { AdBorder } from "./AdBorder";
import type { BorderPosition, FillResult } from "./adFillClient";

/**
 * AdBorder — the shell's one labelled house-ad slot (SPR-07; design wave 3).
 *
 * In the app it is mounted ONCE at the shell (AppShell → AdBorderMount) and
 * serves every lens. These stories isolate it on a mock working surface so the
 * slot, real-vs-house fill, and the reduced-motion behaviour are visible
 * without booting the shell. (It was a four-edge border until the design
 * spec §5 allowed one slot in one rail.)
 *
 * The 1 Hz attention sampler is disabled in every story (samplingEnabled=false)
 * so the stories are static render surfaces — the sampler is exercised by
 * useFrameAttention.test.ts, not Storybook.
 *
 * Reduced motion: the creatives carry NO animation by construction, so the
 * border is reduced-motion-safe regardless of the OS / a11y-addon setting.
 * Toggle prefers-reduced-motion to confirm nothing moves (AdBorder.test.tsx
 * pins the static-creative invariant mechanically).
 *
 * The slot is the same one row at every width; the Wide and Narrow stories
 * set the Storybook viewport to show it at both.
 */

const HOUSE: (opts: { positions: BorderPosition[] }) => Promise<FillResult> = async ({
  positions,
}) => ({
  fills: positions.map((position) => ({
    position,
    kind: "house",
    house: { promoted_document_id: "doc-99", title: "The Order of Time", author: "Carlo Rovelli" },
    revenue_usd_cents: 0,
  })),
  served: false,
});

const NEUTRAL_HOUSE: (opts: { positions: BorderPosition[] }) => Promise<FillResult> = async ({
  positions,
}) => ({
  fills: positions.map((position) => ({ position, kind: "house", house: null, revenue_usd_cents: 0 })),
  served: false,
});

type FillFn = (opts: { positions: BorderPosition[] }) => Promise<FillResult>;

const AD: FillFn = async ({ positions }) => ({
  fills: positions.map((position) => ({
    position,
    kind: "ad",
    ad: {
      inventory_id: "inv-1",
      advertiser_display_name: "Vertical SaaS Inc.",
      creative_url: "https://example.com/c.png",
      landing_url: "https://example.com/?ref=antiek",
    },
    revenue_usd_cents: 120,
  })),
  served: true,
});

const ALL_POSITIONS: BorderPosition[] = ["top", "bottom", "left", "right"];

/** The same fill its story's fetcher resolves to, synchronously. Lost-pixel
 *  captures on the first stable frame, so the rails must paint on FIRST
 *  render; waiting for the fetch effect leaves a blank-rail window and flakes
 *  the CI screenshot (seen on SpeakHouseFill w768: side rails missing). */
function firstPaintFill(fetcher: FillFn): FillResult {
  if (fetcher === NEUTRAL_HOUSE) {
    return {
      fills: ALL_POSITIONS.map((position) => ({ position, kind: "house", house: null, revenue_usd_cents: 0 })),
      served: false,
    };
  }
  if (fetcher === AD) {
    return {
      fills: ALL_POSITIONS.map((position) => ({
        position,
        kind: "ad",
        ad: {
          inventory_id: "inv-1",
          advertiser_display_name: "Vertical SaaS Inc.",
          creative_url: "https://example.com/c.png",
          landing_url: "https://example.com/?ref=antiek",
        },
        revenue_usd_cents: 120,
      })),
      served: true,
    };
  }
  return {
    fills: ALL_POSITIONS.map((position) => ({
      position,
      kind: "house",
      house: { promoted_document_id: "doc-99", title: "The Order of Time", author: "Carlo Rovelli" },
      revenue_usd_cents: 0,
    })),
    served: false,
  };
}

/** A stand-in working surface the border wraps, so the reserved-inset band is
 *  legible against real content (the border sets the seam vars; this surface
 *  reads them as padding the way AppShell's frame does). */
function MockWorkingRegion() {
  return (
    <div
      data-akb-shell-frame
      className="h-screen w-screen bg-ice-2 dark:bg-space-2 text-ink dark:text-bright"
      style={{
        paddingTop: "var(--akb-border-inset-top)",
        paddingRight: "var(--akb-border-inset-right)",
        paddingBottom: "var(--akb-border-inset-bottom)",
        paddingLeft: "var(--akb-border-inset-left)",
        boxSizing: "border-box",
      }}
    >
      <div className="h-full w-full flex items-center justify-center font-serif text-shadow-1 dark:text-moonlight">
        Working region — the border wraps this, never over it.
      </div>
    </div>
  );
}

const meta = {
  title: "Ad / AdBorder",
  component: AdBorder,
  parameters: { layout: "fullscreen" },
  args: { samplingEnabled: false, windowId: "win:story" },
} satisfies Meta<typeof AdBorder>;

export default meta;
type Story = StoryObj<typeof meta>;

function withSurface(args: Parameters<typeof AdBorder>[0]) {
  const initialFill = args.fillFetcher ? firstPaintFill(args.fillFetcher) : undefined;
  return (
    <>
      <MockWorkingRegion />
      <AdBorder {...args} initialFill={initialFill} />
    </>
  );
}

/** Read lens, wide viewport, house fill (the default zero-buyer path). */
export const ReadHouseFill: Story = {
  args: { lens: "read", fillFetcher: HOUSE },
  render: (args) => withSurface(args),
};

/** Research lens, house fill. */
export const ResearchHouseFill: Story = {
  args: { lens: "research", fillFetcher: HOUSE },
  render: (args) => withSurface(args),
};

/** Write lens, house fill. */
export const WriteHouseFill: Story = {
  args: { lens: "write", fillFetcher: HOUSE },
  render: (args) => withSurface(args),
};

/** Speak lens, house fill. */
export const SpeakHouseFill: Story = {
  args: { lens: "speak", fillFetcher: HOUSE },
  render: (args) => withSurface(args),
};

/** A matched advertiser creative (Sponsored). */
export const RealAdFill: Story = {
  args: { lens: "read", fillFetcher: AD },
  render: (args) => withSurface(args),
};

/** The neutral house card (nothing to promote → the library on-ramp). */
export const NeutralHouseCard: Story = {
  args: { lens: "read", fillFetcher: NEUTRAL_HOUSE },
  render: (args) => withSurface(args),
};

/** Wide viewport — one slot, on the top edge. */
export const Wide: Story = {
  args: { lens: "read", fillFetcher: HOUSE },
  parameters: { viewport: { defaultViewport: "responsive" } },
  globals: { viewport: { value: undefined } },
  render: (args) => withSurface(args),
};

/** Narrow viewport — the same one slot; the link truncates, never clips. */
export const Narrow: Story = {
  args: { lens: "read", fillFetcher: HOUSE },
  parameters: { viewport: { defaultViewport: "mobile2" } },
  globals: { viewport: { value: "mobile2" } },
  render: (args) => withSurface(args),
};
