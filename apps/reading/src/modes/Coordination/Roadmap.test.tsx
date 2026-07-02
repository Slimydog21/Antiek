import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { Roadmap } from "./Roadmap";
import type {
  DependencyBlockerView,
  ExecutionFocusView,
  RoadmapView,
  SprintView,
} from "./Roadmap";

afterEach(() => {
  cleanup();
});

function drwStatus(n: number): string {
  if (n <= 4) return "live";
  if (n === 10) return "transferred";
  return "planned";
}

function slugForSprint(spec: "drw" | "read", n: number): string {
  if (spec !== "drw") return `${spec}-sprint-${n}`;
  if (n === 1) return "insight-question-nodes";
  if (n === 3) return "async-note-taker";
  if (n === 5) return "cascade-planner";
  if (n === 10) return "reading-surface";
  return `${spec}-sprint-${n}`;
}

function sprint(
  n: number,
  blockedOn: string[],
  unblocked = false,
  spec: "drw" | "read" = "read",
): SprintView {
  return {
    spec,
    spec_label: spec === "drw" ? "Research (DRW)" : "Read",
    sprint: n,
    slug: slugForSprint(spec, n),
    node_id: `${spec}:${n}`,
    status: spec === "drw" ? drwStatus(n) : "unknown",
    on_critical_path: false,
    blocked_on: blockedOn,
    unblocked,
  };
}

function roadmap(
  sprints: SprintView[],
  unblockedNow: string[] = [],
  dependencyBlockers: DependencyBlockerView[] = [],
  criticalPath: string[] = [],
  executionFocus: ExecutionFocusView | null = null,
): RoadmapView {
  const specs: Array<"drw" | "read"> = ["drw", "read"];
  return {
    total_sprints: sprints.length,
    superseded_count: 0,
    superseded_note: "",
    activation_note:
      "Structural sprint status is not activation closure. Read activation still requires the live dogfood evidence in specs/activation/golden-path.md; CI is the floor, use is the gate.",
    reconciliation: `Read ${sprints.length} = ${sprints.length}`,
    critical_path: criticalPath,
    rosters: specs.flatMap((spec) => {
      const rows = sprints.filter((s) => s.spec === spec);
      if (rows.length === 0) return [];
      return [
        {
          spec,
          label: spec === "drw" ? "Research (DRW)" : "Read",
          directory: spec === "drw" ? "deep-research-workspace" : "read",
          count: rows.length,
          sprints: rows,
        },
      ];
    }),
    unblocked_now: unblockedNow,
    dependency_blockers: dependencyBlockers,
    execution_focus: executionFocus,
    operator_gate_focus: null,
    read_activation: null,
    operator_actions: null,
    phase2_audit: null,
    engineering_deferrals: null,
    loop3: null,
    source_gate: null,
    substrate_layers: [],
  };
}

