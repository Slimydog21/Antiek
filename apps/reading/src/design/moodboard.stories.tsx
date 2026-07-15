import type { Meta, StoryObj } from "@storybook/react";

import { sun, surface, shadow, type as typeTokens, werner } from "./tokens";

/**
 * Antiek design moodboard — operator sign-off gate.
 *
 * This story is the literal S0 acceptance artefact. The operator opens
 * each variant and confirms the aesthetic before any S1 primitive is built.
 *
 * Stories:
 *   - Palette · Day        — 10-step ice/glacial ramp + sun + accents
 *   - Palette · Night      — 10-step void/starlight ramp + sun glow
 *   - Shadows · Day vs Night — chunky offset stack
 *   - Typography           — Inter / JetBrains Mono / Charter
 *   - Outlined Card        — the brand primitive in both modes side-by-side
 *   - Highlighter          — sun-yellow as the reading-product highlighter
 *   - Before / After       — current ChatInput vs the redesign direction
 *
 * Spec reference: docs/ui_redesign_posthog/sprint_00_foundations.html WP-0.3
 * Brand bible:     docs/ui_redesign_posthog/brand_werner.html
 */
const meta = {
  title: "Design / Moodboard",
  parameters: {
    layout: "padded",
    backgrounds: { default: "ice-2" },
  },
  tags: ["autodocs"],
} satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

// ─────────────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────────────

const SURFACE_NAMES_DAY = [
  "ice-0", "ice-1", "ice-2", "ice-3", "ice-4",
  "glacial-1", "glacial-2", "shadow-1", "shadow-2", "ink",
];
const SURFACE_NAMES_NIGHT = [
  "void", "space-1", "space-2", "charcoal-1", "charcoal-2",
  "slate-1", "slate-2", "moonlight", "starlight", "bright",
];

function swatchTextColor(hex: string) {
  const channels = hex
    .slice(1)
    .match(/.{2}/g)!
    .map((channel) => Number.parseInt(channel, 16) / 255)
    .map((channel) =>
      channel <= 0.04045
        ? channel / 12.92
        : ((channel + 0.055) / 1.055) ** 2.4,
    );
  const luminance =
    0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2];
  // Pure endpoints guarantee the WCAG 4.5:1 floor even for mid-ramp samples;
  // the swatch is a token specimen, so its overlaid annotation must not use a
  // softer brand off-black/off-white at the contrast boundary.
  return luminance > 0.179 ? "black" : "white";
}

function Swatch({
  name, hex, dark, role,
}: { name: string; hex: string; dark?: boolean; role?: string }) {
  return (
    <div
      style={{
        background: hex,
        border: `2.5px solid ${sun.base}`,
        borderRadius: 6,
        boxShadow: dark ? "5px 5px 0 0 #8A7300" : "5px 5px 0 0 #0F1419",
        padding: 14,
        minHeight: 88,
        color: swatchTextColor(hex),
        fontFamily: '"JetBrains Mono", monospace',
        fontSize: 11.5,
      }}
    >
      <div style={{ fontSize: 13, fontWeight: 700 }}>{hex}</div>
      <div style={{ marginTop: 6, textTransform: "uppercase", letterSpacing: "0.05em" }}>{name}</div>
      {role && <div style={{ marginTop: 4 }}>{role}</div>}
    </div>
  );
}

function Grid({ children }: { children: React.ReactNode }) {
  return (
    <div style={{
      display: "grid",
      gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
      gap: 12,
      padding: 24,
    }}>{children}</div>
  );
}

function Heading({ children }: { children: React.ReactNode }) {
  return (
    <h2 style={{
      fontFamily: typeTokens.sans,
      fontSize: 28,
      fontWeight: 800,
      margin: "20px 24px 6px",
      borderBottom: `3px solid ${sun.base}`,
      paddingBottom: 8,
      color: "#0F1419",
    }}>{children}</h2>
  );
}

// ─────────────────────────────────────────────────────────────────────
// Palette · Day
// ─────────────────────────────────────────────────────────────────────

