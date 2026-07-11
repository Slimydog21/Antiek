import { describe, expect, it } from "vitest";
import {
  bridgeWorkstationRecordPromptContext,
  formatWorkstationRecordPromptContextBridgeSummary,
} from "./workstationRecordPromptContextBridge";

describe("bridgeWorkstationRecordPromptContext", () => {
  it("bridges records into proposed prompt without injecting", () => {
    const e = bridgeWorkstationRecordPromptContext({
      session_id: "sess-1",
      user_prompt: "What are the open questions on scaling?",
      items: [
        {
          record_id: "r1",
          kind: "insight",
          text: "scaling holds under noise",
          weight: 0.9,
        },
        {
          record_id: "r2",
          kind: "question",
          text: "what about multimodal?",
          weight: 0.5,
        },
      ],
      placement: "prefix",
    });
    expect(e.prompts_injected).toBe(false);
    expect(e.record_persisted).toBe(false);
    expect(e.bridge_ready).toBe(true);
    expect(e.context_line_count).toBe(2);
    expect(e.proposed_prompt).toMatch(/scaling holds/);
    expect(e.proposed_prompt).toMatch(/open questions on scaling/);
    expect(e.proposed_prompt.indexOf("Workstation recursive context")).toBeLessThan(
      e.proposed_prompt.indexOf("User prompt"),
    );
    expect(e.authority).toBe(
      "workstation_record_prompt_context_bridge_advisory",
    );
    expect(formatWorkstationRecordPromptContextBridgeSummary(e)).toMatch(
      /prompts_injected=false/,
    );
  });

  it("suffix placement and empty pack", () => {
    const e = bridgeWorkstationRecordPromptContext({
      session_id: "s",
      user_prompt: "Hello",
      items: [],
      placement: "suffix",
    });
    expect(e.context_line_count).toBe(0);
    expect(e.proposed_prompt).toBe("Hello");
    expect(e.prompts_injected).toBe(false);
    expect(e.record_persisted).toBe(false);
    expect(e.notes.some((n) => n.includes("no invent context"))).toBe(true);
  });

  it("attaches model decision when requested", () => {
    const e = bridgeWorkstationRecordPromptContext({
      session_id: "s",
      user_prompt: "Analyze",
      items: [
        { record_id: "r1", kind: "finding", text: "A holds", weight: 1 },
      ],
      model_decision: {
        selected_model_id: "flash-1",
        models: [
          {
            model_id: "flash-1",
            tier: "flash",
            projected_cost_usd_high: 0.5,
            projected_cost_usd_low: 0.1,
          },
        ],
        daily_cap_usd: 10,
        spent_usd: 1,
      },
    });
    expect(e.model_decision).not.toBeNull();
    expect(e.model_decision!.selected_model_id).toBe("flash-1");
    expect(e.model_decision!.would_exceed).toBe(false);
    expect(e.prompts_injected).toBe(false);
  });

  it("rejects blank user_prompt and invalid placement", () => {
    expect(() =>
      bridgeWorkstationRecordPromptContext({
        session_id: "s",
        user_prompt: "  ",
        items: [],
      }),
    ).toThrow(/user_prompt/);
    expect(() =>
      bridgeWorkstationRecordPromptContext({
        session_id: "s",
        user_prompt: "ok",
        items: [],
        placement: "middle" as "prefix",
      }),
    ).toThrow(/placement/);
  });

  it("rejects prebuilt pack with honesty flags broken", () => {
    expect(() =>
      bridgeWorkstationRecordPromptContext({
        session_id: "s",
        user_prompt: "ok",
        prebuilt_pack: {
          session_id: "s",
          item_count: 0,
          by_kind: {
            insight: 0,
            question: 0,
            highlight: 0,
            finding: 0,
            open_thread: 0,
          },
          prompt_context_lines: [],
          pack_ready: false,
          record_persisted: true as false,
          prompts_injected: false,
          notes: [],
          authority: "workstation_recursive_record_pack_advisory",
        },
      }),
    ).toThrow(/record_persisted/);
  });
});
