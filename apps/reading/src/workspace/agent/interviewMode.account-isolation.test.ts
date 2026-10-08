/** Real owned seam/canonical producer, synthetic local UNIT subjects/seeds.
 * No intake, project POST, provider or live-account proof. */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { awaitWorkspaceOwnerSession, beforeWorkspaceOwnerChange, resumeWorkspaceOwner, setWorkspaceOwner, subscribeWorkspaceOwnerAdmission, suspendWorkspaceOwner, workspaceOwnerSession } from "../../lib/accountWorkspaceOwner";
import { dispatchProjectSeed, resetProjectSeedSeam, subscribeProjectSeed, type ProjectSeed } from "./interviewMode";

const A = "unit-seed-A"; const B = "unit-seed-B";
const seed: ProjectSeed = { title: "UNIT seed", prompt: "UNIT question", sources: ["unit-doc"] };
async function owner(subject: string | null) { setWorkspaceOwner(subject); await awaitWorkspaceOwnerSession(workspaceOwnerSession()); }
async function resume() { resumeWorkspaceOwner(); await awaitWorkspaceOwnerSession(workspaceOwnerSession()); }
beforeEach(async () => { setWorkspaceOwner(null); await owner(A); resetProjectSeedSeam(); });
afterEach(() => { try { resetProjectSeedSeam(); vi.restoreAllMocks(); } finally { setWorkspaceOwner(null); } });

