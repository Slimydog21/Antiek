import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { sectionProse, setSectionProseOwner, suspendSectionProseDispatch } from "./sectionProse";

const { save, generate } = vi.hoisted(() => ({ save: vi.fn(), generate: vi.fn() }));
vi.mock("../../lib/api", async (original) => ({ ...(await original<typeof import("../../lib/api")>()), updateSectionProse: save }));
vi.mock("./writeApi", async (original) => ({ ...(await original<typeof import("./writeApi")>()), generateSection: generate }));
function deferred() {
  let resolve!: (value: unknown) => void;
  const promise = new Promise((done) => { resolve = done; });
  return { promise, resolve };
}
const open = (id = "section", prose = "Server prose") => sectionProse("piece", id, prose, {});
beforeEach(() => {
  setSectionProseOwner(null);
  setSectionProseOwner("owner-a");
  save.mockReset().mockResolvedValue({});
  generate.mockReset();
  vi.useFakeTimers();
});
afterEach(() => { setSectionProseOwner(null); vi.useRealTimers(); });

describe("section prose ownership and retention", () => {
  it("revokes an old debounce before logout can change the cookie", async () => {
    const a = open();
    a.edit("A draft", null);
    setSectionProseOwner(null);
    await vi.advanceTimersByTimeAsync(1000);
    await a.flush();
    expect(save).not.toHaveBeenCalled();
    expect(a.getSnapshot().available).toBe(false);
  });

  it("an old response cannot send queued A prose or change B's section", async () => {
    const first = deferred();
    save.mockReturnValueOnce(first.promise);
    const a = open();
    a.edit("A first", null);
    const saving = a.flush();
    a.edit("A later", null);
    setSectionProseOwner("owner-b");
    const b = open("section", "B prose");
    first.resolve({});
    await saving;
    await vi.advanceTimersByTimeAsync(1000);
    expect(save).toHaveBeenCalledTimes(1);
    expect(b.getSnapshot().draft).toBe("B prose");
    expect(b.getSnapshot().saved).toBe("B prose");
    expect(a.getSnapshot().draft).toBeNull();
  });

  it("suspends a retained draft on unavailable auth and resumes only on confirmed same owner", async () => {
    const a = open();
    a.edit("Retain this", null);
    suspendSectionProseDispatch();
    await vi.advanceTimersByTimeAsync(1000);
    await a.flush();
    expect(save).not.toHaveBeenCalled();
    expect(open()).toBe(a);
    expect(a.getSnapshot().draft).toBe("Retain this");
    expect(a.getSnapshot().save.status).toBe("paused");
    setSectionProseOwner("owner-a");
    await vi.advanceTimersByTimeAsync(0);
    expect(save).toHaveBeenCalledWith("section", { prose_text: "Retain this", original_text: "Server prose", promote_to_graph: false });
  });

  it("suspension stops an in-flight save's follow-up until identity is confirmed", async () => {
    const first = deferred();
    save.mockReturnValueOnce(first.promise);
    const a = open();
    a.edit("First", null);
    const saving = a.flush();
    a.edit("Last", null);
    suspendSectionProseDispatch();
    first.resolve({});
    await saving;
    expect(save).toHaveBeenCalledTimes(1);
    expect(a.getSnapshot().saved).toBe("First");
    expect(a.getSnapshot().draft).toBe("Last");
    setSectionProseOwner("owner-a");
    await vi.advanceTimersByTimeAsync(0);
    expect(save).toHaveBeenLastCalledWith("section", { prose_text: "Last", original_text: "First", promote_to_graph: false });
  });

  it("does not launch generation under another owner after waiting for a save", async () => {
    const first = deferred();
    save.mockReturnValueOnce(first.promise);
    const a = open();
    a.edit("A edit", null);
    const generating = a.generate();
    setSectionProseOwner(null);
    setSectionProseOwner("owner-b");
    first.resolve({});
    await generating;
    expect(generate).not.toHaveBeenCalled();
    expect(open("section", "B initial").getSnapshot().draft).toBe("B initial");
  });

  it("ignores a generation result from a revoked owner", async () => {
    const result = deferred();
    generate.mockReturnValueOnce(result.promise);
    const a = open();
    const generating = a.generate();
    await vi.advanceTimersByTimeAsync(0);
    expect(generate).toHaveBeenCalledTimes(1);
    setSectionProseOwner("owner-b");
    const b = open("section", "B initial");
    result.resolve({ status: "generated", prose_text: "A generated", section_id: "section" });
    await generating;
    expect(b.getSnapshot().draft).toBe("B initial");
    expect(a.getSnapshot().available).toBe(false);
  });

  it("bounds settled inactive entries while keeping failed edits recoverable", async () => {
    const failed = open("failed");
    save.mockRejectedValueOnce(new Error("offline"));
    failed.edit("Recover me", null);
    await failed.flush();
    const oldest = open("oldest");
    oldest.subscribe(() => {})();
    for (let i = 0; i < 40; i++) open(String(i)).subscribe(() => {})();
    expect(open("oldest")).not.toBe(oldest);
    expect(open("failed")).toBe(failed);
    expect(failed.getSnapshot().draft).toBe("Recover me");
  });

  it("retains a cleared draft and reports the endpoint's empty-prose limitation", async () => {
    const a = open();
    a.edit("", { type: "doc", content: [{ type: "paragraph" }] });
    expect(await a.flush()).toBe(false);
    expect(a.getSnapshot().draft).toBe("");
    expect(a.getSnapshot().save.status).toBe("error");
    expect(save).not.toHaveBeenCalled();
  });
});
