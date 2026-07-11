import { describe, expect, it } from "vitest";
import {
  composeWorkstationSessionInsightRecord,
  formatWorkstationSessionInsightRecordSummary,
} from "./workstationSessionInsightRecordCompose";

describe("composeWorkstationSessionInsightRecord", () => {
  it("packs records without persisting or injecting prompts", () => {
    const c = composeWorkstationSessionInsightRecord({
      session_id: "ws-1",
      parent_asset_id: "asset-1",
      operator_ack: true,
      mark_for_prompt_context: true,
      records: [
        {
          record_id: "r1",
          kind: "insight",
          body: "claim holds under noise",
          source_ref: "fdr_1",
        },
        {
          record_id: "r2",
          kind: "question",
          body: "what is the sample size?",
        },
        {
          record_id: "r3",
          kind: "data",
          body: "n=1200",
        },
      ],
    });
    expect(c.record_ready).toBe(true);
    expect(c.record_count).toBe(3);
    expect(c.insight_count).toBe(1);
    expect(c.question_count).toBe(1);
    expect(c.data_count).toBe(1);
    expect(c.record_persisted).toBe(false);
    expect(c.prompts_injected).toBe(false);
    expect(c.store_mutated).toBe(false);
    expect(c.mark_for_prompt_context).toBe(true);
    expect(formatWorkstationSessionInsightRecordSummary(c)).toMatch(
      /record_persisted=false/,
    );
  });

  it("not ready without ack; rejects duplicates", () => {
    const noAck = composeWorkstationSessionInsightRecord({
      session_id: "ws",
      parent_asset_id: "a",
      operator_ack: false,
      records: [{ record_id: "r1", kind: "insight", body: "x" }],
    });
    expect(noAck.record_ready).toBe(false);
    expect(noAck.record_persisted).toBe(false);

    expect(() =>
      composeWorkstationSessionInsightRecord({
        session_id: "ws",
        parent_asset_id: "a",
        operator_ack: true,
        records: [
          { record_id: "r1", kind: "insight", body: "x" },
          { record_id: "r1", kind: "question", body: "y" },
        ],
      }),
    ).toThrow(/duplicate/);
  });
});
