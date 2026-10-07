/**
 * agentStatus.test.ts — SPR-10 M1: the five states, the attention order,
 * the Map-backed mapping table, done/idle from seen timestamps, the run
 * entry census over the context tree, and the toast transition matrix.
 *
 * Property checks use a seeded xorshift32 loop (no fast-check in the tree).
 */
import { describe, expect, it } from "vitest";

import { composePreBackendTree } from "../contracts/adapters/preBackend";
import { EMPTY_TREE } from "../contracts/treeStore";
import { fixtureInputs, summary, tab } from "../contracts/fixtures.test.helpers";
import {
  AGENT_STATUSES,
  ATTENTION_RANK,
  INVESTIGATION_PHASE_TABLE,
  attentionOf,
  collectRuns,
  phaseOf,
  rankOf,
  rollup,
  toastFor,
  type AgentStatus,
  type RawObservation,
} from "./agentStatus";

function xorshift32(seed: number): () => number {
  let x = seed >>> 0 || 1;
  return () => {
    x ^= x << 13; x >>>= 0;
    x ^= x >>> 17;
    x ^= x << 5; x >>>= 0;
    return x / 0x1_0000_0000;
  };
}

const WIRE = ["in_progress", "completed", "failed", "stopped", "not_found"] as const;
const PROTO_KEYS = ["constructor", "toString", "__proto__", "hasOwnProperty", "valueOf"];

function raw(over: Partial<RawObservation> = {}): RawObservation {
  return { status: "completed", completedAt: "2026-10-07T10:00:00Z", since: "2026-10-07T10:00:00Z", title: "t", observedAt: 0, ...over };
}

function randomString(rnd: () => number): string {
  const n = Math.floor(rnd() * 12);
  let s = "";
  for (let i = 0; i < n; i++) s += String.fromCharCode(32 + Math.floor(rnd() * 95));
  return s;
}

describe("the five states in attention order", () => {
  it("AGENT_STATUSES has five members in strictly descending ATTENTION_RANK, ranks exactly {4,3,2,1,0}", () => {
    expect(AGENT_STATUSES).toHaveLength(5);
    const ranks = AGENT_STATUSES.map(rankOf);
    for (let i = 1; i < ranks.length; i++) expect(ranks[i]).toBeLessThan(ranks[i - 1]);
    expect([...ranks].sort((a, b) => b - a)).toEqual([4, 3, 2, 1, 0]);
    expect(ATTENTION_RANK).toEqual({ blocked: 4, done: 3, working: 2, idle: 1, unknown: 0 });
  });

  it("rollup is the max by rank over 1000 seeded multisets; empty → null; unknown never wins against another state", () => {
    const rnd = xorshift32(0x5eed);
    for (let i = 0; i < 1000; i++) {
      const n = 1 + Math.floor(rnd() * 6);
      const xs: AgentStatus[] = [];
      for (let j = 0; j < n; j++) xs.push(AGENT_STATUSES[Math.floor(rnd() * 5)]);
      const r = rollup(xs);
      expect(r).not.toBeNull();
      expect(xs).toContain(r);
      for (const x of xs) expect(rankOf(r!)).toBeGreaterThanOrEqual(rankOf(x));
      if (xs.some((x) => x !== "unknown")) expect(r).not.toBe("unknown");
    }
    expect(rollup([])).toBeNull();
    expect(rollup(["unknown", "unknown"])).toBe("unknown");
  });
});

describe("the mapping table is a Map and total against prototype keys", () => {
  it("the five wire statuses map to the documented rows", () => {
    expect(phaseOf("in_progress")).toEqual({ phase: "working" });
    expect(phaseOf("completed")).toEqual({ phase: "finished" });
    expect(phaseOf("failed")).toEqual({ phase: "finished", detail: "failed" });
    expect(phaseOf("stopped")).toEqual({ phase: "finished", detail: "stopped" });
    expect(phaseOf("not_found")).toEqual({ phase: "unknown", detail: "not_found" });
    expect(INVESTIGATION_PHASE_TABLE instanceof Map).toBe(true);
    expect(INVESTIGATION_PHASE_TABLE.size).toBe(5);
  });

  it('"", undefined, 200 random strings and the prototype keys → unknown, never idle, never a throw', () => {
    const rnd = xorshift32(7);
    const probes: (string | undefined)[] = ["", undefined, ...PROTO_KEYS];
    for (let i = 0; i < 200; i++) probes.push(randomString(rnd));
    for (const p of probes) {
      if (WIRE.includes(p as (typeof WIRE)[number])) continue;
      expect(() => phaseOf(p)).not.toThrow();
      expect(phaseOf(p).phase, JSON.stringify(p)).toBe("unknown");
      const a = attentionOf(raw({ status: p }), null);
      expect(a.state, JSON.stringify(p)).toBe("unknown");
      expect(a.state).not.toBe("idle");
    }
  });
});

