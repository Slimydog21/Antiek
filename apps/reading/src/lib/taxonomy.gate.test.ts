/**
 * taxonomy.gate.test.ts — INV-3 lockstep gate (static reconciliation).
 *
 * INV-3: the analytics taxonomy and its call sites must stay in lockstep,
 * behind ONE typed entry point. `src/lib/analytics.ts` defines the
 * `AnalyticsEvents` union (the taxonomy); components emit events only via
 * `track("<name>", …)`. TypeScript already rejects an off-taxonomy NAME at the
 * call site you are editing — but it can NOT see:
 *   (a) a taxonomy entry that has lost its last caller (a DEAD entry), nor
 *   (b) a raw `posthog.capture("magic")` that bypasses `track()` entirely.
 *
 * This test closes both holes by purely static analysis (no network, no
 * PostHog, no browser): it reconciles the DEFINED set (keys of AnalyticsEvents)
 * against the REFERENCED set (every `track("…")` across src/**), asserts set
 * EQUALITY, and forbids `posthog.capture(` outside the two sanctioned lib files.
 *
 * IF THIS TEST FAILS, the message tells you exactly what to do — read it. In
 * short:
 *   • "orphan call" → you call track("X") but X is not in AnalyticsEvents.
 *     Add X to the AnalyticsEvents type in src/lib/analytics.ts (with its
 *     property shape), or fix the typo in your track() call.
 *   • "dead entry"  → X is in AnalyticsEvents but nothing calls track("X").
 *     Remove X from AnalyticsEvents (or wire up the missing call site).
 *   • "raw capture" → you called posthog.capture(...) directly. Route it
 *     through track() in src/lib/analytics.ts instead — that is the single
 *     entry point INV-3 requires (it enforces the §9.0 content firewall).
 *
 * Why a vitest scan and not an ESLint rule: see the sprint handoff. Short
 * version — the repo has no ESLint config and CI runs vitest; an AST lint rule
 * is the better long-term home and this should migrate there if ESLint lands.
 */
import { readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

const here = dirname(fileURLToPath(import.meta.url)); // …/apps/reading/src/lib
const SRC_DIR = join(here, ".."); // …/apps/reading/src
const ANALYTICS_FILE = join(here, "analytics.ts");

// Files allowed to call posthog.capture( directly — the single entry point and
// its client. Everything else must go through track().
const RAW_CAPTURE_ALLOWLIST = new Set(["lib/analytics.ts", "lib/posthogClient.ts"]);

/** Event-name shape: snake_case lower-alnum. Matches the naming convention. */
const EVENT_NAME = "[a-z][a-z0-9_]*";

/**
 * Recursively collect *.ts / *.tsx files under a dir, EXCLUDING test files
 * (*.test.ts(x)) — tests reference event names as data and would pollute the
 * referenced set. Stories are not scanned (no .stories here, and they would be
 * call sites if present — but the include below is the source tree only).
 */
function collectSourceFiles(dir: string): string[] {
  const out: string[] = [];
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) {
      if (entry === "node_modules" || entry === "dist") continue;
      out.push(...collectSourceFiles(full));
      continue;
    }
    if (!/\.tsx?$/.test(entry)) continue;
    if (/\.test\.tsx?$/.test(entry)) continue;
    out.push(full);
  }
  return out;
}

/**
 * Extract the DEFINED taxonomy: the top-level keys of the `AnalyticsEvents`
 * type. Parsed by brace-depth tracking rather than indentation assumptions, so
 * nested property keys (question_length:, session_id:, …) and the EmptyProps
 * alias do NOT leak in, and the `event:` parameter of the track() signature
 * (which lives outside the type block) is never seen.
 *
 * Honesty note: this is text parsing, not a real TS AST. It is robust to the
 * current shape (a flat object type with inline or EmptyProps values). If the
 * taxonomy ever grows nested type expressions at depth 1 that are not simple
 * `key: value;` members, revisit — but the brace-depth guard means a nested
 * object's inner keys are at depth ≥2 and correctly ignored.
 */
function extractDefinedEvents(source: string): Set<string> {
  const startMarker = "export type AnalyticsEvents = {";
  const startIdx = source.indexOf(startMarker);
  if (startIdx === -1) {
    throw new Error(
      "taxonomy.gate: could not find `export type AnalyticsEvents = {` in " +
        "analytics.ts. If the taxonomy type was renamed/reshaped, update this " +
        "test's parser to match.",
    );
  }

  // Walk from the opening brace, tracking depth; the type body is everything
  // until depth returns to 0.
  const bodyStart = source.indexOf("{", startIdx);
  let depth = 0;
  let i = bodyStart;
  for (; i < source.length; i++) {
    const ch = source[i];
    if (ch === "{") depth++;
    else if (ch === "}") {
      depth--;
      if (depth === 0) break;
    }
  }
  const body = source.slice(bodyStart + 1, i); // inside the outermost braces

  // Now scan the body, collecting `key:` only when at depth 0 RELATIVE to the
  // body (i.e. a top-level member). Strip line comments so commented keys are
  // not counted; block comments in this file are above the type, not inside.
  const events = new Set<string>();
  let localDepth = 0;
  const lines = body.split("\n");
  for (const rawLine of lines) {
    const line = rawLine.replace(/\/\/.*$/, ""); // drop trailing line comment
    // Match a top-level member declaration only when not nested.
    if (localDepth === 0) {
      const m = line.match(new RegExp(`^\\s*(${EVENT_NAME})\\s*:`));
      if (m) events.add(m[1]);
    }
    // Update depth AFTER trying to match this line's leading key, so a member
    // like `foo: {` is captured as `foo` before we descend into its body.
    for (const ch of line) {
      if (ch === "{") localDepth++;
      else if (ch === "}") localDepth = Math.max(0, localDepth - 1);
    }
  }
  return events;
}

