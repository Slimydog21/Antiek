/**
 * narrateEvent.test.ts — the narration-coverage gate (SPR-02 M1).
 *
 * The load-bearing test of this sprint. The thinking stream renders only
 * what narrateEvent returns; if an action_type the orchestrator can emit
 * has no row in the map, it would fall through to the generic "Working…"
 * beat AND log a drift warning. This test makes that impossible to ship
 * silently: it enumerates the generated ActionType catalogue (the single
 * source of truth, regenerated from substrate/schemas/events.py) and asserts
 * EVERY value has an explicit row — a narration or an explicit suppress.
 *
 * When the schema adds an action_type: codegen regenerates types.ts, this
 * test goes red, and narrateEvent.ts must gain a row (narrate it or suppress
 * it) before the build is green. That is the coverage invariant working.
 */
import { describe, expect, it, vi } from "vitest";

import { ActionType } from "../../generated/types";
import type { Event } from "../../generated/types";
import { narrateEvent, narratedActionTypes } from "./narrateEvent";

const ALL_ACTION_TYPES = Object.values(ActionType) as string[];

function eventOf(actionType: string, payload: Record<string, unknown> = {}): Event {
  return {
    event_id: `e-${actionType}`,
    investigation_id: "inv-test",
    action_type: actionType as Event["action_type"],
    payload: payload as unknown as Event["payload"],
    param_version: "v1",
    emitted_at: "2026-05-26T00:00:00Z",
  };
}

describe("narrateEvent — coverage (the gate)", () => {
  it("every action_type in the generated catalogue has an explicit row", () => {
    const covered = narratedActionTypes();
    const missing = ALL_ACTION_TYPES.filter((t) => !covered.has(t));
    expect(
      missing,
      `These action_types have no narration row — add each to narrateEvent.ts ` +
        `(narrate it, or set it to null to suppress):\n  ${missing.join("\n  ")}`,
    ).toEqual([]);
  });

  it("the map has no stale rows for action_types the catalogue dropped", () => {
    const catalogue = new Set(ALL_ACTION_TYPES);
    const stale = [...narratedActionTypes()].filter((t) => !catalogue.has(t));
    expect(
      stale,
      `These rows narrate action_types no longer in the catalogue — remove them:\n  ${stale.join("\n  ")}`,
    ).toEqual([]);
  });

  it("narrating every catalogued type never throws and never warns (no drift)", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    for (const t of ALL_ACTION_TYPES) {
      expect(() => narrateEvent(eventOf(t)), `narrating ${t} threw`).not.toThrow();
    }
    // A warning here means a row resolved to the generic fallback — i.e. an
    // unmapped type slipped through. Coverage above should preempt it.
    expect(warn).not.toHaveBeenCalled();
    warn.mockRestore();
  });
});

describe("narrateEvent — no vocabulary leak (rigor: no substrate noun reaches a line)", () => {
  // The banned tokens that must never appear in a rendered narration line.
  // Mirrors the spirit of copyLint's BANNED_PATTERNS for the dynamic case
  // (copyLint scans source; this scans the produced strings for every type).
  const BANNED = [
    /\bphase\s*\d/i, // "phase 2"
    /\bdispatch\b/i,
    /\bsynthesizer\b/i,
    /\bdecomposer\b/i,
    /\bchunk/i,
    /\baction_type\b/i,
    /\binv-[0-9a-f]{6,}/i, // a raw investigation id
    /_/, // any snake_case token (action types, role names, enum values)
  ];

  it("no narrated line contains a substrate noun, phase number, or raw id", () => {
    for (const t of ALL_ACTION_TYPES) {
      // Feed a payload rich enough to exercise the payload-reading branches,
      // including a value that, if leaked verbatim, would trip the lint.
      const n = narrateEvent(
        eventOf(t, {
          question: "What changed my mind?",
          sub_question: "Which side is better grounded?",
          decomposition: [{}, {}],
          supporting_claims: [{}],
          evidentiary_gaps: [{}],
          paths: [{}],
          final_status: "passed",
          question_text: "An open question",
        }),
      );
      if (!n) continue;
      for (const pat of BANNED) {
        expect(
          pat.test(n.line),
          `narration for ${t} leaks a banned token: ${JSON.stringify(n.line)} (matched ${pat})`,
        ).toBe(false);
      }
    }
  });
});

describe("narrateEvent — honesty (a line claims only what the event asserts)", () => {
  it("a retrieval that returned points says 'found supporting points', not 'found a strong source'", () => {
    const n = narrateEvent(
      eventOf(ActionType.EVIDENCE_RETRIEVE_DELIVERED, { supporting_claims: [{}, {}], evidentiary_gaps: [] }),
    );
    expect(n?.line).toMatch(/2 supporting points/i);
    expect(n?.line).not.toMatch(/strong/i);
  });

  it("an insufficient-evidence retrieval reads as a caution, not a finding", () => {
    const n = narrateEvent(
      eventOf(ActionType.EVIDENCE_RETRIEVE_DELIVERED, { insufficient_evidence: true, supporting_claims: [], evidentiary_gaps: [{}] }),
    );
    expect(n?.tone).toBe("caution");
    expect(n?.line).toMatch(/came up short/i);
  });

  it("a constraint loop that didn't converge is honest about it", () => {
    const n = narrateEvent(eventOf(ActionType.CONSTRAINT_LOOP_RESOLVED, { final_status: "max_iterations_reached" }));
    expect(n?.tone).toBe("caution");
    expect(n?.line).toMatch(/couldn’t fully reconcile/i);
  });

  it("dispatch.call is suppressed — the cost meter owns it, never a line", () => {
    expect(narrateEvent(eventOf(ActionType.DISPATCH_CALL, { cost_usd: 0.01 }))).toBeNull();
  });

  it("start narrates with the question when present", () => {
    const n = narrateEvent(eventOf(ActionType.INVESTIGATION_START_REQUESTED, { question: "Why?" }));
    expect(n?.line).toMatch(/Why\?/);
    expect(n?.tone).toBe("milestone");
  });
});

describe("narrateEvent — totality (an unknown type degrades, never crashes)", () => {
  it("an action_type with no row returns the generic beat and warns once", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const n = narrateEvent(eventOf("totally.invented.type.not.in.catalogue"));
    expect(n).toEqual({ line: "Working…", tone: "step" });
    expect(warn).toHaveBeenCalledOnce();
    warn.mockRestore();
  });
});
