interface StoredAttempt {
  key: string;
  inputSignature: string;
}

function storageKey(planId: string): string {
  return `antiek:cascade-launch-attempt:${planId}`;
}

export function acquireCascadeLaunchAttempt(planId: string, inputs: unknown): string {
  const inputSignature = JSON.stringify(inputs);
  try {
    const raw = sessionStorage.getItem(storageKey(planId));
    if (raw) {
      const stored = JSON.parse(raw) as Partial<StoredAttempt>;
      if (typeof stored.key === "string" && stored.key && stored.inputSignature === inputSignature) {
        return stored.key;
      }
    }
  } catch {
    // Storage denial must not disable launch; the mounted caller still retains
    // the key in memory and server authority remains decisive.
  }
  const key = crypto.randomUUID();
  try {
    sessionStorage.setItem(storageKey(planId), JSON.stringify({ key, inputSignature }));
  } catch {
    // Best effort only; no authority lives client-side.
  }
  return key;
}

export function clearCascadeLaunchAttempt(planId: string): void {
  try {
    sessionStorage.removeItem(storageKey(planId));
  } catch {
    // Best-effort browser cleanup.
  }
}
