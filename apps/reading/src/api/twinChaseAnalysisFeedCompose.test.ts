import { describe, expect, it } from "vitest";
import {
  composeTwinChaseAnalysisFeed,
  formatTwinChaseAnalysisFeedSummary,
} from "./twinChaseAnalysisFeedCompose";

describe("composeTwinChaseAnalysisFeed", () => {
  it("feeds findings into twin scaffold without write", () => {
    const c = composeTwinChaseAnalysisFeed({
      session_id: "sess-1",
      parent_asset_id: "paper-1",
      findings: [
        {
          source_id: "chase_1",
          body: "scaling holds under noise",
          kind: "insight",
        },
        {
          source_id: "chase_2",
          body: "What is the failure mode?",
          kind: "question",
        },
      ],
      analysis_excerpt: "draft collective analysis scaffold",
      operator_ack: true,
      mark_for_prompt_context: true,
    });
    expect(c.feed_ready).toBe(true);
    expect(c.finding_count).toBe(2);
    expect(c.insight_count).toBe(1);
    expect(c.question_count).toBe(1);
    expect(c.twin.twin_propose_ready).toBe(true);
    expect(c.twin_written).toBe(false);
    expect(c.record_persisted).toBe(false);
    expect(c.prompts_injected).toBe(false);
    expect(c.live_dispatch_authorized).toBe(false);
    expect(c.authority).toBe("twin_chase_analysis_feed_compose_advisory");
    const s = formatTwinChaseAnalysisFeedSummary(c);
    expect(s).toMatch(/twin_written=false/);
    expect(s).toMatch(/record_persisted=false/);
    expect(s).toMatch(/prompts_injected=false/);
    expect(s).toMatch(/live_dispatch_authorized=false/);
  });

  it("ack false not feed_ready", () => {
    const c = composeTwinChaseAnalysisFeed({
      session_id: "s",
      parent_asset_id: "p",
      findings: [{ source_id: "a", body: "x", kind: "insight" }],
      operator_ack: false,
    });
    expect(c.feed_ready).toBe(false);
    expect(c.twin_written).toBe(false);
  });

  it("rejects empty findings", () => {
    expect(() =>
      composeTwinChaseAnalysisFeed({
        session_id: "s",
        parent_asset_id: "p",
        findings: [],
        operator_ack: true,
      }),
    ).toThrow(/non-empty/);
  });

  it("rejects duplicate source_id", () => {
    expect(() =>
      composeTwinChaseAnalysisFeed({
        session_id: "s",
        parent_asset_id: "p",
        findings: [
          { source_id: "a", body: "1" },
          { source_id: "a", body: "2" },
        ],
        operator_ack: true,
      }),
    ).toThrow(/duplicate/);
  });
});
