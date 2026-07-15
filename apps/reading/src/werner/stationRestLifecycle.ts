export type StationRestPhase = "active" | "sleeping" | "waking" | "suspended";

/** A deliberate product value: long enough for the activity-specific idle gag
 * to remain the normal resting behavior, short enough for a research session
 * to reveal Werner's background-TV episode. Kept named and injectable. */
export const STATION_LONG_REST_MS = 120_000;
export const STATION_WAKE_MS = 900;

interface Scheduler {
  setTimeout(fn: () => void, ms: number): number;
  clearTimeout(id: number): void;
}

export interface StationRestLifecycle {
  getPhase(): StationRestPhase;
  setEligible(eligible: boolean): void;
  noteInteraction(): void;
  dispose(): void;
}

export function createStationRestLifecycle(
  onPhase: (phase: StationRestPhase) => void,
  options: {
    restMs?: number;
    wakeMs?: number;
    scheduler?: Scheduler;
  } = {},
): StationRestLifecycle {
  const restMs = options.restMs ?? STATION_LONG_REST_MS;
  const wakeMs = options.wakeMs ?? STATION_WAKE_MS;
  const scheduler = options.scheduler ?? {
    setTimeout: (fn, ms) => window.setTimeout(fn, ms),
    clearTimeout: (id) => window.clearTimeout(id),
  };
  let phase: StationRestPhase = "suspended";
  let eligible = false;
  let timer: number | null = null;
  let epoch = 0;

  const clear = () => {
    epoch += 1;
    if (timer !== null) scheduler.clearTimeout(timer);
    timer = null;
  };
  const publish = (next: StationRestPhase) => {
    if (phase === next) return;
    phase = next;
    onPhase(next);
  };
  const armRest = () => {
    clear();
    const token = epoch;
    timer = scheduler.setTimeout(() => {
      if (token !== epoch || !eligible || phase !== "active") return;
      timer = null;
      publish("sleeping");
    }, restMs);
  };

  return {
    getPhase: () => phase,
    setEligible(nextEligible) {
      if (eligible === nextEligible) return;
      eligible = nextEligible;
      clear();
      if (!eligible) {
        publish("suspended");
        return;
      }
      publish("active");
      armRest();
    },
    noteInteraction() {
      if (!eligible) return;
      if (phase === "sleeping") {
        clear();
        publish("waking");
        const token = epoch;
        timer = scheduler.setTimeout(() => {
          if (token !== epoch || !eligible || phase !== "waking") return;
          timer = null;
          publish("active");
          armRest();
        }, wakeMs);
        return;
      }
      if (phase === "waking") return;
      publish("active");
      armRest();
    },
    dispose() {
      eligible = false;
      clear();
      publish("suspended");
    },
  };
}
