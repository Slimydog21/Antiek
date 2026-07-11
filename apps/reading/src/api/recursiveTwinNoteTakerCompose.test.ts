import { describe, expect, it } from "vitest";
import {
  composeRecursiveTwinNoteTaker,
  formatRecursiveTwinNoteTakerSummary,
} from "./recursiveTwinNoteTakerCompose";

describe("composeRecursiveTwinNoteTaker", () => {
  it("proposes twin scaffold without writing or dispatching", () => {
    const c = composeRecursiveTwinNoteTaker({
      parent_asset_id: "asset-1",
      source_excerpt: "<p>Scaling laws under noise</p>",
      operator_ack: true,
      focus_questions: ["What is the sample size?"],
    });
    expect(c.twin_propose_ready).toBe(true);
    expect(c.twin_written).toBe(false);
    expect(c.prompts_injected).toBe(false);
    expect(c.live_dispatch_authorized).toBe(false);
    expect(c.focus_question_count).toBe(1);
    expect(c.twin_scaffold_sections.length).toBeGreaterThanOrEqual(4);
    expect(c.authority).toBe("recursive_twin_note_taker_compose_advisory");
    expect(formatRecursiveTwinNoteTakerSummary(c)).toMatch(/twin_written=false/);
  });

  it("not ready without ack; rejects blank excerpt", () => {
    const noAck = composeRecursiveTwinNoteTaker({
      parent_asset_id: "a",
      source_excerpt: "body",
      operator_ack: false,
    });
    expect(noAck.twin_propose_ready).toBe(false);
    expect(noAck.twin_written).toBe(false);

    expect(() =>
      composeRecursiveTwinNoteTaker({
        parent_asset_id: "a",
        source_excerpt: "  ",
        operator_ack: true,
      }),
    ).toThrow(/source_excerpt/);
  });
});
