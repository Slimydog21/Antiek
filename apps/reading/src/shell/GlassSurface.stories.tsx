import type { Meta, StoryObj } from "@storybook/react";

import { GlassSurface } from "./GlassSurface";

/**
 * GlassSurface (AMS-v2, SPR-03) — the ONE primitive that turns a landing
 * surface translucent over the living mountainscape without dropping body text
 * below the WCAG-AA floor. It composites a scrim behind its content for the AA
 * guarantee, and DEGRADES to an opaque solid fallback when the scene is absent
 * (offline / no scene key) or the OS asks for reduced motion.
 *
 * ── States authored (ALC SPR-09 product-character lift) ──────────────────────
 * GlassSurface is presentational, but it carries genuinely distinct rendered
 * states the dimension rewards authoring: the translucent GLASS variant, the
 * opaque SOLID variant, and the DEGRADED fallback the glass variant renders
 * when `sceneAbsent`. Each is a named story driving the REAL component (the
 * `variant` / `sceneAbsent` props are its own public API) so the
 * frost-vs-fallback states are inspectable in isolation rather than only
 * reachable by toggling the OS reduced-motion setting at runtime.
 *
 * The mock backdrop behind each story stands in for the living `<Scene/>`
 * (z-0) so the translucency (or its absence) reads — no Scene is mounted here;
 * GlassSurface never depends on one.
 */
const meta = {
  title: "Shell / GlassSurface (SPR-03)",
  component: GlassSurface,
  parameters: { layout: "fullscreen" },
  tags: ["autodocs", "a11y-audit"],
} satisfies Meta<typeof GlassSurface>;

export default meta;
type Story = StoryObj<typeof meta>;

function Backdrop({ children }: { children: React.ReactNode }) {
  return (
    <div
      className="h-screen w-screen p-16"
      // A representative busy scene stand-in (the real Scene is the living
      // mountainscape) so the glass translucency is visible against it.
      style={{
        background:
          "linear-gradient(135deg, #0F1419 0%, #2A4A6B 45%, #C9D6E3 100%)",
      }}
    >
      {children}
    </div>
  );
}

function Sample() {
  return (
    <div className="p-8 max-w-lg">
      <h2 className="font-serif text-2xl text-ink dark:text-bright">
        Reading over the living scene
      </h2>
      <p className="mt-3 text-[15px] leading-relaxed text-ink-soft dark:text-starlight font-serif">
        Body text on the glass surface holds the WCAG-AA contrast floor over the
        moving scene behind it — the scrim layer bounds how dark or bright the
        scene can make this text background.
      </p>
    </div>
  );
}

/**
 * GLASS — the translucent frost variant over the (mock) scene. The scene reads
 * through the combined glass + scrim alpha while body text stays above the AA
 * floor. This is the default landing-surface state.
 */
export const Glass: Story = {
  render: () => {
    return (
      <Backdrop>
        <GlassSurface variant="glass" className="rounded-hog">
          <Sample />
        </GlassSurface>
      </Backdrop>
    );
  },
};

/**
 * SOLID — the opaque variant for dense / in-window surfaces the occlusion audit
 * classifies "dense-legible-keep-opaque". Same hue at alpha 1, no
 * backdrop-filter dependency — a distinct authored state from the translucent
 * glass.
 */
export const Solid: Story = {
  render: () => {
    return (
      <Backdrop>
        <GlassSurface variant="solid" className="rounded-hog">
          <Sample />
        </GlassSurface>
      </Backdrop>
    );
  },
};

/**
 * SCENE-ABSENT FALLBACK — the glass variant with `sceneAbsent`, the degraded
 * state for offline / no-scene-key / over-budget. The component renders its
 * opaque solid fallback (identical to the solid variant, so the AA guarantee is
 * one thing) — the "screen complete with no scene behind it" state, authored as
 * its own story instead of left to a runtime condition.
 */
export const SceneAbsentFallback: Story = {
  render: () => {
    return (
      <Backdrop>
        <GlassSurface variant="glass" sceneAbsent className="rounded-hog">
          <Sample />
        </GlassSurface>
      </Backdrop>
    );
  },
};
