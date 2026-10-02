import { describe, expect, it } from "vitest";
import { createModelUsageReadQueue } from "./modelUsageReadQueue";
function deferred() {
  let resolve!: () => void;
  let reject!: (error: Error) => void;
  const promise = new Promise<void>((yes, no) => {
    resolve = yes;
    reject = no;
  });
  return { promise, resolve, reject };
}
const tick = async () => {
  await Promise.resolve();
  await Promise.resolve();
  await Promise.resolve();
};
describe("physical scoped balance queue", () => {
  it("keeps two occupied slots through retirement and only schedules current queued work", async () => {
    const queue = createModelUsageReadQueue();
    const reads = [deferred(), deferred(), deferred()];
    let live = true;
    let outstanding = 0;
    let peak = 0;
    const started: string[] = [];
    for (let index = 0; index < 3; index++)
      queue.enqueue({
        isCurrent: () => live,
        run: async () => {
          outstanding++;
          peak = Math.max(peak, outstanding);
          started.push(`old-${index}`);
          await reads[index].promise;
          outstanding--;
        },
      });
    expect(started).toEqual(["old-0", "old-1"]);
    live = false;
    const newer = deferred();
    queue.enqueue({
      isCurrent: () => true,
      run: async () => {
        outstanding++;
        peak = Math.max(peak, outstanding);
        started.push("new");
        await newer.promise;
        outstanding--;
      },
    });
    expect(started).not.toContain("new");
    reads[0].resolve();
    await tick();
    expect(started).toEqual(["old-0", "old-1", "new"]);
    expect(peak).toBe(2);
    reads[1].resolve();
    newer.resolve();
    await tick();
    expect(started).not.toContain("old-2");
    expect(outstanding).toBe(0);
  });
  it("drains another current task after an issued read rejects without an unhandled rejection", async () => {
    const queue = createModelUsageReadQueue();
    const a = deferred();
    const b = deferred();
    const started: string[] = [];
    queue.enqueue({ isCurrent: () => true, run: () => a.promise });
    queue.enqueue({ isCurrent: () => true, run: () => b.promise });
    queue.enqueue({
      isCurrent: () => true,
      run: async () => {
        started.push("third");
      },
    });
    a.reject(new Error("fixture failure"));
    await tick();
    expect(started).toEqual(["third"]);
    b.resolve();
    await tick();
  });
});
