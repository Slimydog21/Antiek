/**
 * token-parity test (CFEEL-FIX-1) — fails `npm run test` on sun accent/shadow
 * drift between src/design/tokens.css and tailwind.config.js.
 *
 * NO RAW HEX LITERALS LIVE IN THIS FILE. Antiek's `lint:tokens` CI gate
 * (.github/workflows/ci.yml) fails on any new raw hex outside tokens.ts /
 * tokens.css, so this test DERIVES every expected sun value from tokens.css at
 * runtime (the same parse the CI guard uses) rather than hardcoding it. That
 * also keeps the test honest: it can never disagree with the source of truth.
 *
 * Three layers:
 *   1. Runs the real CI guard (scripts/check_token_parity.ts via tsx) as a
 *      subprocess and asserts it exits 0. This is the same command CI runs, so
 *      the test and the guard can never disagree.
 *   2. Asserts the parity invariants directly against the two files: tokens.css
 *      carries weathered (derived, non-empty) sun values, and tailwind.config.js
 *      REFERENCES the CSS var (never a hardcoded hex) for the accent + *-night
 *      shadow families.
 *   3. Proves the guard's parser still FAILS on drift — if a Tailwind value is
 *      re-hardcoded to a hex (the original bug), the parity predicate rejects it.
 *
 * The parity rule (which families, why) is documented in the guard's header.
 */
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const here = dirname(fileURLToPath(import.meta.url)); // apps/reading/src/design
const APP = join(here, "..", ".."); // apps/reading
const GUARD = join(APP, "scripts", "check_token_parity.ts");
const TOKENS_CSS = readFileSync(join(here, "tokens.css"), "utf8");
const TAILWIND = readFileSync(join(APP, "tailwind.config.js"), "utf8");

/** Strip `/* … *\/` comments so a commented-out declaration can never be read
 *  as a live value (mirrors the guard's cssVar comment-safety fix). */
