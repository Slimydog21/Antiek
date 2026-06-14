import { useEffect, useState } from "react";
import type { Meta, StoryObj } from "@storybook/react";

import { KreaArtLayer } from "./KreaArtLayer";
import type { SceneArt } from "../useSceneArt";

/**
 * KreaArtLayer.stories — the LIVE-art crossfade machine, co-located + state-driven
 * (ALC SPR-09, product-character capstone polish — the last un-storied STATEFUL
 * scene component, paired with SceneStatusBadge).
 *
 * KreaArtLayer is the one scene layer with INTERNAL STATE: it drives
 * `useReducer(crossfadeReduce)` (crossfadeMachine.ts) over two PERSISTENT slots
 * (A/B) from the `art` it is handed, easing each slot's opacity TARGET via a CSS
 * `transition: opacity`. It paints the live Krea sky ABOVE ProceduralSky and,
 * crucially, renders NOTHING visual in fallback (the seamless degradation path).
 * The 6 visual scene layers are pure props; THIS one has a state machine, so it
 * earns named co-located stories — the rubric's Dimension-3 L3 criterion.
 *
 * NO LIVE KREA (INV-2, honoured). These stories never call /krea/scene and never
 * touch the network: each story hands the component a fully-formed `SceneArt`
 * fixture (the same data-URI 1×1 PNGs the e2e fixture path uses), so the REAL
 * `crossfadeReduce` runs over the REAL props. We do NOT fake the rendered markup
 * — the slots on screen are the slots the machine actually computes.
 *
 * DETERMINISTIC. `frozen` (reduced-motion) is forced on every story, so the
 * transition collapses to the near-instant `CROSSFADE.reducedMs` dissolve — no
 * live clock, no rAF, no RNG in the render. `MidCrossfade` drives the real
 * machine through a fixed two-URL sequence (art A → art B) once on mount, which
 * is exactly how the crossfade test exercises a swap; both slots end up
 * populated with their genuine machine-computed opacity targets.
 *
 * RENDER SHAPE: BLOCK-bodied render arrows only (the SPR-08 build-storybook
 * csf-indexer escape lesson). The wrapper sizes the `absolute inset-0` layer.
 */

// Two tiny, distinct, instantly-loadable data-URI images (warm vs cool 1×1 PNG)
// — different bytes ⇒ different image_url ⇒ a genuine crossfade swap. These are
// the SAME fixtures the scene-living e2e uses (e2e/scene-living.spec.ts:59-63);
// reused here so the story art is byte-stable and never hits the network.
const FIXTURE_ART = {
  warm: "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==",
  cool: "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==",
} as const;

/** A LIVE SceneArt fixture (status "ready", not fallback) painting `url`. */
function liveArt(url: string, fadeKey: number): SceneArt {
  return {
    imageUrl: url,
    prevImageUrl: null,
    fadeKey,
    isFallback: false,
    status: "ready",
    reason: null,
  };
}

/** A FALLBACK SceneArt fixture (no live art at all — procedural-only). */
function fallbackArt(reason: string | null): SceneArt {
  return {
    imageUrl: null,
    prevImageUrl: null,
    fadeKey: 0,
    isFallback: true,
    status: "fallback",
    reason,
  };
}

const meta = {
  title: "Scene / Layers / KreaArtLayer",
  parameters: { layout: "fullscreen" },
  tags: ["autodocs"],
} satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

/** A stage that sizes the `absolute inset-0` layer over a dark wash, with a
 *  caption naming the inspected state. */
const KreaStage = ({ label, art }: { label: string; art: SceneArt }) => {
  return (
    <div className="bg-ink p-6">
      <div className="mb-2 font-mono text-xs uppercase tracking-wider text-starlight">
        KreaArtLayer · {label} · reducedMotion-frozen (deterministic)
      </div>
      {/* A mid-tone wash so the (tiny, stretched) fixture art reads; the layer
          is the full-bleed `absolute inset-0` element the machine paints into. */}
      <div className="relative aspect-video w-full overflow-hidden rounded-hog bg-shadow-1 dark:bg-space-2">
        <KreaArtLayer art={art} frozen />
      </div>
    </div>
  );
};

/**
 * A stage that drives the REAL crossfade machine through a fixed two-URL sequence
 * (art A → art B) once on mount, so BOTH persistent slots end up populated and
 * the machine is in its mid-crossfade two-slot state (front easing to painted,
 * back easing to 0). No live clock / RNG — the swap is a single deterministic
 * state flip in an effect, the same lever crossfade.test.tsx uses (rerender with
 * a new image_url). `frozen` collapses the eases to the near-instant dissolve.
 */
const CrossfadeStage = ({ label }: { label: string }) => {
  // Start on the warm art; flip to the cool art once, on mount. The REAL
  // useCrossfade reducer sees two distinct live URLs → assigns each to a slot.
  const [url, setUrl] = useState<string>(FIXTURE_ART.warm);
  const [fadeKey, setFadeKey] = useState<number>(1);
  useEffect(() => {
    setUrl(FIXTURE_ART.cool);
    setFadeKey(2);
  }, []);
  return <KreaStage label={label} art={liveArt(url, fadeKey)} />;
};

/** Art present in the FRONT slot — a single live URL handed to the layer; the
 *  machine puts it on a persistent slot at the painted-opacity target. The
 *  "live art is showing" state (data-krea="live", one painted slot). */
export const LiveArtFront: Story = {
  render: () => {
    return <KreaStage label="live art in front slot" art={liveArt(FIXTURE_ART.warm, 1)} />;
  },
};

/** Both slots populated / crossfading — the REAL crossfadeReduce driven through a
 *  warm→cool swap on mount, so slot A eases out (target 0) while slot B eases in
 *  (target painted). The interruptible two-slot transition mid-flight. */
export const MidCrossfade: Story = {
  render: () => {
    return <CrossfadeStage label="mid-crossfade (both slots populated)" />;
  },
};

/** No live art (fallback) — the layer renders NOTHING visual (data-krea=
 *  "fallback", no painted slots); ProceduralSky shows through untouched. The
 *  seamless degradation path the product serves to every keyless user. */
export const FallbackRendersNothing: Story = {
  render: () => {
    return <KreaStage label="fallback — renders nothing" art={fallbackArt("no_api_balance")} />;
  },
};