describe("project seed originating token and held queue", () => {
  it.each(["B", "null", "B-A"])("held A seed is retired by %s rather than assigned to the next intake", async (replacement) => {
    expect(dispatchProjectSeed(seed)).toEqual({ delivered: 0, failed: 0 });
    await owner(replacement === "null" ? null : B); if (replacement === "B-A") await owner(A);
    const got: ProjectSeed[] = []; subscribeProjectSeed((s) => got.push(s));
    expect(got).toEqual([]);
  });
  it("old A registration never receives B dispatch; a new B registration works", async () => {
    const old = vi.fn(); subscribeProjectSeed(old); await owner(B);
    const current = vi.fn(); subscribeProjectSeed(current);
    expect(dispatchProjectSeed(seed)).toEqual({ delivered: 1, failed: 0 });
    expect(old).not.toHaveBeenCalled(); expect(current).toHaveBeenCalledExactlyOnceWith(seed);
  });
  it("an unknown owner can neither retain a seed nor register an intake for a later account", async () => {
    await owner(null); const old = vi.fn(); subscribeProjectSeed(old); dispatchProjectSeed(seed);
    await owner(B); const current = vi.fn(); subscribeProjectSeed(current);
    expect(old).not.toHaveBeenCalled(); expect(current).not.toHaveBeenCalled();
    expect(dispatchProjectSeed(seed)).toEqual({ delivered: 1, failed: 0 });
  });
  it("failed retirement purges held data and refuses old or newly registered callbacks", () => {
    dispatchProjectSeed(seed); const old = vi.fn();
    const off = beforeWorkspaceOwnerChange(() => { throw new Error("UNIT failed retirement"); });
    try { expect(() => setWorkspaceOwner(B)).toThrow("UNIT failed retirement"); } finally { off(); }
    subscribeProjectSeed(old); expect(dispatchProjectSeed(seed)).toEqual({ delivered: 0, failed: 0 }); expect(old).not.toHaveBeenCalled();
  });
  it("suspension keeps ordered held seeds without delivery; confirmation drains once", async () => {
    dispatchProjectSeed(seed); dispatchProjectSeed({ ...seed, title: "second" }); const token = workspaceOwnerSession();
    suspendWorkspaceOwner(); const got: ProjectSeed[] = []; subscribeProjectSeed((s) => got.push(s));
    expect(got).toEqual([]); await resume(); expect(workspaceOwnerSession()).toBe(token);
    expect(got.map((s) => s.title)).toEqual([seed.title, "second"]);
    const later = vi.fn(); subscribeProjectSeed(later); expect(later).not.toHaveBeenCalled();
  });
  it("suspended dispatch is refused without adding a seed for replay", async () => {
    dispatchProjectSeed(seed); suspendWorkspaceOwner(); dispatchProjectSeed({ ...seed, title: "refused" }); await resume();
    const got: ProjectSeed[] = []; subscribeProjectSeed((s) => got.push(s)); expect(got).toEqual([seed]);
  });
  it("ready notification alone does not admit private callbacks or held publication", async () => {
    dispatchProjectSeed(seed); suspendWorkspaceOwner(); const got = vi.fn(); let during = -1;
    const off = subscribeWorkspaceOwnerAdmission(({ state }) => {
      if (state === "ready") { subscribeProjectSeed(got); dispatchProjectSeed({ ...seed, title: "unconfirmed" }); during = got.mock.calls.length; }
    });
    try { await resume(); } finally { off(); }
    expect(during).toBe(0); expect(got).toHaveBeenCalledExactlyOnceWith(seed);
  });
  it.each(["return", "throw"])("synchronous owner replacement inside %s callback stops later consumers and old requeue", async (ending) => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    const first = vi.fn(() => { setWorkspaceOwner(B); if (ending === "throw") throw new Error("UNIT retired callback"); });
    const later = vi.fn(); subscribeProjectSeed(first); subscribeProjectSeed(later); dispatchProjectSeed(seed);
    expect(first).toHaveBeenCalledTimes(1); expect(later).not.toHaveBeenCalled();
    await awaitWorkspaceOwnerSession(workspaceOwnerSession()); const current = vi.fn(); subscribeProjectSeed(current);
    expect(current).not.toHaveBeenCalled(); dispatchProjectSeed({ ...seed, title: "B" }); expect(current).toHaveBeenCalledTimes(1);
  });
  it("consumer suspension holds remaining live deliveries without replaying a completed callback", async () => {
    const first = vi.fn(() => suspendWorkspaceOwner()); const later = vi.fn(); subscribeProjectSeed(first); subscribeProjectSeed(later);
    expect(dispatchProjectSeed(seed)).toEqual({ delivered: 1, failed: 0 }); expect(later).not.toHaveBeenCalled();
    await resume(); expect(first).toHaveBeenCalledTimes(1); expect(later).toHaveBeenCalledExactlyOnceWith(seed);
  });
  it("suspension inside held delivery keeps the remaining order and consumes each completed seed once", async () => {
    dispatchProjectSeed(seed); dispatchProjectSeed({ ...seed, title: "second" }); dispatchProjectSeed({ ...seed, title: "third" });
    const got: ProjectSeed[] = []; subscribeProjectSeed((s) => { got.push(s); if (got.length === 1) suspendWorkspaceOwner(); });
    expect(got.map((s) => s.title)).toEqual([seed.title]); await resume();
    expect(got.map((s) => s.title)).toEqual([seed.title, "second", "third"]);
  });
  it.each(["return", "throw"])("held flush owner replacement on %s cannot deliver or resurrect later old seeds", async (ending) => {
    vi.spyOn(console, "error").mockImplementation(() => {}); dispatchProjectSeed(seed); dispatchProjectSeed({ ...seed, title: "second" });
    const got: ProjectSeed[] = []; subscribeProjectSeed((s) => { got.push(s); setWorkspaceOwner(B); if (ending === "throw") throw new Error("UNIT retired held callback"); });
    expect(got).toHaveLength(1); await awaitWorkspaceOwnerSession(workspaceOwnerSession()); const current = vi.fn(); subscribeProjectSeed(current);
    expect(current).not.toHaveBeenCalled();
  });
  it("an old unsubscribe cannot remove a same-function new owner registration", async () => {
    const consumer = vi.fn(); const offA = subscribeProjectSeed(consumer); await owner(B); subscribeProjectSeed(consumer); offA();
    expect(dispatchProjectSeed(seed)).toEqual({ delivered: 1, failed: 0 }); expect(consumer).toHaveBeenCalledExactlyOnceWith(seed);
  });
  it("unsubscribing a later consumer during dispatch prevents its stale snapshot callback", () => {
    let offLater = () => {}; const later = vi.fn(); subscribeProjectSeed(() => offLater()); offLater = subscribeProjectSeed(later);
    expect(dispatchProjectSeed(seed)).toEqual({ delivered: 1, failed: 0 }); expect(later).not.toHaveBeenCalled();
  });
  it("seam reset within a callback retires its snapshot and never assigns it to a new registration", () => {
    const old = vi.fn(); const current = vi.fn(); subscribeProjectSeed(() => { resetProjectSeedSeam(); subscribeProjectSeed(current); }); subscribeProjectSeed(old);
    dispatchProjectSeed(seed); expect(old).not.toHaveBeenCalled(); expect(current).not.toHaveBeenCalled();
    expect(dispatchProjectSeed(seed)).toEqual({ delivered: 1, failed: 0 }); expect(current).toHaveBeenCalledExactlyOnceWith(seed);
  });
  it("current multiple consumers receive independent seed and sources copies with isolated failure", () => {
    vi.spyOn(console, "error").mockImplementation(() => {}); const got: ProjectSeed[] = [];
    subscribeProjectSeed((s) => { s.title = "changed"; s.sources!.push("changed"); throw new Error("UNIT failure"); }); subscribeProjectSeed((s) => got.push(s));
    expect(dispatchProjectSeed(seed)).toEqual({ delivered: 1, failed: 1 }); expect(got).toEqual([seed]); expect(seed.sources).toEqual(["unit-doc"]);
    const later = vi.fn(); subscribeProjectSeed(later); expect(later).not.toHaveBeenCalled();
  });
  it("failed-only delivery stays held for a later same-owner healthy intake", () => {
    vi.spyOn(console, "error").mockImplementation(() => {}); const broken = subscribeProjectSeed(() => { throw new Error("UNIT failure"); });
    expect(dispatchProjectSeed(seed)).toEqual({ delivered: 0, failed: 1 }); broken();
    const good = vi.fn(); subscribeProjectSeed(good)(); expect(good).toHaveBeenCalledExactlyOnceWith(seed);
    const remount = vi.fn(); subscribeProjectSeed(remount); expect(remount).not.toHaveBeenCalled();
  });
  it("held values are independent of caller mutation before a confirmed intake arrives", () => {
    const input = { ...seed, sources: ["unit-doc"] }; dispatchProjectSeed(input); input.title = "changed"; input.sources.push("changed");
    const got = vi.fn(); subscribeProjectSeed(got); expect(got).toHaveBeenCalledExactlyOnceWith(seed);
  });
  it("a cookie recheck does not retry a previously failed consumer; the seed stays held for a later intake", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {}); const broken = vi.fn(() => { throw new Error("UNIT failure"); });
    subscribeProjectSeed(broken); dispatchProjectSeed(seed); expect(broken).toHaveBeenCalledTimes(1);
    suspendWorkspaceOwner(); await resume(); expect(broken).toHaveBeenCalledTimes(1);
    const good = vi.fn(); subscribeProjectSeed(good); expect(good).toHaveBeenCalledExactlyOnceWith(seed);
  });
  it("resume advances unattempted held seeds without retrying the callback that failed before suspension", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {}); dispatchProjectSeed(seed); dispatchProjectSeed({ ...seed, title: "second" });
    let failures = 0; const got: ProjectSeed[] = [];
    subscribeProjectSeed((s) => {
      if (s.title === seed.title) { failures++; if (failures === 1) suspendWorkspaceOwner(); throw new Error("UNIT first failure"); }
      got.push(s);
    });
    expect(failures).toBe(1); await resume(); expect(failures).toBe(1); expect(got.map((s) => s.title)).toEqual(["second"]);
    const later = vi.fn(); subscribeProjectSeed(later); expect(later).toHaveBeenCalledExactlyOnceWith(seed);
  });
});