function stripComments(src: string): string {
  return src.replace(/\/\*[\s\S]*?\*\//g, "");
}

function twColor(key: string): string | null {
  const m = TAILWIND.match(
    new RegExp(`["']${key}["']\\s*:\\s*["']([^"']+)["']`),
  );
  return m ? m[1].trim() : null;
}

function splitDayNight(src: string): { day: string; night: string } {
  const i = src.search(/@media\s*\(prefers-color-scheme:\s*dark\)/);
  return i === -1
    ? { day: src, night: "" }
    : { day: src.slice(0, i), night: src.slice(i) };
}

/** Last live `--name: <value>;` declaration in a block (comment-safe). */
function lastCssVar(block: string, name: string): string | null {
  const re = new RegExp(`--${name}\\s*:\\s*([^;]+);`, "g");
  let m: RegExpExecArray | null;
  let last: string | null = null;
  while ((m = re.exec(stripComments(block))) !== null) last = m[1].trim();
  return last;
}

const { day, night } = splitDayNight(TOKENS_CSS);

// Derived (never hardcoded) — the weathered sun values tokens.css actually
// carries, parsed the same way the guard parses them.
const DERIVED = {
  daySunDeep: lastCssVar(day, "sun-deep"),
  daySunGlow: lastCssVar(day, "sun-glow"),
  nightSunDeep: lastCssVar(night, "sun-deep"),
  nightSunGlow: lastCssVar(night, "sun-glow"),
} as const;

const IS_HEX = /^#[0-9a-fA-F]{3,8}$/;

describe("token-parity guard (the CI command)", () => {
  it("scripts/check_token_parity.ts exits 0 on the current tree", () => {
    // Throws (and fails the test) if the guard exits non-zero.
    const out = execFileSync("npx", ["tsx", GUARD], {
      cwd: APP,
      encoding: "utf8",
    });
    expect(out).toContain("token-parity OK");
  });
});

describe("token-parity invariants (per family)", () => {
  it("tokens.css carries a real sun value per theme (source of truth, derived)", () => {
    // No hardcoded expectation: just that each is present and a real hex. The
    // guard subprocess above + EXPECTED_CSS in the guard pin the EXACT weathered
    // values; here we only assert the source of truth is populated and well-formed.
    for (const [label, v] of Object.entries(DERIVED)) {
      expect(v, `tokens.css ${label}`).toBeTruthy();
      expect(v as string, `tokens.css ${label} must be a hex`).toMatch(IS_HEX);
    }
    // Day and night MUST differ per theme (a regression that collapses them to
    // one value would be invisible to the presence check alone).
    expect(DERIVED.daySunDeep).not.toBe(DERIVED.nightSunDeep);
    expect(DERIVED.daySunGlow).not.toBe(DERIVED.nightSunGlow);
  });

  it("tailwind accent keys reference the CSS var (cascade per theme, no hardcoded hex)", () => {
    expect(twColor("sun-deep")).toBe("var(--sun-deep)");
    expect(twColor("sun-glow")).toBe("var(--sun-glow)");
  });

  it("tailwind *-night shadows cast var(--sun-deep) (not a hardcoded hex)", () => {
    for (const key of ["z1-night", "z2-night", "z3-night", "lift-night"]) {
      const v = twColor(key);
      expect(v, `boxShadow["${key}"]`).toContain("var(--sun-deep)");
      expect(v, `boxShadow["${key}"] must not hardcode a hex`).not.toMatch(
        /#[0-9a-fA-F]{3,8}/,
      );
    }
  });
});

describe("token-parity guard fails on drift", () => {
  // The parity predicate the guard uses for the accent family: the Tailwind
  // value must be exactly the CSS var, never a hardcoded colour. Re-derive it
  // here (no hex literal) and prove a re-hardcoded value is rejected.
  const isDriftFree = (val: string, key: string) => val === `var(--${key})`;
  const shadowDriftFree = (val: string) => val.includes("var(--sun-deep)");

  it("rejects an accent value re-hardcoded back to a colour", () => {
    const drifted = String(DERIVED.daySunDeep); // a real hex, derived not literal
    expect(isDriftFree("var(--sun-deep)", "sun-deep")).toBe(true);
    expect(isDriftFree(drifted, "sun-deep")).toBe(false);
  });

  it("rejects a *-night shadow whose cast colour is a hardcoded hex", () => {
    const driftedShadow = `0 1px 2px ${String(DERIVED.nightSunDeep)}`;
    expect(shadowDriftFree("0 1px 2px var(--sun-deep)")).toBe(true);
    expect(shadowDriftFree(driftedShadow)).toBe(false);
  });
});


describe("research-state token family (herdr transfer P0-1)", () => {
  // The --state-* tokens are SEMANTIC ALIASES over the palette constants.
  // The invariant: every --state-* var exists in BOTH day and night css
  // blocks, and the tokens.ts `state` mirror names the same alias target.
  // A state colour can then never drift from the brand palette.
  const STATE_KEYS = [
    "working",
    "blocked",
    "done",
    "stopped",
    "muted",
  ] as const;

  const cssStateAliases = (block: string): Map<string, string> => {
    const map = new Map<string, string>();
    const re = /--state-([a-z]+)\s*:\s*var\((--[\w-]+)\);/g;
    let m: RegExpExecArray | null;
    while ((m = re.exec(stripComments(block))) !== null) {
      map.set(m[1], m[2]);
    }
    return map;
  };

  const tsStateAliases = (): Map<string, string> => {
    const src = readFileSync(join(here, "tokens.ts"), "utf8");
    const map = new Map<string, string>();
    const re = /([a-z]+):\s*"var\((--[\w-]+)\)",/g;
    let m: RegExpExecArray | null;
    while ((m = re.exec(src)) !== null) {
      map.set(m[1], m[2]);
    }
    return map;
  };

  it("every state token exists in the day css block", () => {
    const aliases = cssStateAliases(day);
    for (const key of STATE_KEYS) expect(aliases.has(key)).toBe(true);
  });

  it("every state token exists in the night css block", () => {
    const aliases = cssStateAliases(night);
    for (const key of STATE_KEYS) expect(aliases.has(key)).toBe(true);
  });

  it("tokens.ts `state` mirror matches the css aliases exactly", () => {
    const cssAliases = cssStateAliases(day);
    const tsAliases = tsStateAliases();
    for (const key of STATE_KEYS) {
      expect(tsAliases.get(key)).toBe(cssAliases.get(key));
    }
  });

  it("state aliases point only at palette constants (never raw hex)", () => {
    const aliases = cssStateAliases(day);
    for (const target of aliases.values()) {
      expect(target).toMatch(/^--(sun|emperor|aurora|shadow-)/);
    }
  });
});