export const PaletteDay: Story = {
  name: "Palette · Day (off-whites + glacials)",
  render: () => (
    <div style={{ background: "#F4F7FA", minHeight: "100vh" }}>
      <Heading>Brand · the constant</Heading>
      <Grid>
        <Swatch name="sun"      hex={sun.base}        role="brand outline" />
        <Swatch name="sun-deep" hex={sun.deep.day}    role="hover / depth" />
        <Swatch name="sun-glow" hex={sun.glow.day}    role="highlight peaks" />
      </Grid>

      <Heading>Day surface ramp · 10 steps</Heading>
      <Grid>
        {surface.day.map((hex, i) => (
          <Swatch key={i} name={SURFACE_NAMES_DAY[i]} hex={hex} role={`step ${i}`} />
        ))}
      </Grid>

      <Heading>Reserved accents</Heading>
      <Grid>
        <Swatch name="aurora"  hex="#16C2C2" role="AI thinking" />
        <Swatch name="emperor" hex="#E33C2D" role="danger only" />
      </Grid>
    </div>
  ),
};

// ─────────────────────────────────────────────────────────────────────
// Palette · Night
// ─────────────────────────────────────────────────────────────────────

export const PaletteNight: Story = {
  name: "Palette · Night (majestic night sky)",
  parameters: { backgrounds: { default: "space-2 (night)" } },
  render: () => (
    <div style={{
      background: "#0D1019",
      minHeight: "100vh",
      color: "#EEF1F6",
    }}>
      <h2 style={{
        fontFamily: typeTokens.sans, fontSize: 28, fontWeight: 800,
        margin: "20px 24px 6px",
        borderBottom: `3px solid ${sun.base}`,
        paddingBottom: 8,
        color: "#EEF1F6",
      }}>Brand · same yellow, glowing shadows</h2>
      <Grid>
        <Swatch name="sun"      hex={sun.base}        dark role="brand outline" />
        <Swatch name="sun-deep" hex={sun.deep.night}  dark role="night shadow" />
        <Swatch name="sun-glow" hex={sun.glow.night}  dark role="highlight" />
      </Grid>

      <h2 style={{
        fontFamily: typeTokens.sans, fontSize: 28, fontWeight: 800,
        margin: "20px 24px 6px",
        borderBottom: `3px solid ${sun.base}`,
        paddingBottom: 8,
        color: "#EEF1F6",
      }}>Night surface ramp · 10 steps</h2>
      <Grid>
        {surface.night.map((hex, i) => (
          <Swatch key={i} name={SURFACE_NAMES_NIGHT[i]} hex={hex} dark role={`step ${i}`} />
        ))}
      </Grid>
    </div>
  ),
};

// ─────────────────────────────────────────────────────────────────────
// Shadows
// ─────────────────────────────────────────────────────────────────────

export const Shadows: Story = {
  render: () => (
    <div style={{ background: "#F4F7FA", padding: 32 }}>
      <Heading>Chunky offset shadows · z1 · z2 · z3 · lift</Heading>
      <p style={{ margin: "0 24px 18px", color: "#384858", fontSize: 14 }}>
        Day mode casts in ink; night mode casts in sun-deep (glowing).
        Each rises by ~2px on hover with a deeper shadow swap.
      </p>
      <Grid>
        {(["z1", "z2", "z3", "lift"] as const).map((k) => (
          <div key={k} style={{
            background: "#FFFFFF",
            border: `2.5px solid ${sun.base}`,
            borderRadius: 6,
            boxShadow: shadow.day[k],
            padding: 22,
            fontFamily: typeTokens.mono,
            fontSize: 13,
            fontWeight: 700,
            color: "#0F1419",
          }}>
            shadow-{k}
            <div style={{ fontSize: 11, marginTop: 6, opacity: 0.7, fontWeight: 400 }}>
              {shadow.day[k]}
            </div>
          </div>
        ))}
      </Grid>

      <h3 style={{ fontFamily: typeTokens.sans, fontSize: 18, margin: "28px 24px 8px" }}>
        Night equivalents (rendered on dark surface)
      </h3>
      <div style={{ background: "#0D1019", padding: 24, borderRadius: 6 }}>
        <Grid>
          {(["z1", "z2", "z3", "lift"] as const).map((k) => (
            <div key={k} style={{
              background: "#1B202A",
              border: `2.5px solid ${sun.base}`,
              borderRadius: 6,
              boxShadow: shadow.night[k],
              padding: 22,
              fontFamily: typeTokens.mono,
              fontSize: 13,
              fontWeight: 700,
              color: "#EEF1F6",
            }}>
              shadow-{k} (night)
              <div style={{ fontSize: 11, marginTop: 6, opacity: 0.7, fontWeight: 400 }}>
                {shadow.night[k]}
              </div>
            </div>
          ))}
        </Grid>
      </div>
    </div>
  ),
};

