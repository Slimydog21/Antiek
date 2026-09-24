/**
 * token-parity test — fails `npm run test` when tokens.ts, tokens.css and
 * tailwind.config.js disagree, or when the theme mechanism's invariants break.
 *
 * NO RAW HEX LITERALS LIVE IN THIS FILE (lint:tokens forbids them outside the
 * token files): every expectation is read from tokens.ts or resolved from
 * tokens.css through the same parser the CI guard uses (tokenCss.ts).
 *
 * Layers:
 *   1. The CI guard (scripts/check_token_parity.ts) exits 0: the same command
 *      CI runs, so test and guard cannot disagree.
 *   2. Direct invariants: TS semantic == CSS per theme; the night fallback is
 *      the night block; every legacy alias resolves through a semantic token;
 *      the Tailwind keys call sites use read the vars they must.
 *   3. The predicates still FAIL on drift (a re-hardcoded value is rejected).
 */
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

import { parseTokensCss, resolveVar, toRgba } from "./tokenCss";
import { semantic, state, surface, type Theme } from "./tokens";
import { zIndex } from "./zIndex";

const here = dirname(fileURLToPath(import.meta.url)); // apps/reading/src/design
const APP = join(here, "..", ".."); // apps/reading
const GUARD = join(APP, "scripts", "check_token_parity.ts");
const sheet = parseTokensCss(readFileSync(join(here, "tokens.css"), "utf8"));
type TwConfig = {
  darkMode: unknown;
  future?: { hoverOnlyWhenSupported?: boolean };
  theme: { extend: Record<string, Record<string, string | Record<string, string>>> };
};
const twModule = createRequire(import.meta.url)(join(APP, "tailwind.config.js"));
const tailwindConfig = (twModule.default ?? twModule) as TwConfig;
const ext = tailwindConfig.theme.extend;
const THEMES: Theme[] = ["light", "dark"];
const ch = (name: string) => `rgb(var(--${name}-rgb) / <alpha-value>)`;
const hexOf = (theme: Theme, name: string) => {
  const v = resolveVar(sheet, theme, name);
  const c = v === null ? null : toRgba(v);
  return c === null ? null : [c.r, c.g, c.b, Math.round(c.a * 100)].join(",");
};

describe("token-parity guard (the CI command)", () => {
  it("scripts/check_token_parity.ts exits 0 on the current tree", { timeout: 30_000 }, () => {
    const tsx = join(APP, "node_modules", ".bin", "tsx");
    const out = execFileSync(tsx, [GUARD], { cwd: APP, encoding: "utf8" });
    expect(out).toContain("token-parity OK");
  });
});

describe("the semantic layer: one value per token per theme", () => {
  it("tokens.ts `semantic` equals what tokens.css resolves to, in both themes", () => {
    const cssName = (k: string) => `--${k.replace(/([A-Z0-9])/g, (m) => `-${m.toLowerCase()}`)}`;
    for (const theme of THEMES) {
      for (const [key, value] of Object.entries(semantic[theme])) {
        const c = toRgba(value)!;
        expect(hexOf(theme, cssName(key)), `${theme} ${cssName(key)}`).toBe(
          [c.r, c.g, c.b, Math.round(c.a * 100)].join(","),
        );
      }
    }
  });

  it("night and day really differ for the surfaces and text (the theme is not a no-op)", () => {
    for (const name of ["--bg-page", "--bg-card", "--text-1", "--text-3", "--border-rule", "--focus"]) {
      expect(hexOf("light", name), name).not.toBe(hexOf("dark", name));
    }
  });

  it("the no-JS @media fallback declares exactly the [data-theme=dark] block", () => {
    expect(sheet.nightList.length).toBeGreaterThan(40);
    expect(sheet.fallbackList).toEqual(sheet.nightList);
  });

  it("every legacy alias resolves to its semantic token in both themes", () => {
    const aliases: Array<[string, string]> = [
      ["--ice-0", "--bg-card"],
      ["--ice-1", "--bg-card"],
      ["--ice-2", "--bg-page"],
      ["--ice-3", "--bg-inset"],
      ["--ice-4", "--border-hairline"],
      ["--page", "--bg-page"],
      ["--card", "--bg-card"],
      ["--inset", "--bg-inset"],
      ["--divider", "--border-hairline"],
      ["--ink", "--text-1"],
      ["--text", "--text-1"],
      ["--ink-soft", "--text-2"],
      ["--shadow-1", "--text-2"],
      ["--text-muted", "--text-2"],
      ["--ink-mute", "--text-3"],
      ["--rule", "--border-rule"],
      ["--border", "--border-rule"],
      ["--emperor", "--danger"],
    ];
    for (const theme of THEMES) {
      for (const [legacy, sem] of aliases) {
        expect(hexOf(theme, legacy), `${theme} ${legacy} → ${sem}`).toBe(hexOf(theme, sem));
      }
    }
  });

  it("var(--shadow-2) is the fixed slate pigment bg-shadow-2 and surface.day[8] paint (BrainJourney's day coat)", () => {
    // It once aliased --text-2 and the day coat drifted a step lighter.
    const c = toRgba(surface.day[8])!;
    expect(hexOf("light", "--shadow-2")).toBe([c.r, c.g, c.b, 100].join(","));
    expect(hexOf("light", "--shadow-2")).toBe(hexOf("light", "--fixed-ink-2"));
    expect(ext.colors["shadow-2"]).toBe(ch("fixed-ink-2"));
  });

  it("the night palette primitives Login.css (and dark: keys) read are declared", () => {
    for (const name of ["--charcoal-1", "--charcoal-2", "--space-2", "--bright", "--starlight", "--moonlight"]) {
      expect(resolveVar(sheet, "light", name), name).not.toBeNull();
    }
    // moonlight IS the night tertiary text: dark:text-moonlight == night text-3.
    expect(hexOf("dark", "--moonlight")).toBe(hexOf("dark", "--text-3"));
  });
});

