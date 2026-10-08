import { describe, expect, it } from "vitest";

import { parseAssistantReply } from "../../components/ai/aiActions";

const reply = (actions: unknown[]) => `Reply.\n\n@@actions\n${JSON.stringify(actions)}\n@@end`;

describe("agent reply action wire and diagnostics", () => {
  it.each([undefined, "section-1", ""])("preserves a valid writer target and its optional section %s", (section) => {
    const action = { kind: "open_writer", deliverable_id: "draft-1", ...(section === undefined ? {} : { block_id: section }) };
    const parsed = parseAssistantReply(reply([action]));
    expect(parsed.actions).toEqual([action]);
    expect(parsed.parseErrors).toEqual([]);
  });

  it.each([null, 42, [], {}].map((section) => ({ section })))("refuses malformed writer sections without exposing wire vocabulary: $section", ({ section }) => {
    const parsed = parseAssistantReply(reply([
      { kind: "open_writer", deliverable_id: "draft-1", block_id: section },
      { kind: "toast", level: "info", message: "Kept" },
    ]));
    expect(parsed.actions).toEqual([{ kind: "toast", level: "info", message: "Kept" }]);
    expect(parsed.parseErrors).toEqual(["open_writer: section must be text"]);
    expect(parsed.prose).toBe("Reply.");
  });
});
