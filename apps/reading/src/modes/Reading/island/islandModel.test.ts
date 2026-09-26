/**
 * islandModel.test.ts — the pure model proofs (island SPR-01).
 *
 *   - deriveIslandRefs: only thread-linked anchors become islands, with the
 *     passage identity + servability intact.
 *   - islandStatus: the EXPLICIT TOTAL mapping — every projection status
 *     (5) crossed with every ResearchRunState (8) and null appears in a
 *     case, and the terminal authority order holds (gone > budget_halted >
 *     failed > stopped > complete/complete_empty > live). An unmapped
 *     future input fails loudly (assertNever).
 *   - selectIslandFamily: a root with two chases and one grand-chase
 *     extracts exactly that subtree — and the useInvestigationTree merge
 *     rule (substrate parent ids WIN over a forged localStorage map) is
 *     exercised, not assumed.
 */
import { afterEach, describe, expect, it } from "vitest";

import type { ResearchRunState } from "../../../api/research";
import type { BookAnchor, InvestigationSummary } from "../../../lib/api";
import { useInvestigationTree } from "../../../hooks/useInvestigationTree";
import { renderHook } from "@testing-library/react";
import {
  deriveIslandRefs,
  islandStatus,
  selectIslandFamily,
  type IslandStatusInput,
} from "./islandModel";

function anchor(over: Partial<BookAnchor> = {}): BookAnchor {
  return {
    anchor_id: "a-1",
    document_id: "doc-1",
    anchor: {
      normalization: "unicode-nfc-v1",
      node_id: "c-1",
      node_text_sha256: "h".repeat(64),
      start_scalar: 10,
      end_scalar: 21,
      quote: "the passage",
      prefix: "",
      suffix: "",
    },
    servable_at_pin: true,
    selection_text_sha256: "s".repeat(64),
    page_index_hint: 0,
    source: "floatmenu_deep_research",
    status: "active",
    exact_valid: true,
    investigation_id: null,
    created_at: "2026-09-24T10:00:00Z",
    updated_at: "2026-09-24T10:00:00Z",
    ...over,
  };
}

describe("deriveIslandRefs", () => {
  it("only anchors with a thread link become islands; plain highlights never do", () => {
    const refs = deriveIslandRefs([
      anchor({ investigation_id: "inv-1" }),
      anchor({ anchor_id: "a-2" }),
      anchor({ anchor_id: "a-3", investigation_id: "inv-3", servable_at_pin: false }),
    ]);
    expect(refs).toHaveLength(2);
    expect(refs[0]).toEqual({
      anchorId: "a-1",
      documentId: "doc-1",
      passageAnchor: { chunkId: "c-1", start: 10, end: 21 },
      investigationId: "inv-1",
      servable: true,
    });
    expect(refs[1].servable).toBe(false);
  });
});

// ── The total status mapping ──────────────────────────────────────────────

const PROJECTIONS = ["loading", "in_progress", "completed", "failed", "not_found", null] as const;
const SESSIONS: (ResearchRunState | null)[] = [
  "pending",
  "running",
  "paused",
  "stopping",
  "done",
  "stopped",
  "failed",
  "budget_halted",
  null,
];

function expected(input: IslandStatusInput): string {
  if (input.projection === "not_found") return "gone";
  if (input.session === "budget_halted") return "budget_halted";
  if (input.session === "failed") return "failed";
  if (input.session === "stopped") return "stopped";
  if (input.projection === "failed" || input.summary === "failed") return "failed";
  if (input.summary === "stopped") return "stopped";
  if (input.session === "done" || input.projection === "completed" || input.summary === "completed") {
    return input.insightCount === 0 ? "complete_empty" : "complete";
  }
  return "live";
}

