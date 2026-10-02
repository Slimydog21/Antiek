export interface ModelUsageReadTask {
  isCurrent(): boolean;
  run(): Promise<void>;
}
/** Retirement removes scheduling permission; issued reads retain physical slots. */
export function createModelUsageReadQueue() {
  const waiting: ModelUsageReadTask[] = [];
  let outstanding = 0;
  const drain = () => {
    while (outstanding < 2 && waiting.length) {
      const task = waiting.shift();
      if (!task || !task.isCurrent()) continue;
      outstanding += 1;
      void (async () => {
        try {
          if (task.isCurrent()) await task.run();
        } catch {
          /* Read owners report their own failures; release the slot even on rejection. */
        } finally {
          outstanding -= 1;
          drain();
        }
      })();
    }
  };
  return {
    enqueue(task: ModelUsageReadTask) {
      waiting.push(task);
      drain();
    },
  };
}
// Shared across scoped picker mounts; the six legacy consumers remain separate.
export const modelUsageReadQueue = createModelUsageReadQueue();