describe("Roadmap", () => {
  it("renders dependency-ready empty state and blocker summary", () => {
    render(
      <Roadmap
        roadmap={roadmap([
          sprint(5, [], true, "drw"),
          sprint(1, ["drw:5"]),
        ])}
      />,
    );

    expect(
      screen.getByText("0 dependency-ready · 1 blocked by dependency state"),
    ).toBeTruthy();
    expect(
      screen.getByText(/Structural sprint status is not activation closure/),
    ).toBeTruthy();
    expect(
      screen.getByText(/specs\/activation\/golden-path\.md/),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "No sprint is dependency-ready under the current dependency state.",
      ),
    ).toBeTruthy();
    expect(screen.getByText("Dependency blockers")).toBeTruthy();
    expect(screen.getByText("Execution focus")).toBeTruthy();
    expect(
      screen.getByText("Unblock drw:5 — Research (DRW) · SPR-05"),
    ).toBeTruthy();
    expect(
      screen.getByText("Clears dependency pressure for 1 sprint."),
    ).toBeTruthy();
    expect(screen.getByText("drw:5")).toBeTruthy();
    expect(
      screen.getByText("Research (DRW) · SPR-05 · cascade planner · planned"),
    ).toBeTruthy();
    expect(screen.getByText("Read · SPR-01")).toBeTruthy();
    expect(screen.getByText("blocks 1 sprint")).toBeTruthy();
    expect(screen.getByText("waits on drw:5")).toBeTruthy();
  });

  it("resolves critical path nodes to sprint labels", () => {
    render(
      <Roadmap
        roadmap={roadmap(
          [
            sprint(1, [], true, "drw"),
            sprint(3, [], true, "drw"),
            sprint(10, [], true, "drw"),
          ],
          ["drw:1", "drw:3", "drw:10"],
          [],
          ["drw:1", "drw:3", "drw:10"],
        )}
      />,
    );

    expect(screen.getByText("DRW critical path")).toBeTruthy();
    expect(
      screen.getByText("Research (DRW) · SPR-01 · insight question nodes · live"),
    ).toBeTruthy();
    expect(
      screen.getByText("Research (DRW) · SPR-03 · async note taker · live"),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "Research (DRW) · SPR-10 · reading surface · transferred",
      ),
    ).toBeTruthy();
  });

  it("surfaces stale critical path ids without inventing sprint labels", () => {
    render(<Roadmap roadmap={roadmap([], [], [], ["drw:99"])} />);

    expect(screen.getByText("drw:99")).toBeTruthy();
    expect(screen.getByText("not found in sprint roster")).toBeTruthy();
    expect(screen.getByText(/this DRW spine/)).toBeTruthy();
  });

  it("omits dependency blockers when every sprint is dependency-ready", () => {
    render(<Roadmap roadmap={roadmap([sprint(1, [], true)], ["read:1"])} />);

    expect(
      screen.getByText("1 dependency-ready · 0 blocked by dependency state"),
    ).toBeTruthy();
    expect(
      screen.getByText("Next dependency-ready sprint: Read · SPR-01"),
    ).toBeTruthy();
    expect(screen.getByText("read sprint 1 · read:1")).toBeTruthy();
    expect(screen.queryByText("Dependency blockers")).toBeNull();
  });

  it("sorts blocker fan-out, truncates samples, and dedupes duplicate waits", () => {
    render(
      <Roadmap
        roadmap={roadmap(
          [
            sprint(5, [], true, "drw"),
            sprint(6, [], true, "drw"),
            sprint(1, ["drw:5", "drw:5"]),
            sprint(2, ["drw:5"]),
            sprint(3, ["drw:5"]),
            sprint(4, ["drw:5"]),
            sprint(5, ["drw:6"]),
          ],
          [],
          [
            { node_id: "drw:6", blocked_sprints: ["read:5"] },
            {
              node_id: "drw:5",
              blocked_sprints: [
                "read:1",
                "read:1",
                "read:2",
                "read:3",
                "read:4",
              ],
            },
            { node_id: "missing:9", blocked_sprints: ["read:1"] },
          ],
        )}
      />,
    );

    const text = document.body.textContent ?? "";
    expect(text.indexOf("drw:5")).toBeLessThan(text.indexOf("drw:6"));
    expect(screen.getByText("blocks 4 sprints")).toBeTruthy();
    expect(screen.getByText("blocks 1 sprint")).toBeTruthy();
    expect(
      screen.getByText("Unblock drw:5 — Research (DRW) · SPR-05"),
    ).toBeTruthy();
    expect(
      screen.getByText("Clears dependency pressure for 4 sprints."),
    ).toBeTruthy();
    expect(
      screen.getByText("Research (DRW) · SPR-05 · cascade planner · planned"),
    ).toBeTruthy();
    expect(
      screen.getByText("Read · SPR-01, Read · SPR-02, Read · SPR-03 +1 more"),
    ).toBeTruthy();
  });

  it("falls back to roster truth when API blockers are partial or duplicated", () => {
    render(
      <Roadmap
        roadmap={roadmap(
          [
            sprint(1, ["drw:5"]),
            sprint(2, ["drw:5"]),
            sprint(3, ["drw:6"]),
          ],
          [],
          [
            { node_id: "drw:5", blocked_sprints: ["read:1"] },
            { node_id: "drw:5", blocked_sprints: ["read:2"] },
          ],
        )}
      />,
    );

    expect(screen.getAllByText("blocks 2 sprints")).toHaveLength(1);
    expect(screen.getByText("blocks 1 sprint")).toBeTruthy();
    expect(screen.getByText("Read · SPR-01, Read · SPR-02")).toBeTruthy();
    expect(screen.getByText("Read · SPR-03")).toBeTruthy();
  });

  it("prefers blocker focus over dependency-ready rows", () => {
    render(
      <Roadmap
        roadmap={roadmap(
          [
            sprint(5, [], true, "drw"),
            sprint(1, [], true),
            sprint(2, ["drw:5"]),
          ],
          ["read:1"],
        )}
      />,
    );

    expect(
      screen.getByText("Unblock drw:5 — Research (DRW) · SPR-05"),
    ).toBeTruthy();
    expect(screen.queryByText("Next dependency-ready sprint: Read · SPR-01")).toBeNull();
  });

  it("uses valid API execution focus and falls back when it is stale", () => {
    const rows = [
      sprint(5, [], true, "drw"),
      sprint(6, [], true, "drw"),
      sprint(1, ["drw:5"]),
      sprint(2, ["drw:5"]),
      sprint(3, ["drw:6"]),
    ];

    const { rerender } = render(
      <Roadmap
        roadmap={roadmap(
          rows,
          [],
          [
            { node_id: "drw:5", blocked_sprints: ["read:1", "read:2"] },
            { node_id: "drw:6", blocked_sprints: ["read:3"] },
          ],
          [],
          {
            kind: "dependency_blocker",
            node_id: "drw:5",
            blocked_sprints: ["read:2", "read:1"],
          },
        )}
      />,
    );

    expect(
      screen.getByText("Unblock drw:5 — Research (DRW) · SPR-05"),
    ).toBeTruthy();
    expect(
      screen.getByText("Clears dependency pressure for 2 sprints."),
    ).toBeTruthy();

    rerender(
      <Roadmap
        roadmap={roadmap(
          rows,
          [],
          [
            { node_id: "drw:5", blocked_sprints: ["read:1", "read:2"] },
            { node_id: "drw:6", blocked_sprints: ["read:3"] },
          ],
          [],
          {
            kind: "dependency_blocker",
            node_id: "drw:6",
            blocked_sprints: ["read:3"],
          },
        )}
      />,
    );

    expect(
      screen.getByText("Unblock drw:5 — Research (DRW) · SPR-05"),
    ).toBeTruthy();
    expect(
      screen.getByText("Clears dependency pressure for 2 sprints."),
    ).toBeTruthy();

    rerender(
      <Roadmap
        roadmap={roadmap(
          rows,
          [],
          [
            { node_id: "drw:5", blocked_sprints: ["read:1", "read:2"] },
            { node_id: "drw:6", blocked_sprints: ["read:3"] },
          ],
          [],
          {
            kind: "dependency_blocker",
            node_id: "drw:5",
            blocked_sprints: ["read:1"],
          },
        )}
      />,
    );

    expect(
      screen.getByText("Unblock drw:5 — Research (DRW) · SPR-05"),
    ).toBeTruthy();
    expect(
      screen.getByText("Clears dependency pressure for 2 sprints."),
    ).toBeTruthy();
    expect(screen.queryByText("Clears dependency pressure for 1 sprint.")).toBeNull();
    expect(screen.queryByText("Unblock drw:6")).toBeNull();
  });

  it("uses valid dependency-ready API focus and falls back when it is stale", () => {
    const rows = [sprint(1, [], true), sprint(2, [], true)];
    const { rerender } = render(
      <Roadmap
        roadmap={roadmap(rows, ["read:1", "read:2"], [], [], {
          kind: "dependency_ready",
          node_id: "read:1",
        })}
      />,
    );

    expect(
      screen.getByText("Next dependency-ready sprint: Read · SPR-01"),
    ).toBeTruthy();
    expect(screen.getByText("read sprint 1 · read:1")).toBeTruthy();

    rerender(
      <Roadmap
        roadmap={roadmap(rows, ["read:1", "read:2"], [], [], {
          kind: "dependency_ready",
          node_id: "read:2",
        })}
      />,
    );

    expect(
      screen.getByText("Next dependency-ready sprint: Read · SPR-01"),
    ).toBeTruthy();
    expect(screen.getByText("read sprint 1 · read:1")).toBeTruthy();
    expect(screen.queryByText("Next dependency-ready sprint: Read · SPR-02")).toBeNull();
  });

  it("hides execution focus when there is no blocker and no dependency-ready row", () => {
    render(<Roadmap roadmap={roadmap([])} />);

    expect(screen.queryByText("Execution focus")).toBeNull();
  });

  it("falls through to the first open operator gate when structural focus is clear", () => {
    render(
      <Roadmap
        roadmap={{
          ...roadmap([]),
          operator_gate_focus: {
            gate_id: "G2",
            title: "Lawyer review",
            status: "open",
            status_raw: "OPEN — counsel review pending",
            owner: "Operator + counsel",
            blocks: "All Stripe payouts",
            source_path: "docs/operator_gate_actions.md",
          },
        }}
      />,
    );

    expect(screen.getByText("Execution focus")).toBeTruthy();
    expect(screen.getByText("Close G2 — Lawyer review")).toBeTruthy();
    expect(
      screen.getByText("OPEN — counsel review pending · Operator + counsel"),
    ).toBeTruthy();
    expect(screen.getByText("Blocks: All Stripe payouts")).toBeTruthy();
    expect(screen.getByText(/docs\/operator_gate_actions\.md/)).toBeTruthy();
  });

  it("shows Read activation dogfood counters without treating them as closure", () => {
    render(
      <Roadmap
        roadmap={{
          ...roadmap([]),
          read_activation: {
            source_path: "reports/read-dogfood.jsonl",
            state: "incomplete",
            total_sessions: 2,
            valid_sessions: 1,
            invalid_session_count: 1,
            live_provider_sessions: 0,
            citation_trace_sessions: 1,
            non_library_sessions: 0,
            final_verdict: null,
            closure_ready: false,
            remaining_requirements: {
              valid_sessions: 9,
              live_provider_sessions: 5,
              citation_trace_sessions: 2,
              non_library_sessions: 1,
            },
            failures: ["session-2 malformed"],
          },
        }}
      />,
    );

    expect(screen.getByText("Read activation dogfood")).toBeTruthy();
    expect(
      screen.getByText(
        "1/2 valid · 0 live-provider · 1 citation-traced · 0 non-library · verdict=missing",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText("Remaining: 9 valid, 5 live-provider, 2 citation-traced, 1 non-library. Source: reports/read-dogfood.jsonl."),
    ).toBeTruthy();
    expect(screen.getByText("1 invalid session need repair.")).toBeTruthy();
  });

  it("surfaces malformed dogfood logs as repair work", () => {
    render(
      <Roadmap
        roadmap={{
          ...roadmap([]),
          read_activation: {
            source_path: "reports/read-dogfood.jsonl",
            state: "invalid_log",
            total_sessions: 0,
            valid_sessions: 0,
            invalid_session_count: 0,
            live_provider_sessions: 0,
            citation_trace_sessions: 0,
            non_library_sessions: 0,
            final_verdict: null,
            closure_ready: false,
            remaining_requirements: {},
            failures: ["invalid JSON"],
          },
        }}
      />,
    );

    expect(
      screen.getByText(/Dogfood log is malformed; repair the JSONL before counting it/),
    ).toBeTruthy();
  });

  it("surfaces operator action counts and closeable OA focus", () => {
    render(
      <Roadmap
        roadmap={{
          ...roadmap([]),
          operator_actions: {
            source_path: "docs/OPERATOR_ACTIONS.md",
            total_actions: 20,
            open_count: 19,
            closeable_count: 1,
            status_counts: {
              open: 17,
              awaiting_operator_test: 1,
              partially_done: 1,
              closed: 1,
            },
            next_action: {
              action_id: "OA-001",
              title: "Lawyer review",
              status: "open",
              status_raw: "OPEN",
              blocks: "All Stripe payouts",
              owner: "Operator + counsel",
            },
            closeable_action: {
              action_id: "OA-005",
              title: "Autoresearch Wedge 1 ratification",
              status: "awaiting_operator_test",
              status_raw: "AWAITING OPERATOR TEST",
              blocks: "Phase 8 enforcing + Wedges 2-4",
              owner: "Operator",
            },
          },
        }}
      />,
    );

    expect(screen.getByText("Operator actions")).toBeTruthy();
    expect(
      screen.getByText(
        "19/20 not closed · 1 awaiting operator test · 17 open · 1 partially done · 1 closed",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "Closeable now: OA-005 — Autoresearch Wedge 1 ratification. Blocks: Phase 8 enforcing + Wedges 2-4. Source: docs/OPERATOR_ACTIONS.md.",
      ),
    ).toBeTruthy();
  });

  it("surfaces Phase 2 audit execution status beside roadmap state", () => {
    render(
      <Roadmap
        roadmap={{
          ...roadmap([]),
          phase2_audit: {
            source_path: "docs/phase2_execution_audit_v5_2026_07_01.md",
            scorecard_source_path: "docs/phase2_execution_audit_v4_2026_05_23.md",
            current_commit_evidence:
              "23048220 feat(ducklake): route default graph path through catalog",
            engineering_blocked_count: 0,
            status_summary:
              "net engineering-side-blocked items known from v4: 0.",
            next_action_ordering: [
              "Keep docs/OPERATOR_ACTIONS.md as the authoritative operator gate list.",
            ],
            sprint_scorecard: [],
            total_score: {
              sprint: "TOTAL",
              phases: 28,
              met: 6,
              partial: 17,
              unmet: 5,
              delta_vs_v3: "-3 unmet, +3 partial since v3",
            },
            exit_criteria: {
              total: 23,
              met: 3,
              partial: 2,
              unmet: 18,
              note:
                "every unmet exit criterion is blocked by operator action or real-data accumulation, not substrate.",
            },
          },
        }}
      />,
    );

    expect(screen.getByText("Phase 2 execution audit")).toBeTruthy();
    expect(
      screen.getByText(
        "engineering-blocked=0 · sprint phases 6/28 met · 17 partial · 5 unmet · exit criteria 3/23 met · 2 partial · 18 unmet",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(/net engineering-side-blocked items known from v4: 0/),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "Next audit action: Keep docs/OPERATOR_ACTIONS.md as the authoritative operator gate list.",
      ),
    ).toBeTruthy();
  });

  it("surfaces engineering deferrals as do-not-prebuild status", () => {
    render(
      <Roadmap
        roadmap={{
          ...roadmap([]),
          engineering_deferrals: {
            source_path: "docs/engineering_deferrals.md",
            total_deferrals: 19,
            open_count: 16,
            status_counts: {
              deferred: 7,
              partial: 5,
              substrate_shipped: 4,
              closed: 3,
            },
            first_open: {
              deferral_id: "D1",
              title: "Sprint 22 multi-user pivot cluster",
              status: "partial",
              status_raw: "Partial substrate prep",
              unlock_criterion: "G7 closes — earliest ~Nov 2026",
              blocks: "D8 and second-user exit criteria",
            },
          },
        }}
      />,
    );

    expect(screen.getByText("Engineering deferrals")).toBeTruthy();
    expect(
      screen.getByText(
        "16/19 not closed · 7 deferred · 5 partial · 4 substrate shipped · 3 closed",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "Do not pre-build D1 — Sprint 22 multi-user pivot cluster. Unlock: G7 closes — earliest ~Nov 2026. Source: docs/engineering_deferrals.md.",
      ),
    ).toBeTruthy();
  });

  it("surfaces Loop 3 manual and verifier evidence state", () => {
    render(
      <Roadmap
        roadmap={{
          ...roadmap([]),
          loop3: {
            criteria: [],
            manual_met_count: 1,
            evidence_passed_count: 0,
            total_criteria: 5,
            all_criteria_met: false,
            all_evidence_passed: false,
            env_unlocked: false,
            fully_unlocked: false,
            first_failing_evidence: {
              criterion: "trajectory_volume",
              manual_met: true,
              evidence_passed: false,
              evidence_status: "FAIL",
              evidence_summary: "events_dir_exists: /tmp/events",
            },
            events_dir: "/tmp/events",
            open_weight_policy_file: "reports/loop3/open-weight-policy-ids.json",
          },
        }}
      />,
    );

    expect(screen.getByText("Loop 3 / G8")).toBeTruthy();
    expect(
      screen.getByText("manual 1/5 · evidence 0/5 · env=locked · fully=no"),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "First failing evidence: trajectory_volume — events_dir_exists: /tmp/events.",
      ),
    ).toBeTruthy();
  });

  it("surfaces source onboarding gate state", () => {
    render(
      <Roadmap
        roadmap={{
          ...roadmap([]),
          source_gate: {
            source_path: "reports/source_census.json",
            state: "blocked",
            reference_source: "arxiv",
            source_count: 1,
            blocked_count: 1,
            rows: [
              {
                source: "web",
                blocked: true,
                failures: ["metadata_complete_pct=94.0 < 95.0"],
              },
            ],
            error: null,
          },
        }}
      />,
    );

    expect(screen.getByText("Source onboarding gate")).toBeTruthy();
    expect(
      screen.getByText("state=blocked · sources=1 · blocked=1 · reference=arxiv"),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "metadata_complete_pct=94.0 < 95.0 Source: reports/source_census.json.",
      ),
    ).toBeTruthy();
  });

  it("keeps dependency focus ahead of operator gate focus", () => {
    render(
      <Roadmap
        roadmap={{
          ...roadmap([sprint(5, [], true, "drw"), sprint(1, ["drw:5"])]),
          operator_gate_focus: {
            gate_id: "G2",
            title: "Lawyer review",
            status: "open",
            status_raw: "OPEN",
            owner: "Operator + counsel",
            blocks: "All Stripe payouts",
            source_path: "docs/operator_gate_actions.md",
          },
        }}
      />,
    );

    expect(
      screen.getByText("Unblock drw:5 — Research (DRW) · SPR-05"),
    ).toBeTruthy();
    expect(screen.queryByText("Close G2 — Lawyer review")).toBeNull();
  });
});