describe("islandStatus — the exhaustive mapping", () => {
  it("every projection × session combination maps to exactly one island status", () => {
    const cases: string[] = [];
    for (const projection of PROJECTIONS) {
      for (const session of SESSIONS) {
        const input: IslandStatusInput = {
          projection,
          summary: null,
          session,
          insightCount: 3,
        };
        const mapped = islandStatus(input);
        const want = expected(input);
        expect(mapped, `${projection ?? "null"} × ${session ?? "null"}`).toBe(want);
        cases.push(`${projection}:${session}=${mapped}`);
      }
    }
    // 6 × 9 = 54 cases, every one named and checked — an unmapped future
    // state fails here loudly, never silently.
    expect(cases).toHaveLength(54);
  });

  it("gone: a missing trajectory is honest gone, whatever the session says", () => {
    expect(
      islandStatus({ projection: "not_found", summary: "in_progress", session: "running", insightCount: null }),
    ).toBe("gone");
  });

  it("completed-with-insights is complete; completed-empty is complete_empty (not an error)", () => {
    expect(
      islandStatus({ projection: "completed", summary: null, session: null, insightCount: 2 }),
    ).toBe("complete");
    expect(
      islandStatus({ projection: "completed", summary: null, session: null, insightCount: 0 }),
    ).toBe("complete_empty");
    expect(
      islandStatus({ projection: null, summary: "completed", session: "done", insightCount: 0 }),
    ).toBe("complete_empty");
  });

  it("failed / stopped / budget_halted each read their honest terminal", () => {
    expect(islandStatus({ projection: "failed", summary: null, session: null, insightCount: null })).toBe("failed");
    expect(islandStatus({ projection: "in_progress", summary: "stopped", session: null, insightCount: null })).toBe("stopped");
    expect(islandStatus({ projection: "in_progress", summary: null, session: "budget_halted", insightCount: null })).toBe("budget_halted");
  });

  it("live covers loading, in_progress, and every non-terminal session state", () => {
    for (const input of [
      { projection: "loading" as const, summary: null, session: null, insightCount: null },
      { projection: "in_progress" as const, summary: "in_progress" as const, session: "running" as const, insightCount: null },
      { projection: null, summary: null, session: "paused" as const, insightCount: null },
      { projection: null, summary: null, session: "stopping" as const, insightCount: null },
      { projection: null, summary: null, session: "pending" as const, insightCount: null },
    ]) {
      expect(islandStatus(input)).toBe("live");
    }
  });

  it("an unmapped future input fails loudly (assertNever, never a silent live)", () => {
    expect(() =>
      islandStatus({
        projection: "brand_new_state" as never,
        summary: null,
        session: null,
        insightCount: null,
      }),
    ).toThrow(/unmapped island status input/);
  });
});

// ── The family selector + the tree merge rule ─────────────────────────────

function summary(id: string, parent: string | null, status = "in_progress"): InvestigationSummary {
  return {
    investigation_id: id,
    question: `q-${id}`,
    status: status as InvestigationSummary["status"],
    started_at: "2026-09-24T10:00:00Z",
    completed_at: null,
    cost_usd_total: 0.1,
    parent_investigation_id: parent,
  };
}

describe("selectIslandFamily", () => {
  afterEach(() => {
    window.localStorage.removeItem("antiek:investigation_tree");
  });

  it("a root with two chases and one grand-chase extracts exactly that subtree", () => {
    const investigations = [
      summary("root", null),
      summary("chase-1", "root"),
      summary("chase-2", "root"),
      summary("grand-1", "chase-2"),
      summary("other", null),
    ];
    const { result } = renderHook(() => useInvestigationTree(investigations));
    const family = selectIslandFamily(result.current, "chase-1");
    expect(family.map((n) => n.investigationId)).toEqual(["root", "chase-1", "chase-2", "grand-1"]);
    expect(family.map((n) => n.depth)).toEqual([0, 1, 1, 2]);
    expect(family.find((n) => n.investigationId === "other")).toBeUndefined();
  });

  it("substrate parent ids WIN over a forged localStorage map (the merge rule, exercised)", () => {
    // Forge: localStorage claims grand-1's parent is "other" — a wrong parent.
    window.localStorage.setItem(
      "antiek:investigation_tree",
      JSON.stringify({ "grand-1": "other" }),
    );
    const investigations = [
      summary("root", null),
      summary("chase-2", "root"),
      summary("grand-1", "chase-2"), // the substrate's truth
      summary("other", null),
    ];
    const { result } = renderHook(() => useInvestigationTree(investigations));
    // The tree must hang grand-1 under chase-2 (substrate), never "other".
    const family = selectIslandFamily(result.current, "root");
    expect(family.map((n) => n.investigationId)).toEqual(["root", "chase-2", "grand-1"]);
    expect(family.find((n) => n.investigationId === "grand-1")?.depth).toBe(2);
  });

  it("an investigation outside the loaded list is the honest single node", () => {
    const family = selectIslandFamily([], "inv-missing");
    expect(family).toEqual([]);
  });
});
