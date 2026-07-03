import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { apiFetch } from "../../lib/api";
import Coordination from "./index";

vi.mock("../../lib/api", () => ({
  apiFetch: vi.fn(),
}));

const apiFetchMock = vi.mocked(apiFetch);

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("Coordination", () => {
  it("sanitizes gate and roadmap API responses before rendering", async () => {
    apiFetchMock.mockImplementation(async (input) => {
      const path = String(input);
      if (path === "/coordination/gates") {
        return {
          ok: true,
          json: async () => ({
            source_path: " docs/operator_gate_actions.md ",
            gates: [
              {
                gate_id: " G2 ",
                title: " ",
                status: "unexpected",
                status_raw: " open until counsel review ",
                is_provisional: "yes",
                owner: " Legal ",
                closure_record: " ",
                impacts: [
                  {
                    product: "read",
                    effect: " blocks publisher payout ",
                  },
                  {
                    product: "unknown",
                    effect: "Skipped impact",
                  },
                ],
              },
              {
                gate_id: " ",
                title: "Skipped gate",
              },
            ],
          }),
        } as Response;
      }
      return {
        ok: true,
        json: async () => ({
          total_sprints: "45.9",
          superseded_count: "6",
          superseded_note: " shell superseded ",
          activation_note: " structural status is not activation closure ",
          reconciliation: " reconciled count ",
          critical_path: [" drw:1 ", " "],
          rosters: [
            {
              spec: " read ",
              label: " Read ",
              directory: " read ",
              count: "2.9",
              sprints: [
                {
                  spec: "read",
                  spec_label: "Read",
                  sprint: "2",
                  slug: " library-browse ",
                  node_id: " read:2 ",
                  status: " ",
                  on_critical_path: "yes",
                  blocked_on: [" drw:10 ", " "],
                  unblocked: false,
                },
                {
                  spec: "drw",
                  spec_label: "Research (DRW)",
                  sprint: 1,
                  slug: " lock-the-spine ",
                  node_id: " drw:1 ",
                  status: "live",
                  on_critical_path: true,
                  blocked_on: [],
                  unblocked: true,
                },
                {
                  node_id: " ",
                  slug: "Skipped sprint",
                },
              ],
            },
            {
              spec: " ",
              label: "Skipped roster",
            },
          ],
          unblocked_now: [" drw:1 ", " drw:1 ", " read:2 ", " missing:9 ", " "],
          dependency_blockers: [
            {
              node_id: " drw:10 ",
              blocked_sprints: [" read:2 ", " read:2 ", " missing:9 ", " "],
            },
            {
              node_id: " missing:9 ",
              blocked_sprints: [" read:2 "],
            },
            {
              node_id: " ",
              blocked_sprints: ["read:2"],
            },
          ],
          execution_focus: {
            kind: "dependency_blocker",
            node_id: " missing:9 ",
            blocked_sprints: [" read:2 "],
          },
          operator_gate_focus: {
            gate_id: " G2 ",
            title: " Counsel review ",
            status: "calendar",
            status_raw: " open until counsel review ",
            owner: " Legal ",
            blocks: " payouts ",
            source_path: " docs/operator_gate_actions.md ",
          },
          read_activation: {
            source_path: " reports/read-dogfood.jsonl ",
            state: " incomplete ",
            total_sessions: "2.9",
            valid_sessions: "1",
            invalid_session_count: "1",
            live_provider_sessions: "0",
            citation_trace_sessions: "1",
            non_library_sessions: "0",
            final_verdict: " ",
            closure_ready: "yes",
            required_counts: {
              valid_sessions: "10.4",
              live_provider_sessions: "5",
              citation_trace_sessions: "3",
              non_library_sessions: "1",
            },
            remaining_requirements: {
              valid_sessions: "9",
              live_provider_sessions: "5",
              citation_trace_sessions: "2",
              non_library_sessions: "1",
            },
            next_session: {
              next_action: " collect_session ",
              recommended_template: " live-citation ",
              append_command:
                " antiek read activation append-template --kind live-citation ",
              rationale: " collect a real live-citation session ",
              remaining_requirements: {
                valid_sessions: "9",
                live_provider_sessions: "5",
                citation_trace_sessions: "2",
                non_library_sessions: "1",
              },
            },
            failures: [" bad row ", " "],
          },
          adrb_dogfood: {
            state: " incomplete ",
            closure_ready: false,
            dogfood_root: " runs/adrb ",
            operator_log_path: " runs/adrb/operator-log.md ",
            metrics_path: " runs/adrb/dogfood_metrics.md ",
            verdict_path: " docs/adrb_post_dogfood_verdict.md ",
            expected_project_count: "5",
            complete_project_entries: "2",
            reconciled_sessions: "1",
            valid_wave4_candidates: "0",
            metrics_current: false,
            mode_a_verdict: " ",
            mode_b_verdict: " ITERATE ",
            missing_requirements: [
              " expected 5 complete project entries, found 2 ",
              " ",
            ],
            error: " ",
          },
          branch_health: {
            state: " stale ",
            branch: " reader/integration ",
            head_sha: " abc1234 ",
            origin_main_sha: " def5678 ",
            merge_base_distance: "238.9",
            max_behind: "25",
            message: " base is 238 commits behind origin/main (limit N=25) ",
            remediation:
              " run `.venv/bin/python -m tools.ops.rebase_preflight --json`, then `git rebase origin/main` in a disposable worktree ",
            error: " ",
          },
          autoresearch_readiness: {
            state: " incomplete ",
            all_satisfied: false,
            total_items: "6.2",
            satisfied_count: "3",
            operator_bound_count: "3",
            missing_count: "0",
            first_blocker: {
              item_id: " program ",
              label: " Synthesizer program review ",
              status: " operator_bound ",
              evidence:
                " write reports/autoresearch/synthesizer-program-review.md ",
            },
            items: [
              {
                item_id: " tooling ",
                label: " tooling present ",
                status: " satisfied ",
                evidence: " required tool files present ",
              },
              {
                item_id: " ",
                label: " skipped ",
                status: " missing ",
                evidence: " skipped ",
              },
            ],
            source_path: " tools.prompt_autoresearch.readiness_cli ",
            error: " ",
          },
          operator_actions: {
            source_path: " docs/OPERATOR_ACTIONS.md ",
            total_actions: "20.8",
            open_count: "19",
            closeable_count: "1",
            status_counts: {
              open: "17",
              partially_done: "1",
              closed: "1",
            },
            next_action: {
              action_id: " OA-001 ",
              title: " Counsel review ",
              status: " open ",
              status_raw: " OPEN ",
              blocks: " payouts ",
              owner: " Legal ",
            },
            closeable_action: {
              action_id: " OA-005 ",
              title: " Wedge ratification ",
              status: " awaiting_operator_test ",
              status_raw: " AWAITING OPERATOR TEST ",
              blocks: " Phase 8 enforcing ",
              owner: " Operator ",
            },
          },
          phase2_audit: {
            source_path: " docs/phase2_execution_audit_v5_2026_07_01.md ",
            scorecard_source_path: " docs/phase2_execution_audit_v4_2026_05_23.md ",
            current_commit_evidence: " 23048220 feat ",
            engineering_blocked_count: "0",
            status_summary: " engineering-side-blocked items known from v4: 0 ",
            next_action_ordering: [
              " Keep docs/OPERATOR_ACTIONS.md as the authoritative operator gate list. ",
              " ",
            ],
            sprint_scorecard: [
              {
                sprint: " Sprint 22 ",
                phases: "9",
                met: "1",
                partial: "6",
                unmet: "2",
                delta_vs_v3: " +1 partial ",
              },
              {
                sprint: " ",
                phases: "bad",
              },
            ],
            total_score: {
              sprint: " TOTAL ",
              phases: "28",
              met: "6",
              partial: "17",
              unmet: "5",
              delta_vs_v3: " -3 unmet ",
            },
            exit_criteria: {
              total: "23",
              met: "3",
              partial: "2",
              unmet: "18",
              note: " operator action ",
            },
          },
          engineering_deferrals: {
            source_path: " docs/engineering_deferrals.md ",
            total_deferrals: "19.8",
            open_count: "16",
            status_counts: {
              deferred: "7",
              partial: "5",
              substrate_shipped: "4",
              closed: "3",
            },
            first_open: {
              deferral_id: " D1 ",
              title: " Multi-user pivot ",
              status: " partial ",
              status_raw: " Partial substrate prep ",
              unlock_criterion: " G7 closes ",
              blocks: " second-user exit criteria ",
            },
          },
          loop3: {
            criteria: [
              {
                criterion: " trajectory_volume ",
                manual_met: "yes",
                evidence_passed: false,
                evidence_status: " FAIL ",
                evidence_summary: " events dir missing ",
              },
              {
                criterion: " ",
                evidence_summary: "Skipped criterion",
              },
            ],
            manual_met_count: "1",
            evidence_passed_count: "0",
            total_criteria: "5",
            all_criteria_met: "yes",
            all_evidence_passed: "yes",
            env_unlocked: "yes",
            fully_unlocked: "yes",
            first_failing_evidence: {
              criterion: " trajectory_volume ",
              manual_met: true,
              evidence_passed: false,
              evidence_status: " FAIL ",
              evidence_summary: " events dir missing ",
            },
            events_dir: " /tmp/events ",
            open_weight_policy_file: " reports/loop3/open-weight-policy-ids.json ",
          },
          source_gate: {
            source_path: " reports/source_census.json ",
            state: " blocked ",
            reference_source: " arxiv ",
            source_count: "1",
            blocked_count: "1",
            rows: [
              {
                source: " web ",
                blocked: true,
                failures: [" metadata_complete_pct=94.0 < 95.0 ", " "],
              },
              {
                source: " ",
                blocked: true,
                failures: ["Skipped row"],
              },
            ],
            error: " ",
          },
          substrate_layers: [
            {
              name: " db lock ",
              owner: " runtime/db_lock.py ",
              status: " hardened ",
            },
            {
              name: " ",
              owner: "Skipped layer",
            },
          ],
        }),
      } as Response;
    });

    render(<Coordination />);

    await screen.findByText("reconciled count");
    expect(screen.getAllByText("G2").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText("open")).toBeTruthy();
    expect(screen.getByText("open until counsel review")).toBeTruthy();
    expect(screen.getByText("blocks publisher payout")).toBeTruthy();
    expect(screen.queryByText("Skipped gate")).toBeNull();
    expect(screen.queryByText("Skipped impact")).toBeNull();

    expect(screen.getByText("library browse")).toBeTruthy();
    expect(screen.getByText("structural status is not activation closure")).toBeTruthy();
    expect(screen.getByText("Read activation dogfood")).toBeTruthy();
    expect(screen.getByText("Deep Research Bridge dogfood")).toBeTruthy();
    expect(
      screen.getByText(
        "2/5 projects · 1 reconciled · metrics=stale/missing · verdict A=missing B=ITERATE",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "Remaining: expected 5 complete project entries, found 2. Source: runs/adrb.",
      ),
    ).toBeTruthy();
    expect(screen.getByText("Branch freshness")).toBeTruthy();
    expect(
      screen.getByText(
        "reader/integration · HEAD=abc1234 · origin/main=def5678 · behind=238/25",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(/base is 238 commits behind origin\/main/),
    ).toBeTruthy();
    expect(screen.getByText("Prompt autoresearch readiness")).toBeTruthy();
    expect(screen.getByText("3/6 satisfied · 3 operator-bound · 0 missing")).toBeTruthy();
    expect(
      screen.getByText(
        /Next: program — write reports\/autoresearch\/synthesizer-program-review\.md\./,
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "1/10 required valid (2 total) · 0 live-provider · 1 citation-traced · 0 non-library · verdict=missing",
      ),
    ).toBeTruthy();
    expect(screen.getByText("1 invalid session need repair.")).toBeTruthy();
    expect(
      screen.getByText(
        "Next: live-citation · antiek read activation append-template --kind live-citation",
      ),
    ).toBeTruthy();
    expect(screen.getByText("Operator actions")).toBeTruthy();
    expect(
      screen.getByText(
        "19/20 not closed · 1 awaiting operator test · 17 open · 1 partially done · 1 closed",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "Closeable now: OA-005 — Wedge ratification. Blocks: Phase 8 enforcing. Source: docs/OPERATOR_ACTIONS.md.",
      ),
    ).toBeTruthy();
    expect(screen.getByText("Phase 2 execution audit")).toBeTruthy();
    expect(
      screen.getByText(
        "engineering-blocked=0 · sprint phases 6/28 met · 17 partial · 5 unmet · exit criteria 3/23 met · 2 partial · 18 unmet",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "Next audit action: Keep docs/OPERATOR_ACTIONS.md as the authoritative operator gate list.",
      ),
    ).toBeTruthy();
    expect(screen.getByText("Engineering deferrals")).toBeTruthy();
    expect(
      screen.getByText(
        "16/19 not closed · 7 deferred · 5 partial · 4 substrate shipped · 3 closed",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "Do not pre-build D1 — Multi-user pivot. Unlock: G7 closes. Source: docs/engineering_deferrals.md.",
      ),
    ).toBeTruthy();
    expect(screen.getByText("Loop 3 / G8")).toBeTruthy();
    expect(
      screen.getByText("manual 1/5 · evidence 0/5 · env=locked · fully=no"),
    ).toBeTruthy();
    expect(
      screen.getByText("First failing evidence: trajectory_volume — events dir missing."),
    ).toBeTruthy();
    expect(screen.getByText("Source onboarding gate")).toBeTruthy();
    expect(
      screen.getByText("state=blocked · sources=1 · blocked=1 · reference=arxiv"),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "metadata_complete_pct=94.0 < 95.0 Source: reports/source_census.json.",
      ),
    ).toBeTruthy();
    expect(screen.getByText("waits on drw:10")).toBeTruthy();
    expect(screen.getByText("1 dependency-ready · 1 blocked by dependency state")).toBeTruthy();
    expect(screen.getByText("Dependency-ready")).toBeTruthy();
    expect(screen.getByRole("columnheader", { name: "Dependency state" })).toBeTruthy();
    expect(screen.getByText("dependency-ready")).toBeTruthy();
    expect(screen.getByText("Dependency blockers")).toBeTruthy();
    expect(screen.getByText("drw:10")).toBeTruthy();
    expect(screen.getByText("Unblock drw:10")).toBeTruthy();
    expect(screen.queryByText("Close G2 — Counsel review")).toBeNull();
    expect(screen.getByText("blocks 1 sprint")).toBeTruthy();
    expect(screen.queryByText("missing:9")).toBeNull();
    expect(screen.getAllByText("lock the spine").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("drw:1")).toHaveLength(2);
    expect(screen.getByText("db lock")).toBeTruthy();
    expect(document.body.textContent).not.toMatch(
      /Skipped sprint|Skipped roster|Skipped layer/,
    );
  });

  it("renders sanitized operator gate focus when structural roadmap focus is clear", async () => {
    apiFetchMock.mockImplementation(async (input) => {
      const path = String(input);
      if (path === "/coordination/gates") {
        return {
          ok: true,
          json: async () => ({ source_path: "docs/operator_gate_actions.md", gates: [] }),
        } as Response;
      }
      return {
        ok: true,
        json: async () => ({
          total_sprints: 45,
          reconciliation: "Read 9 = 9",
          rosters: [],
          unblocked_now: [],
          dependency_blockers: [],
          execution_focus: null,
          operator_gate_focus: {
            gate_id: " G2 ",
            title: " Counsel review ",
            status: "unexpected",
            status_raw: " open until counsel review ",
            owner: " Legal ",
            blocks: " payouts ",
            source_path: " docs/operator_gate_actions.md ",
          },
          read_activation: {
            source_path: " reports/read-dogfood.jsonl ",
            state: "not_started",
            total_sessions: 0,
            valid_sessions: 0,
            invalid_session_count: 0,
            live_provider_sessions: 0,
            citation_trace_sessions: 0,
            non_library_sessions: 0,
            final_verdict: null,
            closure_ready: false,
            required_counts: {
              valid_sessions: 10,
              live_provider_sessions: 5,
              citation_trace_sessions: 3,
              non_library_sessions: 1,
            },
            remaining_requirements: {
              valid_sessions: 10,
              live_provider_sessions: 5,
              citation_trace_sessions: 3,
              non_library_sessions: 1,
            },
            next_session: {
              next_action: "collect_session",
              recommended_template: "live-citation",
              append_command:
                "antiek read activation append-template --kind live-citation",
              rationale: "Collect a session.",
              remaining_requirements: {
                valid_sessions: 10,
                live_provider_sessions: 5,
                citation_trace_sessions: 3,
                non_library_sessions: 1,
              },
            },
            failures: [],
          },
          substrate_layers: [],
        }),
      } as Response;
    });

    render(<Coordination />);

    await screen.findByText("Close G2 — Counsel review");
    expect(screen.getByText("open until counsel review · Legal")).toBeTruthy();
    expect(screen.getByText("Blocks: payouts")).toBeTruthy();
    expect(
      screen.getByText(/Structural dependencies are clear; this focus is read from/),
    ).toBeTruthy();
  });
});
