import { cleanup, fireEvent, render, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const harness = vi.hoisted(() => ({ generation: 1, get: vi.fn(), put: vi.fn() }));
vi.mock("../../lib/auth", () => ({
  useAuth: () => ({ state: { status: "authenticated" }, sessionGeneration: harness.generation }),
}));
vi.mock("../../lib/api", async (original) => {
  const actual = await original<typeof import("../../lib/api")>();
  return { ...actual, getInterviewMargin: harness.get, putInterviewMargin: harness.put };
});

import { ApiError } from "../../lib/api";
import InterviewNotes from "./InterviewNotes";
import { recoveryMarginKey } from "./recoveryMargin";

const ACCOUNT = "a".repeat(64);
const RECOVERY = "b".repeat(64);
const HASH = "c".repeat(64);
const margin = (body: string, revision = 3) => ({
  schema_version: 1 as const, interview_id: "i", revision, content_sha256: HASH,
  body, account_scope: ACCOUNT, recovery_scope: RECOVERY, replayed: false,
});

function installStorage(): Storage {
  const values = new Map<string, string>();
  const storage: Storage = {
    get length() { return values.size; }, clear: () => values.clear(),
    getItem: (key) => values.get(key) ?? null, key: (index) => [...values.keys()][index] ?? null,
    removeItem: (key) => void values.delete(key), setItem: (key, value) => void values.set(key, String(value)),
  };
  Object.defineProperty(window, "localStorage", { configurable: true, value: storage });
  return storage;
}

beforeEach(() => {
  installStorage(); harness.generation = 1; harness.get.mockReset(); harness.put.mockReset();
});
afterEach(cleanup);

describe("InterviewNotes server authority", () => {
  it("hydrates canonical empty content and never reads legacy bytes", async () => {
    localStorage.setItem("antiek.interview-notes.i", "FOREIGN");
    const spy = vi.spyOn(localStorage, "getItem");
    harness.get.mockResolvedValue(margin("", 0));
    const view = render(<InterviewNotes interviewId="i" />);
    await waitFor(() => expect((view.container.querySelector("textarea") as HTMLTextAreaElement).disabled).toBe(false));
    expect((view.container.querySelector("textarea") as HTMLTextAreaElement).value).toBe("");
    expect(view.container.textContent).toContain("bytes were not read");
    expect(spy).not.toHaveBeenCalledWith("antiek.interview-notes.i");
  });

  it("fails closed when hydration fails", async () => {
    harness.get.mockRejectedValue(new TypeError("offline"));
    const view = render(<InterviewNotes interviewId="i" autosaveDelayMs={0} />);
    await waitFor(() => expect(view.container.textContent).toContain("save unavailable"));
    expect((view.container.querySelector("textarea") as HTMLTextAreaElement).disabled).toBe(true);
    expect(harness.put).not.toHaveBeenCalled();
  });

  it("conditionally saves and writes recovery only for transport failure", async () => {
    harness.get.mockResolvedValue(margin("server"));
    harness.put.mockRejectedValue(new TypeError("network"));
    const view = render(<InterviewNotes interviewId="i" autosaveDelayMs={0} />);
    const textarea = await waitFor(() => {
      const node = view.container.querySelector("textarea") as HTMLTextAreaElement;
      expect(node.disabled).toBe(false); return node;
    });
    fireEvent.change(textarea, { target: { value: "offline draft" } });
    await waitFor(() => expect(view.container.textContent).toContain("recovery saved locally"));
    expect(harness.put).toHaveBeenCalledWith("i", expect.objectContaining({
      base_revision: 3, body: "offline draft", mutation_key: expect.any(String),
    }));
    expect(JSON.parse(localStorage.getItem(recoveryMarginKey(RECOVERY))!)).toMatchObject({
      account_scope: ACCOUNT, interview_id: "i", base_revision: 3, body: "offline draft",
    });
  });

  it("does not label an HTTP conflict offline", async () => {
    harness.get.mockResolvedValue(margin("server"));
    harness.put.mockRejectedValue(new ApiError("conflict", 409, "{}"));
    const view = render(<InterviewNotes interviewId="i" autosaveDelayMs={0} />);
    await waitFor(() => expect((view.container.querySelector("textarea") as HTMLTextAreaElement).disabled).toBe(false));
    fireEvent.change(view.container.querySelector("textarea")!, { target: { value: "changed" } });
    await waitFor(() => expect(view.container.textContent).toContain("conflict — reload"));
    expect(localStorage.getItem(recoveryMarginKey(RECOVERY))).toBeNull();
  });

  it("keeps an HTTP-failed draft visible and permits an explicit retry", async () => {
    harness.get.mockResolvedValue(margin("server"));
    harness.put
      .mockRejectedValueOnce(new ApiError("upstream", 500, "{}"))
      .mockResolvedValueOnce({ ...margin("changed", 4), content_sha256: "d".repeat(64) });
    const view = render(<InterviewNotes interviewId="i" autosaveDelayMs={0} />);
    await waitFor(() => expect((view.container.querySelector("textarea") as HTMLTextAreaElement).disabled).toBe(false));
    fireEvent.change(view.container.querySelector("textarea")!, { target: { value: "changed" } });
    await waitFor(() => expect(view.container.textContent).toContain("save failed — retry"));
    expect((view.container.querySelector("textarea") as HTMLTextAreaElement).value).toBe("changed");
    expect(localStorage.getItem(recoveryMarginKey(RECOVERY))).toBeNull();
    fireEvent.click([...view.container.querySelectorAll("button")].find((node) => node.textContent === "Retry save")!);
    await waitFor(() => expect(harness.put).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(view.container.textContent).toContain("saved"));
  });

  it("fences a slow prior-account hydration", async () => {
    let resolve!: (value: ReturnType<typeof margin>) => void;
    harness.get.mockReturnValueOnce(new Promise((done) => { resolve = done; }));
    harness.get.mockResolvedValueOnce(margin("ACCOUNT TWO"));
    const view = render(<InterviewNotes interviewId="i" />);
    harness.generation = 2;
    view.rerender(<InterviewNotes interviewId="i" />);
    resolve(margin("STALE ACCOUNT ONE"));
    await waitFor(() => expect((view.container.querySelector("textarea") as HTMLTextAreaElement).value).toBe("ACCOUNT TWO"));
  });
});