describe("the false-blocked lens: blocked only through needsInput", () => {
  it("never blocked without needsInput, for every wire status, undefined and random strings", () => {
    const rnd = xorshift32(99);
    const probes: (string | undefined)[] = [...WIRE, undefined, "", ...PROTO_KEYS];
    for (let i = 0; i < 100; i++) probes.push(randomString(rnd));
    for (const p of probes) {
      for (const seen of [null, "2026-10-07T09:00:00Z", "2026-10-07T11:00:00Z"]) {
        expect(attentionOf(raw({ status: p }), seen).state, JSON.stringify(p)).not.toBe("blocked");
      }
    }
    expect(attentionOf(undefined, null).state).not.toBe("blocked");
  });

  it("needsInput: true with any status → blocked", () => {
    for (const p of [...WIRE, undefined, "", "garbage"]) {
      expect(attentionOf(raw({ status: p, needsInput: true }), "2026-10-07T11:00:00Z").state, JSON.stringify(p)).toBe("blocked");
    }
  });
});

describe("done until viewed, then idle", () => {
  const done = "2026-10-07T10:00:00Z";
  it("completed: lastSeen null → done; after → idle; before → done; unparsable completedAt → done", () => {
    expect(attentionOf(raw({ status: "completed", completedAt: done }), null)).toEqual({ state: "done" });
    expect(attentionOf(raw({ status: "completed", completedAt: done }), "2026-10-07T10:00:01Z")).toEqual({ state: "idle" });
    expect(attentionOf(raw({ status: "completed", completedAt: done }), "2026-10-07T09:59:59Z")).toEqual({ state: "done" });
    expect(attentionOf(raw({ status: "completed", completedAt: "not a date" }), "2026-10-07T10:00:01Z")).toEqual({ state: "done" });
  });

  it("failed uses completedAt ?? since and carries reason failed", () => {
    expect(attentionOf(raw({ status: "failed", completedAt: null, since: done }), null)).toEqual({ state: "done", reason: "failed" });
    expect(attentionOf(raw({ status: "failed", completedAt: null, since: done }), "2026-10-07T10:00:01Z")).toEqual({ state: "idle", reason: "failed" });
    expect(attentionOf(raw({ status: "failed", completedAt: done, since: "2026-10-07T01:00:00Z" }), "2026-10-07T05:00:00Z")).toEqual({ state: "done", reason: "failed" });
  });

  it("stopped → idle/stopped; not_found → unknown/not_found; in_progress → working; absent → unknown with the caller's reason", () => {
    expect(attentionOf(raw({ status: "stopped" }), null)).toEqual({ state: "idle", reason: "stopped" });
    expect(attentionOf(raw({ status: "not_found" }), null)).toEqual({ state: "unknown", reason: "not_found" });
    expect(attentionOf(raw({ status: "in_progress" }), null)).toEqual({ state: "working" });
    expect(attentionOf(undefined, null, "no-run")).toEqual({ state: "unknown", reason: "no-run" });
    expect(attentionOf(undefined, null, "outside-window")).toEqual({ state: "unknown", reason: "outside-window" });
    expect(attentionOf(undefined, null)).toEqual({ state: "unknown", reason: "outside-window" });
  });
});

