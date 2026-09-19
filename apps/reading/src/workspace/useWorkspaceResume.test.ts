import { beforeEach, describe, expect, it } from "vitest";

import { MAX_WINDOWS, useWindows } from "./windowsStore";
import { checkpointKey, deepResearchSessionWindowId, hostedDocumentWindowId, replayWorkspace, semanticEntries } from "./useWorkspaceResume";

describe("closed workspace resumability projection", () => {
  beforeEach(() => useWindows.getState().reset());

  it("preserves excluded windows, never projects their payloads, and replays through canonical opens", () => {
    const store = useWindows.getState();
    store.open("hosted_html_document", { html: "private", document_id: "doc" }, { id: "excluded-doc" });
    store.open("deep_research_session", { prompt: "private" }, { id: "excluded-session" });
    replayWorkspace([{ kind: "stats" }, { kind: "research_artifact", investigation_id: "inv-1" }]);
    const state = useWindows.getState();
    expect(state.windows["excluded-doc"]).toBeDefined();
    expect(state.windows["excluded-session"]).toBeDefined();
    expect(state.windows["win:stats"]).toMatchObject({ kind: "stats", mode: "floating", payload: {} });
    expect(state.windows["win:research_artifact:inv-1"]).toMatchObject({ kind: "research_artifact", mode: "floating", payload: { investigationId: "inv-1" } });
    const projected = semanticEntries(state.windows, ["stats", "research_artifact:inv-1"]);
    expect(projected).toEqual([{ kind: "stats" }, { kind: "research_artifact", investigation_id: "inv-1" }]);
    expect(JSON.stringify(projected)).not.toContain("private");
  });

  it("geometry, focus, mode, and z-order changes do not change the projection", () => {
    const store = useWindows.getState();
    store.open("stats", {}, { id: "win:stats" });
    store.open("library", {}, { id: "win:library" });
    const order = ["stats", "library"];
    const before = semanticEntries(useWindows.getState().windows, order);
    store.setRect("win:stats", { x: 999, width: 321 });
    store.focus("win:stats");
    store.expand("win:library");
    store.restore("win:library");
    expect(semanticEntries(useWindows.getState().windows, order)).toEqual(before);
  });

  it("projects and replays only exact references without raw HTML or caller metadata", () => {
    const store = useWindows.getState();
    store.open("hosted_html_document", {
      document_id: "same",
      title: "caller title",
      html: "raw secret",
      source: "caller authority",
      resume_ref: { resolver: "hosted_document", document_id: "same" },
    }, { id: "referenced" });
    store.open("hosted_html_document", {
      document_id: "same",
      html: "ephemeral secret",
    }, { id: "ephemeral" });
    store.open("hosted_html_document", {
      resume_ref: { resolver: "hosted_document", document_id: "same", extra: "open" },
      html: "invalid reference secret",
    }, { id: "invalid-reference" });

    const projected = semanticEntries(useWindows.getState().windows, [
      "hosted_html_document:hosted_document:same",
    ]);
    expect(projected).toEqual([{
      kind: "hosted_html_document",
      resolver: "hosted_document",
      document_id: "same",
    }]);
    expect(JSON.stringify(projected)).not.toMatch(/raw secret|caller title|caller authority/);

    replayWorkspace([
      { kind: "hosted_html_document", resolver: "hosted_document", document_id: "same" },
      { kind: "hosted_html_document", resolver: "engagement_document", document_id: "same" },
    ]);
    const windows = useWindows.getState().windows;
    expect(windows.ephemeral).toBeDefined();
    expect(windows["invalid-reference"]).toBeDefined();
    expect(windows.referenced).toBeUndefined();
    const hostedId = hostedDocumentWindowId("hosted_document", "same");
    const engagementId = hostedDocumentWindowId("engagement_document", "same");
    expect(hostedId).not.toContain("hosted_document");
    expect(hostedId).not.toContain("same");
    expect(hostedId).not.toBe(engagementId);
    expect(windows[hostedId].payload).toEqual({
      document_id: "same",
      resume_ref: { resolver: "hosted_document", document_id: "same" },
    });
    expect(windows[engagementId].payload).toEqual({
      document_id: "same",
      resume_ref: { resolver: "engagement_document", document_id: "same" },
    });
  });

  it("honors MAX_WINDOWS without replacing preserved excluded windows", () => {
    const store = useWindows.getState();
    for (let index = 0; index < MAX_WINDOWS; index += 1) store.open("hosted_html_document", { html: `secret-${index}` }, { id: `excluded-${index}` });
    replayWorkspace([{ kind: "stats" }]);
    const state = useWindows.getState();
    expect(Object.keys(state.windows)).toHaveLength(MAX_WINDOWS);
    expect(state.windows["win:stats"]).toBeUndefined();
    expect(Object.values(state.windows).every((window) => window.kind === "hosted_html_document")).toBe(true);
  });

  it("checkpoints a fresh session by admission ref and replays only through the resolver ref", () => {
    const store = useWindows.getState();
    store.open("deep_research_session", {
      session_id: "session-1",
      spawn_id: "spawn-secret",
      selection_text: "private selection",
      goal: "private goal",
      workspace_resume_ref: { session_id: "session-1" },
    }, { id: "fresh-session" });

    const projected = semanticEntries(useWindows.getState().windows, ["deep_research_session:session-1"]);
    expect(projected).toEqual([{ kind: "deep_research_session", session_id: "session-1" }]);
    expect(JSON.stringify(projected)).not.toMatch(/spawn-secret|private selection|private goal/);

    replayWorkspace(projected);
    const replayed = useWindows.getState().windows[deepResearchSessionWindowId("session-1")];
    expect(replayed.mode).toBe("floating");
    expect(replayed.payload).toEqual({ resume_ref: { session_id: "session-1" } });
  });

  it("checkpoints and replays an interrogation as dual references without private projection bytes", () => {
    const store = useWindows.getState();
    store.open("collective_unit", {
      resume_ref: { manifest_id: "manifest" },
      interrogation_ref: { investigation_id: "inv", receipt_id: "receipt" },
      question: "private question",
      prompt_block: "private completed reasoning",
      ordered_spawn_ids: ["private-spawn"],
    }, { id: "fresh-interrogation" });

    const key = checkpointKey({ kind: "ancestry_interrogation", investigation_id: "inv", manifest_id: "manifest", receipt_id: "receipt" });
    const projected = semanticEntries(useWindows.getState().windows, [key]);
    expect(projected).toEqual([{
      kind: "ancestry_interrogation",
      investigation_id: "inv",
      manifest_id: "manifest",
      receipt_id: "receipt",
    }]);
    expect(JSON.stringify(projected)).not.toMatch(/private question|private completed reasoning|private-spawn/);

    replayWorkspace(projected);
    const replayed = Object.values(useWindows.getState().windows).find((window) =>
      window.kind === "collective_unit" && (window.payload.interrogation_ref as { receipt_id?: string } | undefined)?.receipt_id === "receipt");
    expect(replayed?.payload).toEqual({
      resume_ref: { manifest_id: "manifest" },
      interrogation_ref: { investigation_id: "inv", receipt_id: "receipt" },
    });
    expect(replayed?.mode).toBe("floating");
  });

  it("does not downgrade malformed interrogation references and keeps generic and interrogated collectives distinct", () => {
    const store = useWindows.getState();
    store.open("collective_unit", {
      resume_ref: { manifest_id: "manifest" },
    }, { id: "generic" });
    store.open("collective_unit", {
      resume_ref: { manifest_id: "manifest" },
      interrogation_ref: { investigation_id: " inv", receipt_id: "receipt" },
    }, { id: "malformed-whitespace" });
    store.open("collective_unit", {
      resume_ref: { manifest_id: "manifest" },
      interrogation_ref: { investigation_id: "inv", receipt_id: "receipt", question: "leak" },
    }, { id: "malformed-extra" });
    store.open("collective_unit", {
      resume_ref: { manifest_id: "manifest" },
      interrogation_ref: { investigation_id: "inv", receipt_id: "receipt" },
    }, { id: "interrogated" });

    const projected = semanticEntries(useWindows.getState().windows, [
      "collective_unit:manifest",
      checkpointKey({ kind: "ancestry_interrogation", investigation_id: "inv", manifest_id: "manifest", receipt_id: "receipt" }),
    ]);
    expect(projected).toEqual([
      { kind: "collective_unit", manifest_id: "manifest" },
      {
        kind: "ancestry_interrogation",
        investigation_id: "inv",
        manifest_id: "manifest",
        receipt_id: "receipt",
      },
    ]);
    expect(JSON.stringify(projected)).not.toContain("leak");
  });

  it("uses collision-free interrogation checkpoint keys", () => {
    const first = checkpointKey({
      kind: "ancestry_interrogation", investigation_id: "a:b", manifest_id: "c", receipt_id: "d",
    });
    const second = checkpointKey({
      kind: "ancestry_interrogation", investigation_id: "a", manifest_id: "b:c", receipt_id: "d",
    });
    expect(first).not.toBe(second);
  });

  it("cannot ingest legacy panel snapshot or URL state", () => {
    // Projection accepts only the whole-page windows record. Legacy panel
    // snapshots and ?ws= state have no argument through which to enter.
    expect(semanticEntries(useWindows.getState().windows, [])).toEqual([]);
    expect(semanticEntries).toHaveLength(2);
  });
});