describe("Tailwind keys call sites use resolve to the right token", () => {
  it("every colour key in every colour map reads a tokens.css var (no literals)", () => {
    for (const map of ["colors", "textColor", "backgroundColor", "borderColor"]) {
      for (const [key, raw] of Object.entries(ext[map] ?? {})) {
        // A nested key (teal) keeps Tailwind's palette steps; ours is DEFAULT.
        const value = typeof raw === "object" && raw !== null ? (raw as Record<string, string>).DEFAULT : raw;
        expect(String(value), `${map}.${key}`).toMatch(/^(rgb\(var\(--[\w-]+\) \/ <alpha-value>\)|var\(--[\w-]+\))$/);
      }
    }
  });

  it("split keys: text-sun-deep is the brand as text, border-sun-deep the edge", () => {
    expect(ext.textColor["sun-deep"]).toBe(ch("sun-ink"));
    expect(ext.colors["sun-deep"]).toBe(ch("sun-deep"));
    expect(ext.textColor.aurora).toBe(ch("teal"));
    expect(ext.colors.aurora).toBe(ch("aurora"));
    expect(ext.colors.emperor).toBe(ch("danger"));
    expect(ext.backgroundColor.emperor).toBe(ch("danger-fill"));
  });

  it("night borders reach the rule: border-charcoal-1 and the DEFAULT border read --border-rule", () => {
    expect(ext.borderColor["charcoal-1"]).toBe(ch("border-rule"));
    expect(ext.borderColor.DEFAULT).toBe(ch("border-rule"));
    expect(ext.colors.rule).toBe(ch("border-rule"));
  });

  it("the *-night shadows cast var(--sun-deep)", () => {
    const shadows = ext.boxShadow;
    for (const key of ["z1-night", "z2-night", "z3-night", "lift-night"]) {
      expect(shadows[key]).toContain("var(--sun-deep)");
      expect(shadows[key]).not.toMatch(/#[0-9a-fA-F]{3,8}/);
    }
  });

  it("dark: is keyed on the data-theme attribute, and hover waits for a real pointer", () => {
    expect(tailwindConfig.darkMode).toEqual(["selector", '[data-theme="dark"]']);
    expect(tailwindConfig.future?.hoverOnlyWhenSupported).toBe(true);
  });

  it("a bare `transition` runs on the motion tokens", () => {
    expect(ext.transitionDuration.DEFAULT).toBe("var(--motion-base)");
    expect(ext.transitionTimingFunction.DEFAULT).toBe("var(--ease-standard)");
  });
});

describe("state and z-index tokens", () => {
  it("tokens.ts `state` names the same targets tokens.css declares", () => {
    const cssName = (k: string) => `--state-${k.replace(/([A-Z])/g, (m) => `-${m.toLowerCase()}`)}`;
    for (const [key, target] of Object.entries(state)) {
      expect(sheet.root.get(cssName(key)), cssName(key)).toBe(target);
    }
  });

  it("every state resolves to a semantic colour in both themes (never a raw hex at the alias)", () => {
    for (const [name, value] of sheet.root) {
      if (!name.startsWith("--state-")) continue;
      expect(value, name).toMatch(/^var\(--(sun-ink|danger|success|text-[23]|stale|not-run)\)$/);
      for (const theme of THEMES) expect(resolveVar(sheet, theme, name), `${theme} ${name}`).not.toBeNull();
    }
  });

  it("the --z-* ladder in tokens.css equals zIndex.ts", () => {
    const pairs: Array<[string, number]> = [
      ["--z-raised", zIndex.raised],
      ["--z-floating", zIndex.floatingPanelBase],
      ["--z-scene-badge", zIndex.sceneBadge],
      ["--z-window", zIndex.windowBase],
      ["--z-mobile-rail", zIndex.mobileRail],
      ["--z-floating-ceiling", zIndex.floatingPanelCeiling],
      ["--z-mobile-rail-toggle", zIndex.mobileRailToggle],
      ["--z-mascot", zIndex.mascot],
      ["--z-modal", zIndex.modal],
      ["--z-popover", zIndex.popover],
      ["--z-ad-overlay", zIndex.adOverlay],
      ["--z-toast", zIndex.toast],
      ["--z-tooltip", zIndex.tooltip],
    ];
    for (const [name, value] of pairs) expect(Number(sheet.root.get(name)), name).toBe(value);
  });
});

describe("the predicates still fail on drift", () => {
  const keyReadsVar = (v: string) => /^(rgb\(var\(--[\w-]+\) \/ <alpha-value>\)|var\(--[\w-]+\))$/.test(v);

  it("rejects a colour key re-hardcoded to a literal (the CFEEL-FIX-1 bug)", () => {
    const literal = semantic.light.text3; // a real colour value, read not typed
    expect(keyReadsVar(ch("text-3"))).toBe(true);
    expect(keyReadsVar(literal)).toBe(false);
  });

  it("rejects a fallback that drifted from the night block", () => {
    const drifted = [...sheet.nightList.slice(1), "--text-3: var(--slate-2)"];
    expect(drifted).not.toEqual(sheet.nightList);
  });
});