// ─────────────────────────────────────────────────────────────────────
// Typography
// ─────────────────────────────────────────────────────────────────────

export const Typography: Story = {
  render: () => (
    <div style={{ background: "#FBFCFD", padding: 32, color: "#0F1419" }}>
      <Heading>Type stack · Inter · JetBrains Mono · Charter</Heading>

      <div style={{ marginTop: 18 }}>
        <div style={{ fontFamily: typeTokens.sans, fontSize: 40, fontWeight: 800, lineHeight: 1.1 }}>
          Inter Display — H1
        </div>
        <div style={{ fontFamily: typeTokens.sans, fontSize: 26, fontWeight: 700, marginTop: 6 }}>
          Inter Sans — H2 / Section
        </div>
        <div style={{ fontFamily: typeTokens.sans, fontSize: 15, marginTop: 10, lineHeight: 1.55 }}>
          Inter body. The whole UI chrome runs on this — buttons, panels,
          breadcrumbs, tags. 15px / 1.55. Neutral, modern, neutral to
          the eye, leaves the reading prose to do the heavy lifting.
        </div>
        <div style={{ fontFamily: typeTokens.mono, fontSize: 13, marginTop: 16, color: "#384858" }}>
          JetBrains Mono · system text · 13px · for IDs, timestamps,
          status, kbd hints, code, trajectory data.
        </div>
        <div style={{ fontFamily: typeTokens.serif, fontSize: 18, marginTop: 18, lineHeight: 1.55 }}>
          Charter — reading prose. The MasterMdViewer and the Notebook
          prose blocks render in this. The brand chrome may be flat
          and stamped, but the actual <em>reading</em> stays serif —
          a notebook on the inside, a workshop on the outside.
        </div>
      </div>
    </div>
  ),
};

// ─────────────────────────────────────────────────────────────────────
// Outlined Card — the brand primitive
// ─────────────────────────────────────────────────────────────────────

export const OutlinedCard: Story = {
  render: () => (
    <div style={{
      display: "grid",
      gridTemplateColumns: "1fr 1fr",
      gap: 32,
      padding: 32,
    }}>
      {/* Day */}
      <div style={{ background: "#F4F7FA", padding: 24, borderRadius: 6 }}>
        <div style={{
          fontFamily: typeTokens.mono, fontSize: 11.5,
          textTransform: "uppercase", letterSpacing: "0.05em",
          color: "#384858", marginBottom: 12,
        }}>day</div>
        <div style={{
          background: "#FFFFFF",
          border: `2.5px solid ${sun.base}`,
          borderRadius: 6,
          boxShadow: shadow.day.z2,
          padding: "18px 22px",
          fontFamily: typeTokens.sans,
          fontSize: 14,
          color: "#0F1419",
        }}>
          <div style={{ fontWeight: 700, fontSize: 17, marginBottom: 6 }}>
            Outlined Card
          </div>
          <p style={{ margin: 0, color: "#384858" }}>
            The brand primitive. Sun-yellow border, ink-cast offset
            shadow. Every panel, modal, tag, table, and chip inherits
            this edge across the whole product.
          </p>
        </div>
      </div>
      {/* Night */}
      <div style={{ background: "#0D1019", padding: 24, borderRadius: 6 }}>
        <div style={{
          fontFamily: typeTokens.mono, fontSize: 11.5,
          textTransform: "uppercase", letterSpacing: "0.05em",
          color: "#A0AAB8", marginBottom: 12,
        }}>night</div>
        <div style={{
          background: "#1B202A",
          border: `2.5px solid ${sun.base}`,
          borderRadius: 6,
          boxShadow: shadow.night.z2,
          padding: "18px 22px",
          fontFamily: typeTokens.sans,
          fontSize: 14,
          color: "#EEF1F6",
        }}>
          <div style={{ fontWeight: 700, fontSize: 17, marginBottom: 6 }}>
            Same Card · Night
          </div>
          <p style={{ margin: 0, color: "#C4CCD7" }}>
            Same yellow border, but the offset shadow now glows in
            sun-deep instead of absorbing in ink. The chrome reads as
            stitched at night rather than stamped.
          </p>
        </div>
      </div>
    </div>
  ),
};