describe("collectRuns over the context tree", () => {
  const investigations = [
    summary("inv-open", { status: "in_progress", completed_at: null, question: "Open one" }),
    summary("inv-closed", { status: "completed", question: "Closed one" }),
  ];

  it("an investigation node without a tab → one entry, viewOpen false; the same investigation with a tab → the SAME runId, viewOpen true, never two", () => {
    const noTabs = collectRuns(composePreBackendTree(fixtureInputs({ investigations, companionTabs: [] })));
    expect(noTabs.get("inv-open")).toMatchObject({ runId: "inv-open", viewId: "agent:thread:inv-open", viewOpen: false, kind: "research-thread", investigationId: "inv-open", title: "Open one", treeState: "in_progress" });
    expect(noTabs.get("inv-open")!.groupPath).toEqual(["default", "inv-open"]);

    const withTab = collectRuns(composePreBackendTree(fixtureInputs({ investigations, companionTabs: [tab("research-thread", { investigationId: "inv-open", title: "Open one tab" })] })));
    const entries = [...withTab.values()].filter((e) => e.investigationId === "inv-open");
    expect(entries).toHaveLength(1);
    expect(entries[0]).toMatchObject({ runId: "inv-open", viewId: "agent:thread:inv-open", viewOpen: true, title: "Open one tab" });
    expect(withTab.get("inv-closed")!.viewOpen).toBe(false);
  });

  it("dialogue → kind dialogue, no investigationId, groupPath [] (cross-project)", () => {
    const t = collectRuns(composePreBackendTree(fixtureInputs({ investigations, companionTabs: [tab("dialogue")] })));
    const d = t.get("agent:dialogue")!;
    expect(d).toMatchObject({ runId: "agent:dialogue", viewId: "agent:dialogue", viewOpen: true, kind: "dialogue", projectId: null });
    expect(d.investigationId).toBeUndefined();
    expect(d.groupPath).toEqual([]);
    expect(d.treeState).toBeUndefined();
  });

  it("tree status error with roots still yields entries; unfed → empty", () => {
    const ready = composePreBackendTree(fixtureInputs({ investigations, companionTabs: [] }));
    const errored = { ...ready, status: "error" as const, error: "boom" };
    expect(collectRuns(errored).size).toBe(collectRuns(ready).size);
    expect(collectRuns(EMPTY_TREE).size).toBe(0);
  });

  it("a linked agent sits on its own investigation node: the entry's groupPath walks root → project → node", () => {
    const linked = composePreBackendTree(fixtureInputs({
      investigations: [summary("inv-member", { status: "in_progress", completed_at: null })],
      companionTabs: [tab("research-thread", { investigationId: "inv-member", title: "member" })],
      membersByProject: new Map([["p1", [{ member_kind: "investigation", member_id: "inv-member", added_at: "2026-09-18T10:00:00Z" }]]]),
    }));
    const e = collectRuns(linked).get("inv-member")!;
    expect(e.viewOpen).toBe(true);
    expect(e.projectId).toBe("inv-member");
    expect(e.groupPath).toEqual(["p1", "inv-member"]);
    expect(e.rootTitle).toBe("Varda diligence");
  });
});

describe("toastFor: the transition matrix", () => {
  const STATES: readonly (AgentStatus | undefined)[] = [undefined, ...AGENT_STATUSES];

  it("5×5 (+undefined) × {active, inactive} × {grace, no grace}: needs-you only on *→blocked with prev defined and no grace; finished only on working→done inactive and no grace", () => {
    for (const prev of STATES) for (const next of AGENT_STATUSES) for (const isActiveView of [true, false]) for (const inStartupGrace of [true, false]) {
      const t = toastFor(prev, next, { isActiveView, inStartupGrace });
      const label = `${prev}→${next} active=${isActiveView} grace=${inStartupGrace}`;
      if (next === "blocked" && prev !== "blocked" && prev !== undefined && !inStartupGrace) expect(t, label).toEqual({ kind: "needs-you" });
      else if (prev === "working" && next === "done" && !isActiveView && !inStartupGrace) expect(t, label).toEqual({ kind: "finished" });
      else expect(t, label).toBeNull();
    }
  });

  it("first observation and unchanged are null", () => {
    for (const x of AGENT_STATUSES) {
      expect(toastFor(undefined, x, { isActiveView: false, inStartupGrace: false })).toBeNull();
      expect(toastFor(x, x, { isActiveView: false, inStartupGrace: false })).toBeNull();
    }
  });

  it("graft 6: no wire status without needsInput ever yields needs-you, from every prev (failed and stopped included)", () => {
    const rnd = xorshift32(1234);
    const probes: (string | undefined)[] = [...WIRE, undefined, "", ...PROTO_KEYS];
    for (let i = 0; i < 50; i++) probes.push(randomString(rnd));
    for (const p of probes) {
      const next = attentionOf(raw({ status: p }), null).state;
      for (const prev of STATES) {
        const t = toastFor(prev, next, { isActiveView: false, inStartupGrace: false });
        expect(t?.kind, `${prev}→${JSON.stringify(p)}`).not.toBe("needs-you");
      }
    }
  });
});