/**
 * Extract REFERENCED event names: every `track("NAME"` across the source tree.
 * Uses a regex with the `s` (dotAll) flag so a MULTI-LINE call —
 *   track(
 *     "deep_research_canvas_opened",
 *     { … },
 *   )
 * — is matched. (A single-line grep undercounted in the build session and
 * missed deep_research_canvas_opened / notebook_block_deleted.) Allows optional
 * whitespace/newlines between `track`, `(`, and the string literal.
 */
function extractReferencedEvents(files: { path: string; text: string }[]): {
  events: Set<string>;
  byEvent: Map<string, string[]>;
} {
  const events = new Set<string>();
  const byEvent = new Map<string, string[]>();
  // `track` as a whole word (not trackException, not someTrack), then optional
  // ws, `(`, optional ws/newlines, a double-quoted lower-snake name.
  const re = new RegExp(`\\btrack\\s*\\(\\s*"(${EVENT_NAME})"`, "gs");
  for (const { path, text } of files) {
    let m: RegExpExecArray | null;
    re.lastIndex = 0;
    while ((m = re.exec(text)) !== null) {
      const name = m[1];
      events.add(name);
      const list = byEvent.get(name) ?? [];
      if (!list.includes(path)) list.push(path);
      byEvent.set(name, list);
    }
  }
  return { events, byEvent };
}

const sourceFiles = collectSourceFiles(SRC_DIR).map((path) => ({
  path: relative(SRC_DIR, path),
  abs: path,
  text: readFileSync(path, "utf8"),
}));

const definedEvents = extractDefinedEvents(readFileSync(ANALYTICS_FILE, "utf8"));
const { events: referencedEvents, byEvent } = extractReferencedEvents(sourceFiles);

describe("INV-3 taxonomy lockstep gate", () => {
  it("parses non-trivial defined AND referenced sets (explicit no-vacuous-pass guard)", () => {
    // Makes the no-vacuous-pass property EXPLICIT rather than emergent: if EITHER
    // parser silently returned the empty set, the bidirectional equality checks
    // below would pass vacuously (∅ ⊆ ∅). Flooring BOTH sets turns a broken
    // parser into a loud failure instead of a gate that degrades into a no-op
    // (rigor #1). 10 is a deliberately loose floor against the ~20 real events —
    // tight enough to catch a broken parse, loose enough not to be brittle as
    // the taxonomy grows or shrinks.
    expect(definedEvents.size).toBeGreaterThanOrEqual(10);
    expect(referencedEvents.size).toBeGreaterThanOrEqual(10);
  });

  it("has NO orphan call sites: every track(\"X\") names a defined event", () => {
    const orphans = [...referencedEvents].filter((e) => !definedEvents.has(e));
    const detail = orphans
      .map((e) => `  • "${e}"  (called in: ${(byEvent.get(e) ?? []).join(", ")})`)
      .join("\n");
    expect(
      orphans,
      orphans.length === 0
        ? ""
        : `INV-3 violated — ORPHAN track() call(s): a track("X") references an ` +
            `event name that is NOT in the AnalyticsEvents taxonomy.\n${detail}\n` +
            `FIX: add the event (with its property shape) to the AnalyticsEvents ` +
            `type in src/lib/analytics.ts, or correct the typo in the track() call.`,
    ).toEqual([]);
  });

  it("has NO dead entries: every defined event has at least one track(\"X\") caller", () => {
    const dead = [...definedEvents].filter((e) => !referencedEvents.has(e));
    const detail = dead.map((e) => `  • "${e}"`).join("\n");
    expect(
      dead,
      dead.length === 0
        ? ""
        : `INV-3 violated — DEAD taxonomy entr(ies): defined in AnalyticsEvents ` +
            `but no track("X") call site references them.\n${detail}\n` +
            `FIX: remove the entry from the AnalyticsEvents type in ` +
            `src/lib/analytics.ts, or wire up the missing call site.`,
    ).toEqual([]);
  });

  it("has NO raw posthog.capture( outside the sanctioned lib files (single entry point)", () => {
    const offenders: string[] = [];
    for (const { path, text } of sourceFiles) {
      if (RAW_CAPTURE_ALLOWLIST.has(path)) continue;
      if (/posthog\s*\.\s*capture\s*\(/.test(text)) offenders.push(path);
    }
    const detail = offenders.map((p) => `  • ${p}`).join("\n");
    expect(
      offenders,
      offenders.length === 0
        ? ""
        : `INV-3 violated — raw posthog.capture( bypasses the single entry ` +
            `point in:\n${detail}\n` +
            `FIX: do not call posthog.capture() directly. Emit the event via ` +
            `track("<name>", …) from src/lib/analytics.ts — that is the only ` +
            `sanctioned capture surface (it enforces the §9.0 content firewall ` +
            `and keeps the taxonomy in lockstep).`,
    ).toEqual([]);
  });
});