// ─────────────────────────────────────────────────────────────────────
// Highlighter
// ─────────────────────────────────────────────────────────────────────

export const Highlighter: Story = {
  render: () => (
    <div style={{
      background: "#FBFCFD",
      padding: 32,
      maxWidth: 760,
      margin: "0 auto",
      color: "#0F1419",
    }}>
      <Heading>Yellow as the reading-product highlighter</Heading>
      <p style={{ fontFamily: typeTokens.serif, fontSize: 18, lineHeight: 1.6, marginTop: 18 }}>
        Werner is heading <Hl>toward the mountains, some seventy kilometres
        away</Hl>, and although he could be returned to the colony, he
        <Hl> would immediately turn around and head back for the mountains</Hl>.
        The yellow is sun · the brand colour · used here as the operator's
        manual highlight, at 45% opacity, with a 2px sun underline so the
        eye still reads the prose as text-on-paper rather than
        text-replaced-by-fill.
      </p>

      <h3 style={{ fontFamily: typeTokens.sans, fontSize: 18, marginTop: 32 }}>Three layered intensities</h3>
      <div style={{ marginTop: 12, fontFamily: typeTokens.serif, fontSize: 16, lineHeight: 1.7 }}>
        <p><FaintHl>auto-suggested</FaintHl> · model thinks this is worth a look · 18% opacity</p>
        <p><Hl>operator highlight</Hl> · the explicit manual mark · 45% opacity</p>
        <p><ActiveHl>currently selected</ActiveHl> · the one the toolbar is acting on · solid sun</p>
      </div>
    </div>
  ),
};

function Hl({ children }: { children: React.ReactNode }) {
  return (
    <mark style={{
      background: sun.highlight.day,
      boxShadow: `inset 0 -2px 0 ${sun.base}`,
      padding: "0 3px",
      borderRadius: 2,
      color: "inherit",
    }}>{children}</mark>
  );
}
function FaintHl({ children }: { children: React.ReactNode }) {
  return (
    <mark style={{
      background: sun.highlight.faint,
      padding: "0 3px",
      borderRadius: 2,
      color: "inherit",
    }}>{children}</mark>
  );
}
function ActiveHl({ children }: { children: React.ReactNode }) {
  return (
    <mark style={{
      background: sun.base,
      padding: "0 3px",
      borderRadius: 2,
      color: "#0F1419",
    }}>{children}</mark>
  );
}

// ─────────────────────────────────────────────────────────────────────
// Before / After — current ChatInput vs the brand direction
// ─────────────────────────────────────────────────────────────────────

