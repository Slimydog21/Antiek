import { describe, it, expect } from "vitest";

import { parseAssistantReply } from "./aiActions";

describe("parseAssistantReply — fence detection", () => {
  it("returns the whole input as prose when no fence is present", () => {
    const r = parseAssistantReply("Plain reply with no actions.");
    expect(r.prose).toBe("Plain reply with no actions.");
    expect(r.actions).toHaveLength(0);
    expect(r.parseErrors).toHaveLength(0);
  });

  it("strips a single @@actions / @@end fence + parses the JSON inside", () => {
    const raw =
      "Here's what I think.\n\n@@actions\n" +
      JSON.stringify([
        {
          kind: "open_panel",
          panel_kind: "HtmlReader",
          props: { documentId: "doc-1", anchorId: "antiek-anchor-1", investigationId: "inv-1" },
          mode: "floating",
        },
      ]) +
      "\n@@end";
    const r = parseAssistantReply(raw);
    expect(r.prose).toBe("Here's what I think.");
    expect(r.actions).toHaveLength(1);
    expect(r.actions[0].kind).toBe("open_panel");
  });

  it("works with no trailing @@end (greedy take to end)", () => {
    const raw = "Note this.\n\n@@actions\n[]";
    const r = parseAssistantReply(raw);
    expect(r.prose).toBe("Note this.");
    expect(r.actions).toHaveLength(0);
  });
});

describe("parseAssistantReply — schema enforcement", () => {
  it("drops unknown action kinds + records the error", () => {
    const raw =
      "Reply.\n\n@@actions\n" +
      JSON.stringify([
        { kind: "open_panel", panel_kind: "HtmlReader", props: { documentId: "doc-1" } },
        { kind: "rm_rf_root", target: "/" },
      ]) +
      "\n@@end";
    const r = parseAssistantReply(raw);
    expect(r.actions).toHaveLength(1);
    expect(r.actions[0].kind).toBe("open_panel");
    expect(r.parseErrors.length).toBeGreaterThan(0);
    expect(r.parseErrors[0]).toContain("rm_rf_root");
  });

  it("reports JSON-parse failures + returns prose intact", () => {
    const raw = "Body.\n\n@@actions\n[{not: valid}]\n@@end";
    const r = parseAssistantReply(raw);
    expect(r.prose).toBe("Body.");
    expect(r.actions).toHaveLength(0);
    expect(r.parseErrors[0]).toContain("JSON parse");
  });

  it("rejects a non-array payload", () => {
    const raw = "X.\n\n@@actions\n{\"kind\": \"open_panel\"}\n@@end";
    const r = parseAssistantReply(raw);
    expect(r.actions).toHaveLength(0);
    expect(r.parseErrors[0]).toContain("Expected an array");
  });

  it("skips non-object entries inside the array", () => {
    const raw =
      "X.\n\n@@actions\n" +
      JSON.stringify([null, 42, "string", { kind: "focus_panel", id: "p1" }]) +
      "\n@@end";
    const r = parseAssistantReply(raw);
    expect(r.actions).toHaveLength(1);
    expect(r.actions[0].kind).toBe("focus_panel");
    expect(r.parseErrors.length).toBeGreaterThan(0);
  });
});

describe("parseAssistantReply — closed-enum hardening", () => {
  it("accepts HTML reader lineage and rejects legacy PDF/page actions", () => {
    const raw = "X.\n\n@@actions\n" + JSON.stringify([
      { kind: "open_panel", panel_kind: "HtmlReader", props: { documentId: "doc-1", anchorId: "antiek-anchor-2", investigationId: "inv-2" } },
      { kind: "open_panel", panel_kind: "PdfViewer", props: { documentId: "doc-1", page: 2 } },
      { kind: "open_panel", panel_kind: "HtmlReader", props: { documentId: "doc-1", page: 2 } },
    ]) + "\n@@end";
    const r = parseAssistantReply(raw);
    expect(r.actions).toHaveLength(1);
    expect(r.parseErrors).toHaveLength(2);
  });

  it("never returns an action with an unknown kind, even if the model insists", () => {
    const raw =
      "X.\n\n@@actions\n" +
      JSON.stringify([
        { kind: "exec_shell", cmd: "rm -rf" },
        { kind: "fetch_url", url: "https://evil.example" },
        { kind: "open_panel", panel_kind: "FakeChat" },
      ]) +
      "\n@@end";
    const r = parseAssistantReply(raw);
    expect(r.actions.every((a) => a.kind === "open_panel")).toBe(true);
    expect(r.parseErrors).toHaveLength(2);
  });
});

describe("parseAssistantReply — canonical notebook regions", () => {
  const anchor = `antiek-anchor-${"a".repeat(64)}`;
  const parseRegion = (attrs: Record<string, unknown>) => parseAssistantReply(
    "X.\n\n@@actions\n" + JSON.stringify([{ kind: "add_to_notebook", notebook_id: "nb", block: { kind: "region_embed", attrs } }]) + "\n@@end",
  );

  it("accepts document_id + anchor_id with optional source_page", () => {
    const result = parseRegion({ document_id: "doc-1", anchor_id: anchor, source_page: 2 });
    expect(result.actions).toHaveLength(1);
    expect(result.parseErrors).toHaveLength(0);
  });

  it("rejects missing lineage and page-only/page/initialPage payloads", () => {
    for (const attrs of [
      { document_id: "doc-1", page: 2 },
      { document_id: "doc-1", anchor_id: anchor, page: 2 },
      { document_id: "doc-1", anchor_id: anchor, initialPage: 2 },
      { document_id: "doc-1", anchor_id: "not-canonical" },
      { anchor_id: anchor },
    ]) {
      const result = parseRegion(attrs);
      expect(result.actions).toHaveLength(0);
      expect(result.parseErrors[0]).toContain("region_embed");
    }
  });
});