export const BeforeAfter: Story = {
  name: "Before / After · ChatInput",
  render: () => (
    <div style={{
      display: "grid", gridTemplateColumns: "1fr 1fr",
      gap: 32, padding: 32, background: "#F4F7FA",
    }}>
      <div>
        <div style={{
          fontFamily: typeTokens.mono, fontSize: 11.5,
          textTransform: "uppercase", letterSpacing: "0.05em",
          color: "#384858", marginBottom: 12,
        }}>before · current flat shell</div>
        <div style={{
          background: "#ffffff",
          border: "1px solid #e7e5e4",   // stone-200, the current UI
          borderRadius: 4,
          padding: 14,
          fontFamily: typeTokens.sans,
        }}>
          <textarea
            placeholder="Ask anything…"
            style={{
              width: "100%",
              border: "1px solid #d6d3d1",
              borderRadius: 3,
              padding: 8,
              fontFamily: typeTokens.sans,
              fontSize: 14,
              outline: "none",
              resize: "none",
              minHeight: 80,
            }}
          />
          <div style={{ marginTop: 8, display: "flex", justifyContent: "flex-end" }}>
            <button style={{
              background: "#0F1419", color: "#ffffff",
              border: "1px solid #0F1419", borderRadius: 3,
              padding: "6px 12px", fontSize: 13, cursor: "pointer",
            }}>Ask</button>
          </div>
        </div>
      </div>

      <div>
        <div style={{
          fontFamily: typeTokens.mono, fontSize: 11.5,
          textTransform: "uppercase", letterSpacing: "0.05em",
          color: "#384858", marginBottom: 12,
        }}>after · Werner brand</div>
        <div style={{
          background: "#FFFFFF",
          border: `2.5px solid ${sun.base}`,
          borderRadius: 6,
          boxShadow: shadow.day.z2,
          padding: 14,
          fontFamily: typeTokens.sans,
        }}>
          <textarea
            placeholder="Ask anything…"
            style={{
              width: "100%",
              border: `2px solid ${sun.base}`,
              borderRadius: 4,
              padding: 10,
              fontFamily: typeTokens.sans,
              fontSize: 14,
              outline: "none",
              resize: "none",
              minHeight: 80,
              background: "#FBFCFD",
            }}
          />
          <div style={{ marginTop: 10, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span style={{
              fontFamily: typeTokens.mono, fontSize: 11,
              padding: "1px 8px",
              background: "#FBFCFD",
              border: `2px solid #0F1419`,
              borderRadius: 4,
              boxShadow: "2px 2px 0 0 #0F1419",
            }}>⌘ ↵</span>
            <button style={{
              background: sun.base, color: "#0F1419",
              border: `2px solid #0F1419`, borderRadius: 6,
              padding: "6px 14px", fontFamily: typeTokens.mono,
              fontWeight: 700, fontSize: 13, cursor: "pointer",
              boxShadow: "3px 3px 0 0 #0F1419",
            }}>Ask</button>
          </div>
        </div>
      </div>
    </div>
  ),
};

// ─────────────────────────────────────────────────────────────────────
// Werner (palette reference)
// ─────────────────────────────────────────────────────────────────────

export const WernerPalette: Story = {
  name: "Werner · bill+feet = brand sun",
  render: () => (
    <div style={{ padding: 32, background: "#F4F7FA" }}>
      <Heading>Werner palette — the visual hook</Heading>
      <p style={{ margin: "0 0 18px", color: "#384858", maxWidth: 620 }}>
        Werner's bill and feet are the exact same yellow as the brand
        outline. That is the link between mascot and chrome — outline = bill =
        highlight, one colour repeated.
      </p>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 24 }}>
        <div>
          <div style={{
            fontFamily: typeTokens.mono, fontSize: 11.5,
            textTransform: "uppercase", letterSpacing: "0.05em",
            color: "#384858", marginBottom: 12,
          }}>day werner</div>
          <Grid>
            <Swatch name="coat"  hex={werner.day.coat}  role="off-black" />
            <Swatch name="belly" hex={werner.day.belly} role="off-white" />
            <Swatch name="bill"  hex={werner.day.bill}  role="= sun" />
            <Swatch name="foot"  hex={werner.day.foot}  role="= sun" />
            <Swatch name="eye"   hex={werner.day.eye}   role="ink dot" />
          </Grid>
        </div>
        <div>
          <div style={{
            fontFamily: typeTokens.mono, fontSize: 11.5,
            textTransform: "uppercase", letterSpacing: "0.05em",
            color: "#384858", marginBottom: 12,
          }}>night werner</div>
          <Grid>
            <Swatch name="coat"  hex={werner.night.coat}  role="deeper black" dark />
            <Swatch name="belly" hex={werner.night.belly} role="starlight"   />
            <Swatch name="bill"  hex={werner.night.bill}  role="= sun"        />
            <Swatch name="foot"  hex={werner.night.foot}  role="= sun"        />
            <Swatch name="eye"   hex={werner.night.eye}   role="starlight"   />
          </Grid>
        </div>
      </div>
    </div>
  ),
};
